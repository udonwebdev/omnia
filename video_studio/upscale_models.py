"""OMNIA Video Studio — Video Upscaling, Super-Resolution & Detail Enhancement Models (Module 26).

Defines authoritative domain models for:
- UpscaleAlgorithm: NEAREST_NEIGHBOR, BILINEAR, BICUBIC, LANCZOS4, LEARNED_SUPER_RES (Model-backed).
- SizingPolicy: SCALE_FACTOR, FIT_CANVAS, FILL_CANVAS, CUSTOM_DIMENSIONS.
- AspectRatioMode: PRESERVE_ASPECT, STRETCH, CENTER_CROP.
- QualityMode: FAST, BALANCED, HIGH_QUALITY.
- UpscaleConfig: Complete serializable parameter configuration.
- UpscaleDiagnostics: Metadata on processed dimensions, scale factor, time, and backend used.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple


class UpscaleAlgorithm(str, Enum):
    NEAREST_NEIGHBOR = "NEAREST_NEIGHBOR" # Fast nearest-neighbor replication
    BILINEAR = "BILINEAR"                 # Bilinear interpolation
    BICUBIC = "BICUBIC"                   # Bicubic spline interpolation
    LANCZOS4 = "LANCZOS4"                 # Lanczos 8x8 neighborhood sinc reconstruction
    LEARNED_SUPER_RES = "LEARNED_SUPER_RES" # Model-backed neural super-resolution (when runtime available)


class SizingPolicy(str, Enum):
    SCALE_FACTOR = "SCALE_FACTOR"         # Multiplier e.g. 1.5x, 2.0x, 4.0x
    FIT_CANVAS = "FIT_CANVAS"             # Scale to fit inside target canvas preserving aspect ratio
    FILL_CANVAS = "FILL_CANVAS"           # Scale to fill target canvas with center cropping
    CUSTOM_DIMENSIONS = "CUSTOM_DIMENSIONS" # Explicit target (width, height)


class AspectRatioMode(str, Enum):
    PRESERVE_ASPECT = "PRESERVE_ASPECT"   # Letterbox / pillarbox if needed
    STRETCH = "STRETCH"                   # Anamorphic stretch to target
    CENTER_CROP = "CENTER_CROP"           # Crop excess to fill dimension exactly


class UpscaleQualityMode(str, Enum):
    FAST = "FAST"                         # Lower order / nearest / linear for preview
    BALANCED = "BALANCED"                 # Standard bicubic / standard lanczos
    HIGH_QUALITY = "HIGH_QUALITY"         # Lanczos4 with post-restoration unsharp detail enhancement


@dataclass
class UpscaleConfig:
    """Configuration for video frame upscaling, super-resolution, and detail enhancement."""
    algorithm: UpscaleAlgorithm = UpscaleAlgorithm.LANCZOS4
    sizing_policy: SizingPolicy = SizingPolicy.SCALE_FACTOR
    aspect_mode: AspectRatioMode = AspectRatioMode.PRESERVE_ASPECT
    quality_mode: UpscaleQualityMode = UpscaleQualityMode.BALANCED

    # Target Dimensions or Scale
    scale_factor: float = 2.0             # Scale multiplier (1.0 to 8.0)
    target_width: int = 1920              # Used when sizing_policy is CUSTOM or FIT/FILL
    target_height: int = 1080

    # Detail Enhancement & Sharpening
    detail_enhancement: bool = True       # Enable post-upscale edge detail sharpening
    sharpen_amount: float = 0.25          # Post-upscale unsharp mask amount [0.0 to 1.0]
    sharpen_radius: float = 1.0           # Gaussian blur radius for unsharp mask
    halo_suppression: bool = True         # Clamp ringing and halo artifacts around sharp transitions

    # Pre-upscale Denoising Integration (Module 25)
    pre_denoise: bool = False             # Clean source noise before enlarging artifacts
    denoise_strength: float = 10.0

    # Learned Super-Resolution Model Configuration
    model_name: Optional[str] = None      # e.g. "ESPCN", "FSRCNN", "EDSR", "LapSRN"
    model_path: Optional[str] = None
    use_gpu: bool = False

    is_enabled: bool = True

    def calculate_target_size(self, src_w: int, src_h: int) -> Tuple[int, int]:
        """Calculates exact output (width, height) respecting sizing policy and aspect ratio."""
        if self.sizing_policy == SizingPolicy.SCALE_FACTOR:
            w = max(2, int(round(src_w * self.scale_factor)))
            h = max(2, int(round(src_h * self.scale_factor)))
            # Ensure even dimensions for video codecs
            if w % 2 != 0: w += 1
            if h % 2 != 0: h += 1
            return w, h

        target_w = max(2, self.target_width)
        target_h = max(2, self.target_height)

        if self.aspect_mode == AspectRatioMode.STRETCH:
            return target_w, target_h

        # Aspect ratio calculations
        src_aspect = src_w / max(1.0, src_h)
        tgt_aspect = target_w / max(1.0, target_h)

        if self.sizing_policy == SizingPolicy.FIT_CANVAS:
            if src_aspect > tgt_aspect:
                w = target_w
                h = max(2, int(round(target_w / src_aspect)))
            else:
                h = target_h
                w = max(2, int(round(target_h * src_aspect)))
        elif self.sizing_policy == SizingPolicy.FILL_CANVAS:
            if src_aspect > tgt_aspect:
                h = target_h
                w = max(2, int(round(target_h * src_aspect)))
            else:
                w = target_w
                h = max(2, int(round(target_w / src_aspect)))
        else: # CUSTOM_DIMENSIONS
            w = target_w
            h = target_h

        if w % 2 != 0: w += 1
        if h % 2 != 0: h += 1
        return w, h

    def to_dict(self) -> Dict[str, Any]:
        return {
            "algorithm": self.algorithm.value,
            "sizing_policy": self.sizing_policy.value,
            "aspect_mode": self.aspect_mode.value,
            "quality_mode": self.quality_mode.value,
            "scale_factor": round(self.scale_factor, 2),
            "target_width": self.target_width,
            "target_height": self.target_height,
            "detail_enhancement": self.detail_enhancement,
            "sharpen_amount": round(self.sharpen_amount, 2),
            "sharpen_radius": round(self.sharpen_radius, 2),
            "halo_suppression": self.halo_suppression,
            "pre_denoise": self.pre_denoise,
            "denoise_strength": round(self.denoise_strength, 2),
            "model_name": self.model_name,
            "model_path": self.model_path,
            "use_gpu": self.use_gpu,
            "is_enabled": self.is_enabled,
        }


@dataclass
class UpscaleDiagnostics:
    """Operational telemetry and processing diagnostics for an upscaling run."""
    input_width: int
    input_height: int
    output_width: int
    output_height: int
    scale_factor_x: float
    scale_factor_y: float
    processing_time_ms: float
    algorithm_used: str
    backend: str = "CPU"
    model_inference: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "input_width": self.input_width,
            "input_height": self.input_height,
            "output_width": self.output_width,
            "output_height": self.output_height,
            "scale_factor_x": round(self.scale_factor_x, 3),
            "scale_factor_y": round(self.scale_factor_y, 3),
            "processing_time_ms": round(self.processing_time_ms, 2),
            "algorithm_used": self.algorithm_used,
            "backend": self.backend,
            "model_inference": self.model_inference,
        }
