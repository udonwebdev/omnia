"""OMNIA Video Studio — Video Denoising, Noise Reduction & Image Restoration Models (Module 25).

Defines authoritative domain models for:
- DenoiseMethod: BILATERAL_SPATIAL, FAST_NL_MEANS, GUIDED_FILTER, TEMPORAL_ACCUMULATION.
- DenoiseQualityMode: FAST, BALANCED, HIGH_QUALITY.
- DenoiseChannelScope: LUMA_AND_CHROMA, LUMA_ONLY, CHROMA_ONLY.
- RestorationOptions: Dead pixel correction, deblocking, post-sharpening (unsharp mask), dithering.
- DenoiseConfig: Complete serializable parameter configuration.
- DenoiseDiagnostics: Metrics on noise reduction (MSE, PSNR estimation, processing time).
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple


class DenoiseMethod(str, Enum):
    BILATERAL_SPATIAL = "BILATERAL_SPATIAL"   # Edge-preserving spatial bilateral filtering
    FAST_NL_MEANS = "FAST_NL_MEANS"           # Fast Non-Local Means spatial denoising
    GUIDED_FILTER = "GUIDED_FILTER"           # Edge-preserving guided filtering
    TEMPORAL_ACCUMULATION = "TEMPORAL_ACCUMULATION" # Temporal multi-frame recursive/weighted accumulation


class DenoiseQualityMode(str, Enum):
    FAST = "FAST"           # Optimized kernel radius for responsive playback
    BALANCED = "BALANCED"   # Balanced noise reduction and edge retention
    HIGH_QUALITY = "HIGH_QUALITY" # Deeper non-local search or multi-pass restoration


class DenoiseChannelScope(str, Enum):
    LUMA_AND_CHROMA = "LUMA_AND_CHROMA" # Separate processing of luminance and color grain
    LUMA_ONLY = "LUMA_ONLY"             # Filter luminance grain, preserve original chroma
    CHROMA_ONLY = "CHROMA_ONLY"         # Clean color blotchiness / chroma noise only


@dataclass
class DenoiseConfig:
    """Configuration for spatial/temporal video denoising and image restoration."""
    method: DenoiseMethod = DenoiseMethod.BILATERAL_SPATIAL
    quality_mode: DenoiseQualityMode = DenoiseQualityMode.BALANCED
    channel_scope: DenoiseChannelScope = DenoiseChannelScope.LUMA_AND_CHROMA

    # Spatial Parameters
    strength: float = 15.0              # Primary filtering strength [1.0 to 100.0]
    luma_strength: float = 15.0         # Luminance filtering strength [1.0 to 100.0]
    chroma_strength: float = 15.0       # Chrominance filtering strength [1.0 to 100.0]
    spatial_radius: int = 5             # Pixel search/filter radius [1 to 15]
    edge_preservation: float = 0.75     # Edge threshold sensitivity [0.1 to 1.0]

    # Temporal Parameters
    temporal_enabled: bool = False      # Enable multi-frame temporal noise reduction
    temporal_frames: int = 3            # Number of adjacent frames in temporal window (1 to 5)
    temporal_threshold: float = 25.0    # Motion/difference cutoff to prevent ghosting [5.0 to 80.0]
    temporal_blend_weight: float = 0.35 # Temporal accumulation weight [0.05 to 0.75]

    # Restoration & Artifact Mitigation
    dead_pixel_correction: bool = False # Remove single-pixel hot/dead sensor defects
    dead_pixel_threshold: float = 40.0  # Threshold difference from 8-neighborhood median
    deblocking_strength: float = 0.0    # Mild block boundary smoothing [0.0 to 1.0]
    post_sharpening: float = 0.0        # Unsharp mask post-denoise detail recovery [0.0 to 1.0]
    add_dither: bool = False            # Sub-perceptual dither to prevent banding

    is_enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "method": self.method.value,
            "quality_mode": self.quality_mode.value,
            "channel_scope": self.channel_scope.value,
            "strength": round(self.strength, 2),
            "luma_strength": round(self.luma_strength, 2),
            "chroma_strength": round(self.chroma_strength, 2),
            "spatial_radius": self.spatial_radius,
            "edge_preservation": round(self.edge_preservation, 3),
            "temporal_enabled": self.temporal_enabled,
            "temporal_frames": self.temporal_frames,
            "temporal_threshold": round(self.temporal_threshold, 2),
            "temporal_blend_weight": round(self.temporal_blend_weight, 3),
            "dead_pixel_correction": self.dead_pixel_correction,
            "dead_pixel_threshold": round(self.dead_pixel_threshold, 2),
            "deblocking_strength": round(self.deblocking_strength, 2),
            "post_sharpening": round(self.post_sharpening, 2),
            "add_dither": self.add_dither,
            "is_enabled": self.is_enabled,
        }


@dataclass
class DenoiseDiagnostics:
    """Performance and numerical metrics for a denoising execution."""
    processing_time_ms: float
    psnr_gain_db: Optional[float] = None
    mse_reduction: Optional[float] = None
    temporal_frames_used: int = 1
    method_used: str = "BILATERAL_SPATIAL"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "processing_time_ms": round(self.processing_time_ms, 2),
            "psnr_gain_db": round(self.psnr_gain_db, 2) if self.psnr_gain_db is not None else None,
            "mse_reduction": round(self.mse_reduction, 4) if self.mse_reduction is not None else None,
            "temporal_frames_used": self.temporal_frames_used,
            "method_used": self.method_used,
        }
