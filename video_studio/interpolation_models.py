"""OMNIA Video Studio — Frame Interpolation & Frame-Rate Conversion Models (Module 27).

Defines authoritative domain models for:
- InterpolationMethod: FRAME_DUPLICATION, FRAME_BLENDING, MOTION_COMPENSATED_OPTICAL_FLOW, LEARNED_RIFE (Model-backed).
- TimestampPolicy: EXACT_RATIONAL, VARIABLE_SMOOTHED, AUDIO_MASTER_SLAVE.
- SceneCutAction: NEAREST_FALLBACK, DUP_PREV, CUT_SPLIT.
- RationalFrameRate: Exact integer numerator/denominator representation avoiding floating point drift.
- FrameRateConversionConfig: Complete configuration for rate conversion, slow motion, and motion-compensated synthesis.
- InterpolationDiagnostics: Operational telemetry on generated frames, detected cuts, and optical flow confidence.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
from fractions import Fraction
import math


class InterpolationMethod(str, Enum):
    FRAME_DUPLICATION = "FRAME_DUPLICATION"             # Nearest source frame selection (fastest, no ghosting)
    FRAME_BLENDING = "FRAME_BLENDING"                   # Weighted temporal crossfade (smooth, ghosting on fast motion)
    MOTION_COMPENSATED = "MOTION_COMPENSATED"           # Farneback dense optical flow bi-directional motion warping
    LEARNED_MODEL = "LEARNED_MODEL"                     # Deep learning frame interpolation (RIFE/IFNet when model present)


class SceneCutAction(str, Enum):
    NEAREST_FALLBACK = "NEAREST_FALLBACK" # Fall back to nearest source frame across scene cuts
    HOLD_PREVIOUS = "HOLD_PREVIOUS"       # Hold previous scene frame until cut boundary


class QualityMode(str, Enum):
    DRAFT = "DRAFT"       # Fast nearest-neighbor / frame duplication for timeline scrub
    STANDARD = "STANDARD" # Frame blend or fast optical flow
    STUDIO = "STUDIO"     # High-density Farneback optical flow with occlusion masking


@dataclass
class RationalFrameRate:
    """Exact rational frame rate representation (e.g. 24000/1001 for 23.976 fps, 30000/1001 for 29.97 fps)."""
    numerator: int
    denominator: int = 1

    @classmethod
    def from_float(cls, fps: float) -> "RationalFrameRate":
        if abs(fps - 23.976) < 0.01:
            return cls(24000, 1001)
        elif abs(fps - 29.97) < 0.01:
            return cls(30000, 1001)
        elif abs(fps - 59.94) < 0.01:
            return cls(60000, 1001)
        else:
            frac = Fraction(fps).limit_denominator(1001)
            return cls(frac.numerator, frac.denominator)

    @property
    def fps(self) -> float:
        return float(self.numerator) / max(1, self.denominator)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "numerator": self.numerator,
            "denominator": self.denominator,
            "fps": round(self.fps, 4),
        }


@dataclass
class FrameRateConversionConfig:
    """Configuration for frame rate conversion, speed ramping synthesis, and intermediate frame generation."""
    method: InterpolationMethod = InterpolationMethod.MOTION_COMPENSATED
    quality_mode: QualityMode = QualityMode.STANDARD

    # Target Rate
    source_rate: RationalFrameRate = field(default_factory=lambda: RationalFrameRate(24, 1))
    target_rate: RationalFrameRate = field(default_factory=lambda: RationalFrameRate(60, 1))

    # Optical Flow & Motion Compensation
    motion_flow_scale: float = 0.5        # Image scale for dense optical flow pyramid [0.25 to 1.0]
    motion_flow_levels: int = 3           # Pyramid levels
    motion_flow_iterations: int = 3       # Optical flow refinement iterations
    motion_confidence_threshold: float = 0.4 # Minimum optical flow confidence before falling back to blend

    # Scene Cut Detection
    detect_scene_cuts: bool = True        # Prevent interpolating across hard cuts
    scene_cut_threshold: float = 35.0     # Mean Absolute Difference (MAD) threshold for cut detection [10.0 to 90.0]
    scene_cut_action: SceneCutAction = SceneCutAction.NEAREST_FALLBACK

    # Model-backed Interpolation Adapter (RIFE / Neural)
    model_path: Optional[str] = None
    use_gpu: bool = False

    is_enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "method": self.method.value,
            "quality_mode": self.quality_mode.value,
            "source_rate": self.source_rate.to_dict(),
            "target_rate": self.target_rate.to_dict(),
            "motion_flow_scale": round(self.motion_flow_scale, 2),
            "motion_flow_levels": self.motion_flow_levels,
            "motion_confidence_threshold": round(self.motion_confidence_threshold, 2),
            "detect_scene_cuts": self.detect_scene_cuts,
            "scene_cut_threshold": round(self.scene_cut_threshold, 2),
            "scene_cut_action": self.scene_cut_action.value,
            "model_path": self.model_path,
            "use_gpu": self.use_gpu,
            "is_enabled": self.is_enabled,
        }


@dataclass
class InterpolationDiagnostics:
    """Operational metrics on intermediate frame synthesis."""
    source_frames_sampled: int
    output_frames_generated: int
    scene_cuts_detected: int
    optical_flow_fallbacks: int
    processing_time_ms: float
    method_used: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_frames_sampled": self.source_frames_sampled,
            "output_frames_generated": self.output_frames_generated,
            "scene_cuts_detected": self.scene_cuts_detected,
            "optical_flow_fallbacks": self.optical_flow_fallbacks,
            "processing_time_ms": round(self.processing_time_ms, 2),
            "method_used": self.method_used,
        }
