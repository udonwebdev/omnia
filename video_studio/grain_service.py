"""OMNIA Video Studio — Film Grain & Video Texture Service (Module 31).

Coordinates:
- Clip-level FilmGrainConfig lifecycle, versioning, and undo/redo stacks.
- Curated procedural presets with descriptive, non-copyrighted names:
  * 35mm Fine Cinema (subtle clean silver grain, minimal color noise)
  * 16mm Vintage Indie (prominent coarse grain clusters, organic halation)
  * 8mm Retro Home Movie (heavy grain, gate weave, dust specks & hairlines)
  * Noir Monochrome High-Contrast (coarse monochromatic luma-only grain)
  * Modern Digital Noise (ultra-fine subtle digital sensor texture)
- Integration with Module 8 (AnimationService) for keyframing grain intensity, scale, and weighting.
- Capability registration in VideoStudioCapabilityRegistry under VideoStudioCategory.MOTION / VideoStudioCategory.COLOR.
"""

from typing import Dict, Any, List, Optional, Tuple
import logging
import copy
import time
import numpy as np

from video_studio.grain_models import (
    FilmGrainConfig,
    GrainType,
    TemporalGrainMode,
    HalationMode,
    AnalogTextureConfig,
    GrainDiagnostics,
)
from video_studio.grain_engine import video_grain_engine, VideoGrainEngine
from video_studio.effects_models import VideoFrameBuffer
from video_studio.animation_service import AnimationService
from video_studio.registry import video_studio_capability_registry
from video_studio.registry_models import (
    VideoStudioCategory,
    ImplementationState,
    VideoStudioCapabilityDescriptor,
)

logger = logging.getLogger("omnia.video_studio.grain_service")


