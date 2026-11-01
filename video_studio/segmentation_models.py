"""OMNIA Video Studio — Object Segmentation, Semantic Masking & Subject Isolation Models (Module 34).

Defines authoritative domain models for:
- SegmentationWorkflowType: MODEL_BACKED (AI neural runtime), MANUAL_SPLINE, IMPORTED_MASK, CHROMA_KEY_MATTE
- SegmentationPromptType: POSITIVE_POINT, NEGATIVE_POINT, BOUNDING_BOX, TEXT_PROMPT
- MaskCombinationMode: REPLACE, UNION (ADD), INTERSECT, SUBTRACT, INVERT
- MaskFormat: FLOAT32_SOFT, UINT8_BINARY
- SegmentationModelStatus: AVAILABLE, UNAVAILABLE, FAILED
- SegmentationPrompt: Typed container for positive/negative point coords, boxes, and text prompts
- ModelRuntimeDescriptor: Provenance, model weights path, supported prompt types, hardware requirements
- VideoSegmentMask: Single frame segmentation mask with provenance, soft alpha data, confidence, and bounds
- MultiMaskFrameContainer: Multi-mask per-frame representation with object instance IDs
- MaskRefinementConfig: Thresholding, Gaussian/bilateral edge feathering, erosion, dilation, hole-filling, inversion
- SegmentationJobStatus: QUEUED, PROCESSING, COMPLETED, CANCELLED, FAILED
- SegmentationDiagnostics: Latency, pixel coverage percentage, confidence metrics, warnings
"""

import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import numpy as np


class SegmentationWorkflowType(str, Enum):
    """Origin and computation mode of the segmentation mask."""
    MODEL_BACKED = "MODEL_BACKED"       # Neural deep-learning runtime (e.g. SAM / MobileSAM / DeepLab)
    MANUAL_SPLINE = "MANUAL_SPLINE"     # User hand-drawn vector spline / rotoscope mask
    IMPORTED_MASK = "IMPORTED_MASK"     # Externally rendered grayscale or alpha video sequence
    CHROMA_KEY_MATTE = "CHROMA_KEY_MATTE" # Extracted from Module 23 Chroma Keying engine


class SegmentationPromptType(str, Enum):
    """Input prompt modalities supported by interactive segmentation models."""
    POSITIVE_POINT = "POSITIVE_POINT"   # Foreground inclusion point (x, y)
    NEGATIVE_POINT = "NEGATIVE_POINT"   # Background exclusion point (x, y)
    BOUNDING_BOX = "BOUNDING_BOX"       # Inclusion bounding box (x1, y1, x2, y2)
    TEXT_PROMPT = "TEXT_PROMPT"         # Semantic natural language text prompt (if conditioned)


class MaskCombinationMode(str, Enum):
    """Boolean and blending operations between overlapping masks or chroma mattes."""
    REPLACE = "REPLACE"                 # Overwrite target matte
    UNION = "UNION"                     # max(A, B) - additive combine
    INTERSECT = "INTERSECT"             # A * B - logical AND intersection
    SUBTRACT = "SUBTRACT"               # max(0, A - B) - subtractive cut
    INVERT = "INVERT"                   # 1.0 - A


class MaskFormat(str, Enum):
    """Precision and dynamic range of mask data."""
    FLOAT32_SOFT = "FLOAT32_SOFT"       # Floating-point [0.0, 1.0] preserving subpixel antialiasing & hair detail
    UINT8_BINARY = "UINT8_BINARY"       # Strict binary 0 or 255 mask


class SegmentationModelStatus(str, Enum):
    """Runtime availability of the neural segmentation engine."""
    AVAILABLE = "AVAILABLE"             # Valid model weights and runtime present and loaded
    UNAVAILABLE = "UNAVAILABLE"         # No model weights bundled or runtime unsupported
    FAILED = "FAILED"                   # Inference error during execution


@dataclass
class SegmentationPrompt:
    """User-supplied prompt coordinate or description."""
    prompt_type: SegmentationPromptType
    # Coordinates in normalized image space [0.0, 1.0] or absolute pixels
    x: float = 0.0
    y: float = 0.0
    # Bounding box coords (x1, y1, x2, y2)
    box: Optional[Tuple[float, float, float, float]] = None
    text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt_type": self.prompt_type.value,
            "x": round(float(self.x), 3),
            "y": round(float(self.y), 3),
            "box": list(self.box) if self.box else None,
            "text": self.text,
        }


@dataclass
class ModelRuntimeDescriptor:
    """Metadata describing a segmentation neural network model."""
    model_id: str = "sam_base_stub"
    model_name: str = "Segment Anything Model (SAM) Adapter"
    version: str = "1.0.0"
    provider: str = "local_onnx"
    supported_prompts: List[SegmentationPromptType] = field(default_factory=lambda: [
        SegmentationPromptType.POSITIVE_POINT,
        SegmentationPromptType.NEGATIVE_POINT,
        SegmentationPromptType.BOUNDING_BOX,
    ])
    supported_classes: List[str] = field(default_factory=lambda: ["generic_object", "person", "foreground"])
    is_text_conditioned: bool = False
    requires_gpu: bool = True
    weights_path: Optional[str] = None
    status: SegmentationModelStatus = SegmentationModelStatus.UNAVAILABLE
    status_reason: str = "No local neural model weights bundled in standard workspace."

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_name": self.model_name,
            "version": self.version,
            "provider": self.provider,
            "supported_prompts": [p.value for p in self.supported_prompts],
            "supported_classes": self.supported_classes,
            "is_text_conditioned": self.is_text_conditioned,
            "requires_gpu": self.requires_gpu,
            "weights_path": self.weights_path,
            "status": self.status.value,
            "status_reason": self.status_reason,
        }


