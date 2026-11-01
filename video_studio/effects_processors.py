"""OMNIA Video Studio — Video Effects & Color Processors (Module 10).

Implements:
- IVideoEffectProcessor: Base processor contract (process, reset, schemas).
- TransformEffectProcessor: 2D translation (pos_x, pos_y), scale (scale_x, scale_y, uniform), rotation (degrees around pivot), and interpolation.
- OpacityEffectProcessor: Alpha scaling with non-destructive blend.
- FlipEffectProcessor: Horizontal and vertical image mirroring.
- ColorCorrectionProcessor: Exposure (EV stops), Brightness (-100 to 100), Contrast (0.0 to 3.0), Saturation (0.0 to 3.0), Temperature (-100 to 100), Tint (-100 to 100).
- InvertEffectProcessor: Photometric color inversion.
- EffectProcessorRegistry: Central registration, discovery, parameter validation, and instance creation.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple
import math
import numpy as np
import cv2

from video_studio.effects_models import (
    VideoFrameBuffer,
    EffectParameterSchema,
    ParameterType,
    EffectCategory,
    ProcessingBackend,
    EffectInstance,
)

# ==============================================================================
# 1. Base Effect Processor Interface
# ==============================================================================

class IVideoEffectProcessor(ABC):
    """Abstract contract for an image-frame processing node."""

    def __init__(self, effect_id: str, name: str, category: EffectCategory):
        self.effect_id = effect_id
        self.name = name
        self.category = category
        self.backend = ProcessingBackend.CPU
        self.parameter_schemas: Dict[str, EffectParameterSchema] = {}

    @abstractmethod
    def process_frame(
        self,
        frame: VideoFrameBuffer,
        parameters: Dict[str, Any],
        render_width: int,
        render_height: int,
    ) -> VideoFrameBuffer:
        """Processes the video frame buffer in-place or returns a transformed buffer."""
        pass

    def validate_parameters(self, raw_params: Dict[str, Any]) -> Dict[str, Any]:
        """Validates all input parameters against schema, clamping and applying defaults."""
        validated = {}
        for param_id, schema in self.parameter_schemas.items():
            val = raw_params.get(param_id, schema.default_value)
            ok, clean_val, _ = schema.validate(val)
            validated[param_id] = clean_val
        return validated

    def get_schemas(self) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self.parameter_schemas.values()]


# ==============================================================================
# 2. Transform & Opacity Processors
# ==============================================================================

class TransformEffectProcessor(IVideoEffectProcessor):
    """2D Spatial Transformation: Translation, Scaling, and Rotation around a pivot."""

    def __init__(self):
        super().__init__("effect.transform", "Transform", EffectCategory.TRANSFORM)
        self.parameter_schemas = {
            "pos_x": EffectParameterSchema("pos_x", "Position X", ParameterType.FLOAT, 0.0, unit="px"),
            "pos_y": EffectParameterSchema("pos_y", "Position Y", ParameterType.FLOAT, 0.0, unit="px"),
            "scale_x": EffectParameterSchema("scale_x", "Scale X", ParameterType.FLOAT, 1.0, min_value=0.001, max_value=20.0),
            "scale_y": EffectParameterSchema("scale_y", "Scale Y", ParameterType.FLOAT, 1.0, min_value=0.001, max_value=20.0),
            "uniform_scale": EffectParameterSchema("uniform_scale", "Uniform Scale", ParameterType.BOOLEAN, True),
            "rotation": EffectParameterSchema("rotation", "Rotation", ParameterType.ANGLE, 0.0, min_value=-360.0, max_value=360.0, unit="deg"),
            "pivot_x": EffectParameterSchema("pivot_x", "Pivot X (Normalized)", ParameterType.FLOAT, 0.5, min_value=0.0, max_value=1.0),
            "pivot_y": EffectParameterSchema("pivot_y", "Pivot Y (Normalized)", ParameterType.FLOAT, 0.5, min_value=0.0, max_value=1.0),
        }

    def process_frame(
        self,
        frame: VideoFrameBuffer,
        parameters: Dict[str, Any],
        render_width: int,
        render_height: int,
    ) -> VideoFrameBuffer:
        p = self.validate_parameters(parameters)
        pos_x = float(p["pos_x"])
        pos_y = float(p["pos_y"])
        scale_x = float(p["scale_x"])
        scale_y = float(p["scale_x"]) if p["uniform_scale"] else float(p["scale_y"])
        rot = float(p["rotation"])
        pivot_x = float(p["pivot_x"]) * frame.width
        pivot_y = float(p["pivot_y"]) * frame.height

        # Identity bypass check
        if abs(pos_x) < 1e-3 and abs(pos_y) < 1e-3 and abs(scale_x - 1.0) < 1e-3 and abs(scale_y - 1.0) < 1e-3 and abs(rot) < 1e-3:
            return frame

        # Compute affine 2x3 matrix: T(pos) * T(pivot) * R(rot) * S(scale) * T(-pivot)
        rad = math.radians(rot)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)

        # Scale and Rotate around pivot
        m00 = cos_a * scale_x
        m01 = -sin_a * scale_y
        m10 = sin_a * scale_x
        m11 = cos_a * scale_y

        # Offset
        tx = pos_x + pivot_x - (m00 * pivot_x + m01 * pivot_y)
        ty = pos_y + pivot_y - (m10 * pivot_x + m11 * pivot_y)

        matrix = np.array([[m00, m01, tx], [m10, m11, ty]], dtype=np.float32)

        # Apply warp affine using OpenCV
        transformed = cv2.warpAffine(
            frame.data,
            matrix,
            (frame.width, frame.height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0, 0),
        )

        out_frame = frame.copy()
        out_frame.data = transformed
        return out_frame


class OpacityEffectProcessor(IVideoEffectProcessor):
    """Linear Alpha / Opacity blend processor."""

    def __init__(self):
        super().__init__("effect.opacity", "Opacity", EffectCategory.COMPOSITING)
        self.parameter_schemas = {
            "opacity": EffectParameterSchema("opacity", "Opacity", ParameterType.FLOAT, 1.0, min_value=0.0, max_value=1.0),
        }

    def process_frame(
        self,
        frame: VideoFrameBuffer,
        parameters: Dict[str, Any],
        render_width: int,
        render_height: int,
    ) -> VideoFrameBuffer:
        p = self.validate_parameters(parameters)
        opacity = float(p["opacity"])
        if abs(opacity - 1.0) < 1e-4:
            return frame

        out = frame.copy()
        # Scale alpha channel (index 3 in RGBA)
        if out.data.shape[2] == 4:
            out.data[:, :, 3] = np.clip(out.data[:, :, 3].astype(np.float32) * opacity, 0, 255).astype(np.uint8)
        return out


class FlipEffectProcessor(IVideoEffectProcessor):
    """Image flipping horizontally or vertically."""

    def __init__(self):
        super().__init__("effect.flip", "Flip", EffectCategory.TRANSFORM)
        self.parameter_schemas = {
            "flip_horizontal": EffectParameterSchema("flip_horizontal", "Flip Horizontal", ParameterType.BOOLEAN, False),
            "flip_vertical": EffectParameterSchema("flip_vertical", "Flip Vertical", ParameterType.BOOLEAN, False),
        }

    def process_frame(
        self,
        frame: VideoFrameBuffer,
        parameters: Dict[str, Any],
        render_width: int,
        render_height: int,
    ) -> VideoFrameBuffer:
        p = self.validate_parameters(parameters)
        flip_h = p["flip_horizontal"]
        flip_v = p["flip_vertical"]

        if not flip_h and not flip_v:
            return frame

        out = frame.copy()
        if flip_h and flip_v:
            out.data = cv2.flip(out.data, -1)
        elif flip_h:
            out.data = cv2.flip(out.data, 1)
        elif flip_v:
            out.data = cv2.flip(out.data, 0)
        return out


# ==============================================================================
# 3. Foundational Color Correction Processor
# ==============================================================================

class ColorCorrectionProcessor(IVideoEffectProcessor):
    """Comprehensive color grading: Exposure (EV), Brightness, Contrast, Saturation, Temperature, and Tint."""

    def __init__(self):
        super().__init__("effect.color_correction", "Color Correction", EffectCategory.COLOR)
        self.parameter_schemas = {
            "exposure": EffectParameterSchema("exposure", "Exposure", ParameterType.FLOAT, 0.0, min_value=-5.0, max_value=5.0, unit="EV"),
            "brightness": EffectParameterSchema("brightness", "Brightness", ParameterType.FLOAT, 0.0, min_value=-100.0, max_value=100.0),
            "contrast": EffectParameterSchema("contrast", "Contrast", ParameterType.FLOAT, 1.0, min_value=0.0, max_value=3.0),
            "saturation": EffectParameterSchema("saturation", "Saturation", ParameterType.FLOAT, 1.0, min_value=0.0, max_value=3.0),
            "temperature": EffectParameterSchema("temperature", "Temperature", ParameterType.FLOAT, 0.0, min_value=-100.0, max_value=100.0),
            "tint": EffectParameterSchema("tint", "Tint", ParameterType.FLOAT, 0.0, min_value=-100.0, max_value=100.0),
            "gamma": EffectParameterSchema("gamma", "Gamma", ParameterType.FLOAT, 1.0, min_value=0.1, max_value=3.0),
        }

    def process_frame(
        self,
        frame: VideoFrameBuffer,
        parameters: Dict[str, Any],
        render_width: int,
        render_height: int,
    ) -> VideoFrameBuffer:
        p = self.validate_parameters(parameters)
        exp_ev = float(p["exposure"])
        brightness = float(p["brightness"])
        contrast = float(p["contrast"])
        saturation = float(p["saturation"])
        temp = float(p["temperature"])
        tint = float(p["tint"])
        gamma = float(p["gamma"])

        # Check identity
        is_identity = (
            abs(exp_ev) < 1e-3
            and abs(brightness) < 1e-3
            and abs(contrast - 1.0) < 1e-3
            and abs(saturation - 1.0) < 1e-3
            and abs(temp) < 1e-3
            and abs(tint) < 1e-3
            and abs(gamma - 1.0) < 1e-3
        )
        if is_identity:
            return frame

        out = frame.copy()
        # Separate RGB and Alpha
        rgb = out.data[:, :, :3].astype(np.float32) / 255.0
        alpha = out.data[:, :, 3:] if out.data.shape[2] == 4 else None

        # 1. Exposure: 2^EV multiplier
        if abs(exp_ev) > 1e-3:
            rgb *= (2.0 ** exp_ev)

        # 2. Temperature & Tint
        # Temperature adjusts Red vs Blue channels
        if abs(temp) > 1e-3:
            t_factor = temp / 100.0
            rgb[:, :, 0] += t_factor * 0.1 # Red (warmer)
            rgb[:, :, 2] -= t_factor * 0.1 # Blue (cooler)

        # Tint adjusts Green vs Magenta
        if abs(tint) > 1e-3:
            tint_factor = tint / 100.0
            rgb[:, :, 1] += tint_factor * 0.1 # Green

        # 3. Contrast & Brightness
        # contrast around 0.5 center, plus brightness offset
        if abs(contrast - 1.0) > 1e-3 or abs(brightness) > 1e-3:
            b_offset = brightness / 255.0
            rgb = (rgb - 0.5) * contrast + 0.5 + b_offset

        # 4. Gamma power curve
        if abs(gamma - 1.0) > 1e-3:
            rgb = np.maximum(0.0, rgb) ** (1.0 / gamma)

        # 5. Saturation in Rec.709 Luminance space
        if abs(saturation - 1.0) > 1e-3:
            # Rec.709 luma weights: 0.2126 R + 0.7152 G + 0.0722 B
            luma = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
            luma = np.expand_dims(luma, axis=-1)
            rgb = luma + saturation * (rgb - luma)

        # Clamp and restore uint8
        clamped_rgb = np.clip(rgb * 255.0, 0, 255).astype(np.uint8)

        if alpha is not None:
            out.data = np.concatenate([clamped_rgb, alpha], axis=-1)
        else:
            out.data = clamped_rgb

        return out


class InvertEffectProcessor(IVideoEffectProcessor):
    """Photometric Color Inversion."""

    def __init__(self):
        super().__init__("effect.invert", "Invert", EffectCategory.FILTER)
        self.parameter_schemas = {
            "invert_rgb": EffectParameterSchema("invert_rgb", "Invert RGB", ParameterType.BOOLEAN, True),
            "invert_alpha": EffectParameterSchema("invert_alpha", "Invert Alpha", ParameterType.BOOLEAN, False),
        }

    def process_frame(
        self,
        frame: VideoFrameBuffer,
        parameters: Dict[str, Any],
        render_width: int,
        render_height: int,
    ) -> VideoFrameBuffer:
        p = self.validate_parameters(parameters)
        inv_rgb = p["invert_rgb"]
        inv_a = p["invert_alpha"]

        if not inv_rgb and not inv_a:
            return frame

        out = frame.copy()
        if inv_rgb:
            out.data[:, :, :3] = 255 - out.data[:, :, :3]
        if inv_a and out.data.shape[2] == 4:
            out.data[:, :, 3] = 255 - out.data[:, :, 3]
        return out


# ==============================================================================
# 4. Effect Processor Registry
# ==============================================================================

class EffectProcessorRegistry:
    """Central registry and factory for all video effects and color processors."""

    def __init__(self):
        self._processors: Dict[str, IVideoEffectProcessor] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        builtins = [
            TransformEffectProcessor(),
            OpacityEffectProcessor(),
            FlipEffectProcessor(),
            ColorCorrectionProcessor(),
            InvertEffectProcessor(),
        ]
        for b in builtins:
            self._processors[b.effect_id] = b

        try:
            from video_studio.chroma_processor import ChromaKeyEffectProcessor
            ck = ChromaKeyEffectProcessor()
            self._processors[ck.effect_id] = ck
        except Exception:
            pass

        try:
            from video_studio.denoise_processor import VideoDenoiseEffectProcessor
            dn = VideoDenoiseEffectProcessor()
            self._processors[dn.effect_id] = dn
        except Exception:
            pass

        try:
            from video_studio.upscale_processor import VideoUpscaleEffectProcessor
            up = VideoUpscaleEffectProcessor()
            self._processors[up.effect_id] = up
        except Exception:
            pass

        try:
            from video_studio.deblur_processor import VideoDeblurEffectProcessor
            db = VideoDeblurEffectProcessor()
            self._processors[db.effect_id] = db
        except Exception:
            pass

        try:
            from video_studio.lighting_processor import VideoLightingEffectProcessor
            lt = VideoLightingEffectProcessor()
            self._processors[lt.effect_id] = lt
        except Exception:
            pass

        try:
            from video_studio.lens_processor import VideoLensEffectProcessor
            le = VideoLensEffectProcessor()
            self._processors[le.effect_id] = le
        except Exception:
            pass

        try:
            from video_studio.grain_processor import VideoGrainEffectProcessor
            gr = VideoGrainEffectProcessor()
            self._processors[gr.effect_id] = gr
        except Exception:
            pass

        try:
            from video_studio.depth_processor import VideoDepthEffectProcessor
            dp = VideoDepthEffectProcessor()
            self._processors[dp.effect_id] = dp
        except Exception:
            pass

        try:
            from video_studio.optical_flow_processor import VideoMotionFlowEffectProcessor
            fl = VideoMotionFlowEffectProcessor()
            self._processors[fl.effect_id] = fl
        except Exception:
            pass

        try:
            from video_studio.segmentation_processor import VideoSegmentationEffectProcessor
            sg = VideoSegmentationEffectProcessor()
            self._processors[sg.effect_id] = sg
        except Exception:
            pass

    def register(self, processor: IVideoEffectProcessor) -> None:
        self._processors[processor.effect_id] = processor

    def get(self, effect_id: str) -> Optional[IVideoEffectProcessor]:
        return self._processors.get(effect_id)

    def list_effects(self) -> List[Dict[str, Any]]:
        return [
            {
                "effect_id": p.effect_id,
                "name": p.name,
                "category": p.category.value,
                "backend": p.backend.value,
                "parameters": p.get_schemas(),
            }
            for p in self._processors.values()
        ]

    def create_instance(self, effect_id: str, parameters: Optional[Dict[str, Any]] = None) -> EffectInstance:
        proc = self._processors.get(effect_id)
        if not proc:
            raise ValueError(f"Effect '{effect_id}' is not registered.")
        clean_params = proc.validate_parameters(parameters or {})
        return EffectInstance(
            effect_id=effect_id,
            name=proc.name,
            category=proc.category,
            parameters=clean_params,
        )


# Global singleton
effect_processor_registry = EffectProcessorRegistry()