class VideoGrainService:
    """Central service managing video film grain, analog texture presets, and capability lifecycle."""

    def __init__(
        self,
        engine: Optional[VideoGrainEngine] = None,
        animation_service: Optional[AnimationService] = None,
    ):
        self.engine = engine or video_grain_engine
        self.animation_service = animation_service
        self._configs: Dict[str, FilmGrainConfig] = {} # clip_id -> FilmGrainConfig
        self._presets: Dict[str, FilmGrainConfig] = {} # preset_name -> FilmGrainConfig
        self._undo_stacks: Dict[str, List[FilmGrainConfig]] = {}
        self._redo_stacks: Dict[str, List[FilmGrainConfig]] = {}

        self._init_built_in_presets()
        self.register_capabilities()

    def set_animation_service(self, animation_service: AnimationService) -> None:
        self.animation_service = animation_service

    def _init_built_in_presets(self) -> None:
        """Initializes descriptive, production-oriented film grain presets with real calibrated parameters."""
        presets = [
            # 1. 35mm Fine Cinema
            FilmGrainConfig(
                config_id="preset_35mm_fine",
                preset_name="35mm Fine Cinema",
                grain_type=GrainType.FINE,
                intensity=0.18,
                scale=1.0,
                luma_weight=1.0,
                chroma_weight=0.15,
                shadow_weight=0.9,
                midtone_weight=1.0,
                highlight_weight=0.25,
                temporal_mode=TemporalGrainMode.FRAME_VARYING,
                provenance="OMNIA Calibrated Fine 35mm Profile",
            ),
            # 2. 16mm Vintage Indie
            FilmGrainConfig(
                config_id="preset_16mm_indie",
                preset_name="16mm Vintage Indie",
                grain_type=GrainType.COARSE,
                intensity=0.38,
                scale=2.0,
                luma_weight=1.0,
                chroma_weight=0.35,
                shadow_weight=0.95,
                midtone_weight=1.0,
                highlight_weight=0.45,
                temporal_mode=TemporalGrainMode.FRAME_VARYING,
                texture=AnalogTextureConfig(
                    halation_mode=HalationMode.RED_ORANGE,
                    halation_threshold=0.82,
                    halation_intensity=0.35,
                    halation_radius=14.0,
                ),
                provenance="OMNIA Vintage 16mm Calibrated Profile",
            ),
            # 3. 8mm Retro Home Movie
            FilmGrainConfig(
                config_id="preset_8mm_retro",
                preset_name="8mm Retro Home Movie",
                grain_type=GrainType.COARSE,
                intensity=0.55,
                scale=2.8,
                luma_weight=1.0,
                chroma_weight=0.5,
                shadow_weight=1.0,
                midtone_weight=1.0,
                highlight_weight=0.6,
                temporal_mode=TemporalGrainMode.FRAME_VARYING,
                texture=AnalogTextureConfig(
                    enable_gate_weave=True,
                    weave_amplitude_x=0.8,
                    weave_amplitude_y=1.2,
                    weave_frequency=1.0,
                    halation_mode=HalationMode.RED_ORANGE,
                    halation_threshold=0.75,
                    halation_intensity=0.5,
                    halation_radius=18.0,
                    enable_film_wear=True,
                    dust_density=0.0004,
                    scratch_intensity=0.6,
                    scratch_count=2,
                ),
                provenance="OMNIA 8mm Archival Emulation Profile",
            ),
            # 4. Noir Monochrome Grain
            FilmGrainConfig(
                config_id="preset_noir_grain",
                preset_name="Noir Monochrome Grain",
                grain_type=GrainType.GAUSSIAN,
                intensity=0.42,
                scale=1.5,
                luma_weight=1.0,
                chroma_weight=0.0, # Zero color noise
                shadow_weight=1.0,
                midtone_weight=0.9,
                highlight_weight=0.3,
                temporal_mode=TemporalGrainMode.FRAME_VARYING,
                provenance="OMNIA High-Contrast Silver Halide Profile",
            ),
            # 5. Modern Digital Sensor Texture
            FilmGrainConfig(
                config_id="preset_digital_subtle",
                preset_name="Modern Subtle Texture",
                grain_type=GrainType.FINE,
                intensity=0.10,
                scale=0.8,
                luma_weight=1.0,
                chroma_weight=0.1,
                shadow_weight=0.7,
                midtone_weight=0.5,
                highlight_weight=0.2,
                temporal_mode=TemporalGrainMode.TEMPORALLY_COHERENT,
                coherence_factor=0.5,
                provenance="OMNIA Subtle Anti-Banding Dither Profile",
            ),
        ]
        for p in presets:
            self._presets[p.preset_name] = p

    # -------------------------------------------------------------------------
    # 1. Config Lifecycle & Undo/Redo
    # -------------------------------------------------------------------------

    def get_or_create_config(self, clip_id: str) -> FilmGrainConfig:
        if clip_id not in self._configs:
            self._configs[clip_id] = FilmGrainConfig(clip_id=clip_id)
            self._undo_stacks[clip_id] = []
            self._redo_stacks[clip_id] = []
        return self._configs[clip_id]

    def update_config(
        self,
        clip_id: str,
        new_config: FilmGrainConfig,
    ) -> FilmGrainConfig:
        cur = self.get_or_create_config(clip_id)
        # Push current state to undo stack
        self._undo_stacks[clip_id].append(copy.deepcopy(cur))
        if len(self._undo_stacks[clip_id]) > 50:
            self._undo_stacks[clip_id].pop(0)
        self._redo_stacks[clip_id].clear()

        new_config.clip_id = clip_id
        new_config.revision = cur.revision + 1
        new_config.updated_at = time.time()
        self._configs[clip_id] = new_config
        return new_config

    def undo(self, clip_id: str) -> Optional[FilmGrainConfig]:
        if not self._undo_stacks.get(clip_id):
            return None
        cur = self.get_or_create_config(clip_id)
        self._redo_stacks[clip_id].append(copy.deepcopy(cur))
        prev = self._undo_stacks[clip_id].pop()
        self._configs[clip_id] = prev
        return prev

    def redo(self, clip_id: str) -> Optional[FilmGrainConfig]:
        if not self._redo_stacks.get(clip_id):
            return None
        cur = self.get_or_create_config(clip_id)
        self._undo_stacks[clip_id].append(copy.deepcopy(cur))
        nxt = self._redo_stacks[clip_id].pop()
        self._configs[clip_id] = nxt
        return nxt

    # -------------------------------------------------------------------------
    # 2. Presets Management
    # -------------------------------------------------------------------------

    def list_presets(self) -> List[Dict[str, Any]]:
        return [p.to_dict() for p in self._presets.values()]

    def get_preset(self, preset_name: str) -> Optional[FilmGrainConfig]:
        return self._presets.get(preset_name)

    def apply_preset_to_clip(
        self,
        clip_id: str,
        preset_name: str,
        intensity_scale: float = 1.0,
    ) -> FilmGrainConfig:
        preset = self.get_preset(preset_name)
        if not preset:
            raise ValueError(f"Preset '{preset_name}' not found. Available: {list(self._presets.keys())}")

        cfg = copy.deepcopy(preset)
        cfg.clip_id = clip_id
        cfg.intensity = float(np.clip(preset.intensity * intensity_scale, 0.0, 1.0))
        return self.update_config(clip_id, cfg)

    # -------------------------------------------------------------------------
    # 3. Frame Processing Dispatch
    # -------------------------------------------------------------------------

    def process_frame(
        self,
        clip_id: str,
        frame: VideoFrameBuffer,
    ) -> Tuple[VideoFrameBuffer, GrainDiagnostics]:
        config = self.get_or_create_config(clip_id)
        return self.engine.process_frame(frame, config)

    # -------------------------------------------------------------------------
    # 4. Capability Registration
    # -------------------------------------------------------------------------

    def register_capabilities(self) -> None:
        """Registers Module 31 capabilities accurately into VideoStudioCapabilityRegistry."""
        caps = [
            VideoStudioCapabilityDescriptor(
                id="video.texture.film_grain",
                name="Deterministic Procedural Film Grain Synthesis",
                description="Seeded procedural normal and coarse film grain with Luma/Chroma split and tonal curve weighting.",
                category=VideoStudioCategory.MOTION,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["grain", "film", "texture", "noise"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.texture.analog_emulation",
                name="Analog Film Emulation & Texture Artifacts",
                description="Subpixel gate weave jitter, anti-halation layer highlight glow bloom, and procedural wear.",
                category=VideoStudioCategory.MOTION,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["analog", "halation", "gate_weave", "wear"],
            ),
        ]

        for cap in caps:
            try:
                video_studio_capability_registry.register(cap)
                logger.info(f"Registered VideoStudio capability: {cap.id} [{cap.category.value}] (State: {cap.implementation_state.value})")
            except Exception as e:
                logger.debug(f"Capability '{cap.id}' notice: {e}")


# Global singleton instance
video_grain_service = VideoGrainService()