@dataclass
class MaskRefinementConfig:
    """Non-destructive morphological and edge-refinement parameters."""
    threshold: float = 0.5              # Binarization cutoff [0.0, 1.0] (0.0 to disable thresholding)
    enable_threshold: bool = False      # If False, soft antialiased edges are strictly preserved
    feather_radius: float = 0.0         # Edge feather radius in pixels [0.0, 50.0]
    feather_edge_aware: bool = False    # If True, guided bilateral filter; if False, Gaussian feather
    erode_radius: int = 0               # Morphological shrink in pixels [0, 20]
    dilate_radius: int = 0              # Morphological expand in pixels [0, 20]
    fill_holes: bool = False            # Automatic connected-component interior hole closure
    invert_mask: bool = False           # Invert foreground/background polarity

    def to_dict(self) -> Dict[str, Any]:
        return {
            "threshold": round(float(self.threshold), 3),
            "enable_threshold": self.enable_threshold,
            "feather_radius": round(float(self.feather_radius), 2),
            "feather_edge_aware": self.feather_edge_aware,
            "erode_radius": self.erode_radius,
            "dilate_radius": self.dilate_radius,
            "fill_holes": self.fill_holes,
            "invert_mask": self.invert_mask,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MaskRefinementConfig":
        return cls(
            threshold=float(data.get("threshold", 0.5)),
            enable_threshold=bool(data.get("enable_threshold", False)),
            feather_radius=float(data.get("feather_radius", 0.0)),
            feather_edge_aware=bool(data.get("feather_edge_aware", False)),
            erode_radius=int(data.get("erode_radius", 0)),
            dilate_radius=int(data.get("dilate_radius", 0)),
            fill_holes=bool(data.get("fill_holes", False)),
            invert_mask=bool(data.get("invert_mask", False)),
        )


@dataclass
class VideoSegmentMask:
    """Individual segmented mask with pixel data and metadata."""
    mask_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    instance_id: int = 1
    label: str = "foreground_subject"
    workflow: SegmentationWorkflowType = SegmentationWorkflowType.MODEL_BACKED
    width: int = 1920
    height: int = 1080
    data: Optional[np.ndarray] = None   # 2D float32 [0.0, 1.0] array
    confidence: float = 1.0
    bounding_box: Optional[Tuple[int, int, int, int]] = None # (x1, y1, x2, y2)
    is_visible: bool = True
    refinement: MaskRefinementConfig = field(default_factory=MaskRefinementConfig)

    def to_dict(self) -> Dict[str, Any]:
        has_data = self.data is not None
        coverage_pct = 0.0
        if has_data:
            coverage_pct = float(np.count_nonzero(self.data > 0.1)) / float(self.data.size) * 100.0
        return {
            "mask_id": self.mask_id,
            "instance_id": self.instance_id,
            "label": self.label,
            "workflow": self.workflow.value,
            "width": self.width,
            "height": self.height,
            "has_data": has_data,
            "confidence": round(float(self.confidence), 3),
            "bounding_box": list(self.bounding_box) if self.bounding_box else None,
            "is_visible": self.is_visible,
            "coverage_percentage": round(coverage_pct, 2),
            "refinement": self.refinement.to_dict(),
        }


@dataclass
class MultiMaskFrameContainer:
    """Complete collection of segmentation masks for a single video timeline frame."""
    frame_index: int = 0
    pts_seconds: float = 0.0
    clip_id: str = "default_clip"
    masks: List[VideoSegmentMask] = field(default_factory=list)

    def get_mask(self, mask_id: str) -> Optional[VideoSegmentMask]:
        for m in self.masks:
            if m.mask_id == mask_id:
                return m
        return None

    def composite_combined_mask(self, mode: MaskCombinationMode = MaskCombinationMode.UNION) -> Optional[np.ndarray]:
        """Combine all visible masks into a single float32 [0.0, 1.0] alpha matte."""
        visible = [m for m in self.masks if m.is_visible and m.data is not None]
        if not visible:
            return None

        h, w = visible[0].height, visible[0].width
        accum = visible[0].data.copy()

        for m in visible[1:]:
            d = m.data
            if mode == MaskCombinationMode.UNION:
                accum = np.maximum(accum, d)
            elif mode == MaskCombinationMode.INTERSECT:
                accum = accum * d
            elif mode == MaskCombinationMode.SUBTRACT:
                accum = np.maximum(0.0, accum - d)
            elif mode == MaskCombinationMode.REPLACE:
                accum = d.copy()

        return np.clip(accum, 0.0, 1.0)
