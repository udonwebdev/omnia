"""OMNIA Video Studio — Color Grading, Color Management & Look Models (Module 16).

Domain models for non-destructive color grading:
- ColorSpace: Color spaces and transfer characteristics (REC709, REC2020, SRGB, DCI_P3, PQ_ST2084, HLG).
- PrimaryGrade: Exposure, brightness, contrast, pivot, highlights, shadows, white balance (temperature/tint), saturation, vibrance.
- LiftGammaGain: 3-way color wheel balances (lift, gamma, gain, offset) in RGB + master luminance.
- CurvePoint & ColorCurves: Spline/linear interpolated curves for Master RGB, Red, Green, Blue, and Luminance.
- HSLQualifier: Secondary color selection (hue center/width/softness, sat min/max, luma min/max, feather).
- LUTDescriptor: 1D/3D .cube Look-Up Table model with domain and interpolation policy.
- ColorGradeDocument: Complete grade specification per clip, track, or look preset.
- ColorScopeData: Real computed histogram, waveform, vectorscope, and RGB parade measurements.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import math
import time
import uuid

# ==============================================================================
# 1. Color Space & Transfer Functions
# ==============================================================================

class ColorSpace(str, Enum):
    REC709 = "REC709"         # ITU-R BT.709 (SDR Broadcast standard)
    SRGB = "SRGB"             # sRGB standard display space
    REC2020 = "REC2020"       # ITU-R BT.2020 (Wide color gamut)
    DCI_P3 = "DCI_P3"         # Digital Cinema Initiatives P3
    PQ_ST2084 = "PQ_ST2084"   # SMPTE ST 2084 (Perceptual Quantizer HDR)
    HLG = "HLG"               # Hybrid Log-Gamma (ARIB STD-B67 HDR)

class ColorRange(str, Enum):
    FULL = "FULL"             # 0-255 (8-bit) / 0.0-1.0 (float)
    LEGAL = "LEGAL"           # 16-235 (8-bit video range)

class LUTType(str, Enum):
    LUT_1D = "1D"
    LUT_3D = "3D"

# ==============================================================================
# 2. Primary Correction & Lift/Gamma/Gain
# ==============================================================================

@dataclass
class PrimaryGrade:
    """Primary tone and color adjustments."""
    exposure: float = 0.0        # In EV stops (-5.0 to +5.0)
    brightness: float = 0.0      # Offset (-100.0 to +100.0)
    contrast: float = 1.0        # Multiplier (0.0 to 3.0)
    pivot: float = 0.5           # Contrast center pivot (0.0 to 1.0)
    highlights: float = 0.0      # Highlights compression/boost (-100.0 to +100.0)
    shadows: float = 0.0         # Shadows compression/lift (-100.0 to +100.0)
    temperature: float = 0.0     # Cool (blue) to Warm (amber) (-100.0 to +100.0)
    tint: float = 0.0            # Green to Magenta (-100.0 to +100.0)
    saturation: float = 1.0      # Global saturation (0.0 to 3.0)
    vibrance: float = 0.0        # Saturation boost protecting skin tones / saturated areas (-100.0 to +100.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "exposure": self.exposure,
            "brightness": self.brightness,
            "contrast": self.contrast,
            "pivot": self.pivot,
            "highlights": self.highlights,
            "shadows": self.shadows,
            "temperature": self.temperature,
            "tint": self.tint,
            "saturation": self.saturation,
            "vibrance": self.vibrance,
        }

@dataclass
class WheelBalance:
    """Individual color wheel balance (RGB offsets + Master)."""
    r: float = 0.0
    g: float = 0.0
    b: float = 0.0
    master: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {"r": self.r, "g": self.g, "b": self.b, "master": self.master}

@dataclass
class LiftGammaGain:
    """Three-way primary grading wheels (Lift for shadows, Gamma for midtones, Gain for highlights, Offset)."""
    lift: WheelBalance = field(default_factory=WheelBalance)
    gamma: WheelBalance = field(default_factory=WheelBalance)
    gain: WheelBalance = field(default_factory=WheelBalance)
    offset: WheelBalance = field(default_factory=WheelBalance)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lift": self.lift.to_dict(),
            "gamma": self.gamma.to_dict(),
            "gain": self.gain.to_dict(),
            "offset": self.offset.to_dict(),
        }

# ==============================================================================
# 3. Tone Curves & HSL Secondary Qualifier
# ==============================================================================

@dataclass
class CurvePoint:
    x: float  # Input value (0.0 to 1.0)
    y: float  # Output value (0.0 to 1.0)

    def to_dict(self) -> Dict[str, Any]:
        return {"x": self.x, "y": self.y}

@dataclass
class ColorCurves:
    """Parametric spline tone curves for Master RGB, Red, Green, and Blue."""
    master: List[CurvePoint] = field(default_factory=lambda: [CurvePoint(0.0, 0.0), CurvePoint(1.0, 1.0)])
    red: List[CurvePoint] = field(default_factory=lambda: [CurvePoint(0.0, 0.0), CurvePoint(1.0, 1.0)])
    green: List[CurvePoint] = field(default_factory=lambda: [CurvePoint(0.0, 0.0), CurvePoint(1.0, 1.0)])
    blue: List[CurvePoint] = field(default_factory=lambda: [CurvePoint(0.0, 0.0), CurvePoint(1.0, 1.0)])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "master": [p.to_dict() for p in self.master],
            "red": [p.to_dict() for p in self.red],
            "green": [p.to_dict() for p in self.green],
            "blue": [p.to_dict() for p in self.blue],
        }

@dataclass
class HSLQualifier:
    """Secondary color qualification mask based on Hue, Saturation, and Luminance."""
    is_enabled: bool = False
    hue_center: float = 0.0      # 0.0 to 360.0 degrees
    hue_width: float = 30.0      # Width of hue window
    hue_softness: float = 10.0   # Feathering angle on boundaries
    sat_min: float = 0.1         # Minimum saturation (0.0 to 1.0)
    sat_max: float = 1.0         # Maximum saturation (0.0 to 1.0)
    luma_min: float = 0.0        # Minimum luminance (0.0 to 1.0)
    luma_max: float = 1.0        # Maximum luminance (0.0 to 1.0)
    feather_radius: int = 0      # Spatial blur / feathering radius
    # Targeted corrections applied exclusively to qualified pixels:
    target_hue_shift: float = 0.0   # Degrees shift (-180.0 to +180.0)
    target_sat_scale: float = 1.0   # Saturation scaling factor
    target_luma_offset: float = 0.0 # Luminance offset

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_enabled": self.is_enabled,
            "hue_center": self.hue_center,
            "hue_width": self.hue_width,
            "hue_softness": self.hue_softness,
            "sat_min": self.sat_min,
            "sat_max": self.sat_max,
            "luma_min": self.luma_min,
            "luma_max": self.luma_max,
            "feather_radius": self.feather_radius,
            "target_hue_shift": self.target_hue_shift,
            "target_sat_scale": self.target_sat_scale,
            "target_luma_offset": self.target_luma_offset,
        }

# ==============================================================================
# 4. LUT Descriptor & Complete Grade Document
# ==============================================================================

@dataclass
class LUTDescriptor:
    lut_id: str
    name: str
    lut_type: LUTType = LUTType.LUT_3D
    size: int = 33              # Grid size (e.g. 17, 33, 65 for 3D; 1024 for 1D)
    intensity: float = 1.0      # 0.0 to 1.0 blend factor
    is_enabled: bool = True
    data: Optional[Any] = None  # NumPy table (size, size, size, 3) or (size, 3)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lut_id": self.lut_id,
            "name": self.name,
            "lut_type": self.lut_type.value,
            "size": self.size,
            "intensity": self.intensity,
            "is_enabled": self.is_enabled,
        }

@dataclass
class ColorGradeDocument:
    """Canonical non-destructive color grade specification."""
    grade_id: str
    name: str = "Grade"
    source_color_space: ColorSpace = ColorSpace.REC709
    working_color_space: ColorSpace = ColorSpace.REC709
    primary: PrimaryGrade = field(default_factory=PrimaryGrade)
    wheels: LiftGammaGain = field(default_factory=LiftGammaGain)
    curves: ColorCurves = field(default_factory=ColorCurves)
    hsl_qualifier: HSLQualifier = field(default_factory=HSLQualifier)
    lut: Optional[LUTDescriptor] = None
    is_enabled: bool = True
    version: int = 1
    revision: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "grade_id": self.grade_id,
            "name": self.name,
            "source_color_space": self.source_color_space.value,
            "working_color_space": self.working_color_space.value,
            "primary": self.primary.to_dict(),
            "wheels": self.wheels.to_dict(),
            "curves": self.curves.to_dict(),
            "hsl_qualifier": self.hsl_qualifier.to_dict(),
            "lut": self.lut.to_dict() if self.lut else None,
            "is_enabled": self.is_enabled,
            "version": self.version,
            "revision": self.revision,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

# ==============================================================================
# 5. Color Scopes Data Structures
# ==============================================================================

@dataclass
class ColorScopeData:
    """Statistical measurement derived from real decoded frame pixel data."""
    frame_timestamp: float
    histogram_r: List[int]        # 256-bin histogram
    histogram_g: List[int]
    histogram_b: List[int]
    histogram_luma: List[int]
    waveform_samples: List[float] # Sub-sampled column luma envelope [min, max, mean]
    vectorscope_uv: List[Tuple[float, float]] # Sub-sampled (U, V) or (Cb, Cr) chrominance points
    rgb_parade: Dict[str, List[float]] # Channel column profiles
