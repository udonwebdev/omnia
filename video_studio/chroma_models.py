"""OMNIA Video Studio — Green Screen, Chroma Keying & Advanced Matte Extraction Models (Module 23).

Defines authoritative domain models for:
- ChromaColorSpace: LAB, YCBCR, HSV, RGB (perceptually weighted or Euclidean).
- ChromaKeyType: GREEN_SCREEN, BLUE_SCREEN, CUSTOM_COLOR.
- MatteDisplayMode: COMPOSITE, MATTE_ONLY, FOREGROUND_KEYED, ORIGINAL, SPILL_ONLY.
- KeyColorSample: RGB color tuple with weight and label.
- ChromaKeyParameters: Tolerance, softness, threshold, choke, feather, erode, dilate,
  spill suppression strength/color/threshold, invert, and preview display mode.
- ChromaKeyResult: Result of keying operation containing matte array, processed frame, and diagnostics.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import numpy as np


class ChromaColorSpace(str, Enum):
    LAB = "LAB"          # CIE L*a*b* perceptual color distance (ideal for delta-E chroma separation)
    YCBCR = "YCBCR"      # YCbCr broadcast chroma distance
    HSV = "HSV"          # Hue-Saturation angular/radial distance
    RGB = "RGB"          # Weighted Euclidean RGB distance


class ChromaKeyType(str, Enum):
    GREEN_SCREEN = "GREEN_SCREEN" # Standard pure green #00FF00
    BLUE_SCREEN = "BLUE_SCREEN"   # Standard pure blue #0000FF
    CUSTOM_COLOR = "CUSTOM_COLOR" # User sampled key color


class MatteDisplayMode(str, Enum):
    COMPOSITE = "COMPOSITE"              # Keyed FG composited over BG or checkerboard
    MATTE_ONLY = "MATTE_ONLY"            # Grayscale alpha matte visualization
    FOREGROUND_KEYED = "FOREGROUND_KEYED"# Cutout foreground with transparency
    ORIGINAL = "ORIGINAL"                # Unmodified source frame
    SPILL_ONLY = "SPILL_ONLY"            # Visualizing suppressed spill regions


@dataclass
class KeyColorSample:
    """Individual color sample picked from footage (r, g, b in [0, 255])."""
    r: int
    g: int
    b: int
    weight: float = 1.0
    label: str = "Primary"

    def to_rgb_tuple(self) -> Tuple[int, int, int]:
        return (int(self.r), int(self.g), int(self.b))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "r": self.r,
            "g": self.g,
            "b": self.b,
            "weight": round(self.weight, 2),
            "label": self.label,
        }


@dataclass
class ChromaKeyConfig:
    """Configuration and processing parameters for Chroma Keying & Matte Extraction."""
    key_type: ChromaKeyType = ChromaKeyType.GREEN_SCREEN
    color_space: ChromaColorSpace = ChromaColorSpace.LAB
    key_samples: List[KeyColorSample] = field(default_factory=lambda: [KeyColorSample(r=0, g=255, b=0)])

    # Key Extraction
    tolerance: float = 40.0         # Acceptance distance radius around key color [1.0, 150.0]
    softness: float = 20.0          # Falloff softness gradient range [0.0, 100.0]
    matte_threshold_low: float = 0.0# Black point clip [0.0, 1.0]
    matte_threshold_high: float = 1.0 # White point clip [0.0, 1.0]

    # Edge Refinement
    feather_radius: int = 0         # Gaussian edge feather radius [0 to 30]
    choke: int = 0                  # Morphological erosion/dilation (-20 to 20; neg=choke/erode, pos=expand/dilate)
    edge_contrast: float = 1.0      # S-curve edge contrast multiplier [0.5, 3.0]
    invert_matte: bool = False      # Invert alpha matte (keep screen, remove subject)

    # Spill Suppression
    spill_suppression: bool = True  # Enable spill suppression
    spill_strength: float = 0.8     # Desaturation / neutralization intensity [0.0, 1.0]
    spill_threshold: float = 0.1    # Sensitivity threshold for green/blue tint [0.0, 1.0]
    spill_replace_color: Optional[Tuple[int, int, int]] = None # None = desaturate/neutralize, or RGB tint

    # Matte Cleanup
    cleanup_holes_radius: int = 0   # Morphological close/hole filling radius [0, 10]
    cleanup_spots_radius: int = 0   # Morphological open/dust removal radius [0, 10]

    # Display & Integration
    display_mode: MatteDisplayMode = MatteDisplayMode.COMPOSITE
    is_enabled: bool = True

    def get_primary_color(self) -> Tuple[int, int, int]:
        if self.key_samples:
            return self.key_samples[0].to_rgb_tuple()
        if self.key_type == ChromaKeyType.BLUE_SCREEN:
            return (0, 0, 255)
        return (0, 255, 0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key_type": self.key_type.value,
            "color_space": self.color_space.value,
            "key_samples": [s.to_dict() for s in self.key_samples],
            "tolerance": round(self.tolerance, 2),
            "softness": round(self.softness, 2),
            "matte_threshold_low": round(self.matte_threshold_low, 3),
            "matte_threshold_high": round(self.matte_threshold_high, 3),
            "feather_radius": self.feather_radius,
            "choke": self.choke,
            "edge_contrast": round(self.edge_contrast, 2),
            "invert_matte": self.invert_matte,
            "spill_suppression": self.spill_suppression,
            "spill_strength": round(self.spill_strength, 2),
            "spill_threshold": round(self.spill_threshold, 2),
            "spill_replace_color": list(self.spill_replace_color) if self.spill_replace_color else None,
            "cleanup_holes_radius": self.cleanup_holes_radius,
            "cleanup_spots_radius": self.cleanup_spots_radius,
            "display_mode": self.display_mode.value,
            "is_enabled": self.is_enabled,
        }
