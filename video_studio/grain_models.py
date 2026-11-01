"""OMNIA Video Studio — Film Grain, Video Texture & Analog Emulation Models (Module 31).

Defines serialization models, enums, parameters, and diagnostics for:
- Deterministic procedural film grain generation (Gaussian / Uniform / Perlin-like coarse).
- Fine vs. coarse spatial grain scaling.
- Independent Luma and Chroma (color noise) weighting in Rec.709 color space.
- Tonal weighting across Shadows, Midtones, and Highlights.
- Temporal grain behavior: FIXED, FRAME_VARYING, and TEMPORALLY_COHERENT.
- Analog-inspired texture operations:
  * Subtle gate weave / film jitter (subpixel vertical/horizontal translation)
  * Halation highlight glow (diffuse reddish bloom around high-contrast specular borders)
  * Procedural dust and hairline emulsion scratches
- Provenance-tracked analog emulation presets.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
import uuid
import time


class GrainType(str, Enum):
    """Statistical distribution and morphology for generated grain."""
    GAUSSIAN = "GAUSSIAN"             # Standard normal distribution (natural silver halide)
    COARSE = "COARSE"                 # Downscaled / clustered optical film grain (16mm/8mm aesthetic)
    FINE = "FINE"                     # High-frequency micro-grain (35mm low ISO aesthetic)
    ORGANIC = "ORGANIC"               # Multi-octave structured grain pattern


class TemporalGrainMode(str, Enum):
    """Temporal evolution and animated behavior across video frames."""
    FRAME_VARYING = "FRAME_VARYING"   # Traditional film: unique random distribution each frame
    FIXED = "FIXED"                   # Static frozen grain pattern (for freeze-frames or stylized stills)
    TEMPORALLY_COHERENT = "TEMPORALLY_COHERENT" # Smooth temporal blend across adjacent frames


class HalationMode(str, Enum):
    """Optical emulsion halation glow behavior."""
    OFF = "OFF"
    RED_ORANGE = "RED_ORANGE"         # Authentic anti-halation layer absorption glow
    DIFFUSE_WHITE = "DIFFUSE_WHITE"   # General specular flare / bloom


@dataclass
class AnalogTextureConfig:
    """Configures optional physical analog film artifacts."""
    # Gate Weave: Subtle frame translation / jitter
    enable_gate_weave: bool = False
    weave_amplitude_x: float = 0.0     # Horizontal jitter in pixels [-5.0, 5.0]
    weave_amplitude_y: float = 0.0     # Vertical jitter in pixels [-5.0, 5.0]
    weave_frequency: float = 1.0       # Cycle frequency per frame

    # Halation: Highlight red/warm bloom on bright edges
    halation_mode: HalationMode = HalationMode.OFF
    halation_threshold: float = 0.85   # Luminance threshold for specular highlights [0.5, 1.0]
    halation_intensity: float = 0.4    # Glow intensity [0.0, 1.0]
    halation_radius: float = 12.0      # Blur spread radius in pixels [2.0, 50.0]

    # Procedural Dust & Hairline Scratches
    enable_film_wear: bool = False
    dust_density: float = 0.0002       # Probability of dust speck per pixel [0.0, 0.005]
    scratch_intensity: float = 0.0     # Intensity of vertical hairline scratches [0.0, 1.0]
    scratch_count: int = 0             # Number of simultaneous vertical scratch tracks [0, 5]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enable_gate_weave": self.enable_gate_weave,
            "weave_amplitude_x": self.weave_amplitude_x,
            "weave_amplitude_y": self.weave_amplitude_y,
            "weave_frequency": self.weave_frequency,
            "halation_mode": self.halation_mode.value,
            "halation_threshold": self.halation_threshold,
            "halation_intensity": self.halation_intensity,
            "halation_radius": self.halation_radius,
            "enable_film_wear": self.enable_film_wear,
            "dust_density": self.dust_density,
            "scratch_intensity": self.scratch_intensity,
            "scratch_count": self.scratch_count,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AnalogTextureConfig":
        return cls(
            enable_gate_weave=bool(d.get("enable_gate_weave", False)),
            weave_amplitude_x=float(d.get("weave_amplitude_x", 0.0)),
            weave_amplitude_y=float(d.get("weave_amplitude_y", 0.0)),
            weave_frequency=float(d.get("weave_frequency", 1.0)),
            halation_mode=HalationMode(d.get("halation_mode", HalationMode.OFF.value)),
            halation_threshold=float(d.get("halation_threshold", 0.85)),
            halation_intensity=float(d.get("halation_intensity", 0.4)),
            halation_radius=float(d.get("halation_radius", 12.0)),
            enable_film_wear=bool(d.get("enable_film_wear", False)),
            dust_density=float(d.get("dust_density", 0.0002)),
            scratch_intensity=float(d.get("scratch_intensity", 0.0)),
            scratch_count=int(d.get("scratch_count", 0)),
        )


@dataclass
class FilmGrainConfig:
    """Primary configuration for film grain and analog texture generation."""
    config_id: str = field(default_factory=lambda: f"grain_cfg_{uuid.uuid4().hex[:8]}")
    clip_id: str = ""
    is_enabled: bool = True

    # Grain Characteristics
    grain_type: GrainType = GrainType.GAUSSIAN
    intensity: float = 0.25            # Overall grain intensity [0.0, 1.0]
    scale: float = 1.0                 # Spatial size multiplier [0.5, 4.0] (1.0 = 1:1 pixel grain)

    # Color & Channel Weighting
    luma_weight: float = 1.0           # Contribution to brightness / luma [0.0, 1.0]
    chroma_weight: float = 0.25        # Contribution to color channels / color grain [0.0, 1.0]

    # Tonal Curve Response (photochemical density curve)
    shadow_weight: float = 0.85        # Grain visibility in shadows [0.0, 1.0]
    midtone_weight: float = 1.0        # Grain visibility in midtones [0.0, 1.0]
    highlight_weight: float = 0.35     # Grain visibility in highlights (silver halide clumps drop in D-max) [0.0, 1.0]

    # Temporal & Seed Settings
    temporal_mode: TemporalGrainMode = TemporalGrainMode.FRAME_VARYING
    base_seed: int = 1337              # Deterministic PRNG seed
    coherence_factor: float = 0.4      # Temporal IIR blend factor if TEMPORALLY_COHERENT [0.0, 0.9]

    # Optional Analog Texture Subsystem
    texture: AnalogTextureConfig = field(default_factory=AnalogTextureConfig)

    # Preset Tracking
    preset_name: Optional[str] = None
    provenance: str = "OMNIA Procedural Texture Engine"

    revision: int = 1
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "config_id": self.config_id,
            "clip_id": self.clip_id,
            "is_enabled": self.is_enabled,
            "grain_type": self.grain_type.value,
            "intensity": self.intensity,
            "scale": self.scale,
            "luma_weight": self.luma_weight,
            "chroma_weight": self.chroma_weight,
            "shadow_weight": self.shadow_weight,
            "midtone_weight": self.midtone_weight,
            "highlight_weight": self.highlight_weight,
            "temporal_mode": self.temporal_mode.value,
            "base_seed": self.base_seed,
            "coherence_factor": self.coherence_factor,
            "texture": self.texture.to_dict(),
            "preset_name": self.preset_name,
            "provenance": self.provenance,
            "revision": self.revision,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FilmGrainConfig":
        return cls(
            config_id=d.get("config_id", f"grain_cfg_{uuid.uuid4().hex[:8]}"),
            clip_id=d.get("clip_id", ""),
            is_enabled=bool(d.get("is_enabled", True)),
            grain_type=GrainType(d.get("grain_type", GrainType.GAUSSIAN.value)),
            intensity=float(d.get("intensity", 0.25)),
            scale=float(d.get("scale", 1.0)),
            luma_weight=float(d.get("luma_weight", 1.0)),
            chroma_weight=float(d.get("chroma_weight", 0.25)),
            shadow_weight=float(d.get("shadow_weight", 0.85)),
            midtone_weight=float(d.get("midtone_weight", 1.0)),
            highlight_weight=float(d.get("highlight_weight", 0.35)),
            temporal_mode=TemporalGrainMode(d.get("temporal_mode", TemporalGrainMode.FRAME_VARYING.value)),
            base_seed=int(d.get("base_seed", 1337)),
            coherence_factor=float(d.get("coherence_factor", 0.4)),
            texture=AnalogTextureConfig.from_dict(d.get("texture", {})),
            preset_name=d.get("preset_name"),
            provenance=d.get("provenance", "OMNIA Procedural Texture Engine"),
            revision=int(d.get("revision", 1)),
            updated_at=float(d.get("updated_at", time.time())),
        )


@dataclass
class GrainDiagnostics:
    """Processing diagnostics and telemetry for video grain and texture synthesis."""
    clip_id: str = ""
    frame_number: int = 0
    processing_time_ms: float = 0.0
    effective_seed: int = 0
    grain_applied: bool = False
    gate_weave_applied: bool = False
    halation_applied: bool = False
    film_wear_applied: bool = False
    status: str = "SUCCESS"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "clip_id": self.clip_id,
            "frame_number": self.frame_number,
            "processing_time_ms": round(self.processing_time_ms, 3),
            "effective_seed": self.effective_seed,
            "grain_applied": self.grain_applied,
            "gate_weave_applied": self.gate_weave_applied,
            "halation_applied": self.halation_applied,
            "film_wear_applied": self.film_wear_applied,
            "status": self.status,
        }
