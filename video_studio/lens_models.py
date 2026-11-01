"""OMNIA Video Studio — Lens Distortion, Optical Correction & Lens Profile Models (Module 30).

Defines serialization models, enums, parameters, and diagnostics for:
- Radial (k1, k2, k3) and tangential (p1, p2) lens distortion models (Brown-Conrady).
- Optical center / principal point offsets (cx, cy) and normalized focal length.
- Lateral chromatic aberration correction (radial red/blue channel scaling).
- Optical vignetting correction with radial falloff cosine/polynomial modeling.
- Curated, verified lens profile library and metadata matching (focal length, sensor size).
- Framing and border policies (crop, clamp, transparent, replicate).
- Keyframe and transform pipeline integration.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
import uuid
import time


class LensModelType(str, Enum):
    """Mathematical lens distortion modeling convention."""
    BROWN_CONRADY = "BROWN_CONRADY"   # Standard radial (k1, k2, k3) + tangential (p1, p2)
    RADIAL_POLYNOMIAL = "RADIAL_POLYNOMIAL" # Pure radial polynomial (k1, k2)
    FISHEYE_EQUIDISTANT = "FISHEYE_EQUIDISTANT" # Extreme wide-angle / action-cam fisheye


class BorderHandlingMode(str, Enum):
    """Behavior for sampling out-of-bounds pixels during inverse warping."""
    TRANSPARENT = "TRANSPARENT"       # Clear transparent black (0, 0, 0, 0)
    CLAMP_EDGE = "CLAMP_EDGE"         # Clamp to closest edge pixel (BORDER_REPLICATE)
    REFLECT = "REFLECT"               # Mirror at boundaries (BORDER_REFLECT)
    CROP_TO_VALID = "CROP_TO_VALID"   # Uniform zoom/crop to avoid any unmapped black borders


class ProfileMatchBasis(str, Enum):
    """Proven basis for lens profile calibration matching."""
    EXACT_METADATA = "EXACT_METADATA" # Exact camera make, model, and focal length match
    FOCAL_LENGTH = "FOCAL_LENGTH"     # Matched by calibrated focal length and sensor crop
    MANUAL_USER = "MANUAL_USER"       # User manually selected profile
    NO_MATCH = "NO_MATCH"             # No profile match; using custom manual parameters


@dataclass
class LensProfile:
    """Optical calibration profile from laboratory or lens manufacturer specifications."""
    profile_id: str
    name: str
    manufacturer: str = ""
    lens_model: str = ""
    camera_model: str = ""
    focal_length_mm: float = 24.0
    sensor_format: str = "Full Frame 35mm" # e.g., Full Frame, APS-C, Micro Four Thirds
    crop_factor: float = 1.0

    # Brown-Conrady Distortion Coefficients
    k1: float = 0.0                    # Primary radial distortion (barrel < 0, pincushion > 0)
    k2: float = 0.0                    # Secondary radial distortion
    k3: float = 0.0                    # Tertiary radial distortion
    p1: float = 0.0                    # Tangential distortion x
    p2: float = 0.0                    # Tangential distortion y

    # Optical Center Offset (normalized relative to image center (0.0, 0.0))
    center_offset_x: float = 0.0       # [-0.2, 0.2]
    center_offset_y: float = 0.0       # [-0.2, 0.2]

    # Chromatic Aberration calibration (lateral displacement factor for Red and Blue relative to Green)
    ca_red_scale: float = 0.0          # [-0.05, 0.05]
    ca_blue_scale: float = 0.0         # [-0.05, 0.05]

    # Vignetting calibration
    vignette_v1: float = 0.0           # Cosine / radial falloff coefficient
    vignette_v2: float = 0.0           # Corner falloff coefficient

    provenance: str = "OMNIA Lab Calibration v1.0"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "name": self.name,
            "manufacturer": self.manufacturer,
            "lens_model": self.lens_model,
            "camera_model": self.camera_model,
            "focal_length_mm": self.focal_length_mm,
            "sensor_format": self.sensor_format,
            "crop_factor": self.crop_factor,
            "k1": self.k1,
            "k2": self.k2,
            "k3": self.k3,
            "p1": self.p1,
            "p2": self.p2,
            "center_offset_x": self.center_offset_x,
            "center_offset_y": self.center_offset_y,
            "ca_red_scale": self.ca_red_scale,
            "ca_blue_scale": self.ca_blue_scale,
            "vignette_v1": self.vignette_v1,
            "vignette_v2": self.vignette_v2,
            "provenance": self.provenance,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LensProfile":
        return cls(
            profile_id=d.get("profile_id", "custom"),
            name=d.get("name", "Custom Profile"),
            manufacturer=d.get("manufacturer", ""),
            lens_model=d.get("lens_model", ""),
            camera_model=d.get("camera_model", ""),
            focal_length_mm=float(d.get("focal_length_mm", 24.0)),
            sensor_format=d.get("sensor_format", "Full Frame 35mm"),
            crop_factor=float(d.get("crop_factor", 1.0)),
            k1=float(d.get("k1", 0.0)),
            k2=float(d.get("k2", 0.0)),
            k3=float(d.get("k3", 0.0)),
            p1=float(d.get("p1", 0.0)),
            p2=float(d.get("p2", 0.0)),
            center_offset_x=float(d.get("center_offset_x", 0.0)),
            center_offset_y=float(d.get("center_offset_y", 0.0)),
            ca_red_scale=float(d.get("ca_red_scale", 0.0)),
            ca_blue_scale=float(d.get("ca_blue_scale", 0.0)),
            vignette_v1=float(d.get("vignette_v1", 0.0)),
            vignette_v2=float(d.get("vignette_v2", 0.0)),
            provenance=d.get("provenance", "OMNIA Custom"),
        )


@dataclass
class LensCorrectionConfig:
    """Active lens correction settings for a clip or rendering pipeline."""
    config_id: str = field(default_factory=lambda: f"lens_cfg_{uuid.uuid4().hex[:8]}")
    clip_id: str = ""
    is_enabled: bool = True
    model_type: LensModelType = LensModelType.BROWN_CONRADY

    # Overall correction strength multiplier [0.0 to 2.0]
    strength: float = 1.0

    # Geometric distortion coefficients
    k1: float = 0.0                    # Barrel (<0) or Pincushion (>0)
    k2: float = 0.0
    k3: float = 0.0
    p1: float = 0.0                    # Tangential decentering
    p2: float = 0.0

    # Optical center shift (normalized 0.0 to 1.0; default (0.5, 0.5))
    center_x: float = 0.5
    center_y: float = 0.5

    # Lateral Chromatic Aberration (CA)
    enable_ca_correction: bool = False
    ca_red_displacement: float = 0.0   # Radial percentage shift for Red channel [-5.0% to 5.0%]
    ca_blue_displacement: float = 0.0  # Radial percentage shift for Blue channel [-5.0% to 5.0%]

    # Optical Vignetting Correction
    enable_vignette_correction: bool = False
    vignette_gain: float = 0.0         # Exposure gain compensation at corners [0.0 to 3.0]
    vignette_midpoint: float = 0.5     # Falloff curve curvature [0.1 to 0.9]

    # Border & Framing Policy
    border_mode: BorderHandlingMode = BorderHandlingMode.CLAMP_EDGE
    auto_crop_scale: float = 1.0       # Additional zoom to fill frame if CROP_TO_VALID

    # Lens Profile Linkage
    profile_id: Optional[str] = None
    profile_match_basis: ProfileMatchBasis = ProfileMatchBasis.NO_MATCH
    match_confidence: float = 0.0

    revision: int = 1
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "config_id": self.config_id,
            "clip_id": self.clip_id,
            "is_enabled": self.is_enabled,
            "model_type": self.model_type.value,
            "strength": self.strength,
            "k1": self.k1,
            "k2": self.k2,
            "k3": self.k3,
            "p1": self.p1,
            "p2": self.p2,
            "center_x": self.center_x,
            "center_y": self.center_y,
            "enable_ca_correction": self.enable_ca_correction,
            "ca_red_displacement": self.ca_red_displacement,
            "ca_blue_displacement": self.ca_blue_displacement,
            "enable_vignette_correction": self.enable_vignette_correction,
            "vignette_gain": self.vignette_gain,
            "vignette_midpoint": self.vignette_midpoint,
            "border_mode": self.border_mode.value,
            "auto_crop_scale": self.auto_crop_scale,
            "profile_id": self.profile_id,
            "profile_match_basis": self.profile_match_basis.value,
            "match_confidence": self.match_confidence,
            "revision": self.revision,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LensCorrectionConfig":
        return cls(
            config_id=d.get("config_id", f"lens_cfg_{uuid.uuid4().hex[:8]}"),
            clip_id=d.get("clip_id", ""),
            is_enabled=bool(d.get("is_enabled", True)),
            model_type=LensModelType(d.get("model_type", LensModelType.BROWN_CONRADY.value)),
            strength=float(d.get("strength", 1.0)),
            k1=float(d.get("k1", 0.0)),
            k2=float(d.get("k2", 0.0)),
            k3=float(d.get("k3", 0.0)),
            p1=float(d.get("p1", 0.0)),
            p2=float(d.get("p2", 0.0)),
            center_x=float(d.get("center_x", 0.5)),
            center_y=float(d.get("center_y", 0.5)),
            enable_ca_correction=bool(d.get("enable_ca_correction", False)),
            ca_red_displacement=float(d.get("ca_red_displacement", 0.0)),
            ca_blue_displacement=float(d.get("ca_blue_displacement", 0.0)),
            enable_vignette_correction=bool(d.get("enable_vignette_correction", False)),
            vignette_gain=float(d.get("vignette_gain", 0.0)),
            vignette_midpoint=float(d.get("vignette_midpoint", 0.5)),
            border_mode=BorderHandlingMode(d.get("border_mode", BorderHandlingMode.CLAMP_EDGE.value)),
            auto_crop_scale=float(d.get("auto_crop_scale", 1.0)),
            profile_id=d.get("profile_id"),
            profile_match_basis=ProfileMatchBasis(d.get("profile_match_basis", ProfileMatchBasis.NO_MATCH.value)),
            match_confidence=float(d.get("match_confidence", 0.0)),
            revision=int(d.get("revision", 1)),
            updated_at=float(d.get("updated_at", time.time())),
        )


@dataclass
class LensDiagnostics:
    """Real-time processing diagnostics for optical lens correction."""
    clip_id: str = ""
    frame_number: int = 0
    processing_time_ms: float = 0.0
    distortion_applied: bool = False
    ca_corrected: bool = False
    vignette_corrected: bool = False
    max_displacement_pixels: float = 0.0
    unmapped_border_pixels_pct: float = 0.0
    status: str = "SUCCESS"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "clip_id": self.clip_id,
            "frame_number": self.frame_number,
            "processing_time_ms": round(self.processing_time_ms, 3),
            "distortion_applied": self.distortion_applied,
            "ca_corrected": self.ca_corrected,
            "vignette_corrected": self.vignette_corrected,
            "max_displacement_pixels": round(self.max_displacement_pixels, 2),
            "unmapped_border_pixels_pct": round(self.unmapped_border_pixels_pct, 2),
            "status": self.status,
        }
