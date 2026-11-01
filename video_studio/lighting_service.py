"""OMNIA Video Studio — Lighting, Exposure & Relighting Service (Module 29).

Coordinates:
- Clip-level LightingEngineDocument lifecycle and versioning.
- Integration with Module 8 (AnimationService) for keyframed lighting properties.
- Integration with Module 22 (TrackingService) for motion-tracked light regions.
- Preset management (Studio Portrait, High Contrast Noir, Sunlight Leak, Stage Spotlight, Golden Rim).
- Undo / redo command patterns and editing state.
- Capability registration in VideoStudioCapabilityRegistry under VideoStudioCategory.COLOR.
"""

from typing import Dict, Any, List, Optional, Tuple
import logging
import copy
import time

from video_studio.lighting_models import (
    LightingEngineDocument,
    GlobalExposureTonalConfig,
    LocalLightRegion,
    LightType,
    LightBlendMode,
    RelightingEngineMode,
    SceneAwareRelightingExtension,
    LightingDiagnostics,
)
from video_studio.lighting_engine import video_lighting_engine, VideoLightingEngine
from video_studio.effects_models import VideoFrameBuffer
from video_studio.animation_service import AnimationService
from video_studio.registry import video_studio_capability_registry
from video_studio.registry_models import (
    VideoStudioCategory,
    ImplementationState,
    VideoStudioCapabilityDescriptor,
)

logger = logging.getLogger("omnia.video_studio.lighting_service")


class VideoLightingService:
    """Central service orchestrating video exposure, lighting regions, presets, and capability lifecycle."""

    def __init__(
        self,
        engine: Optional[VideoLightingEngine] = None,
        animation_service: Optional[AnimationService] = None,
    ):
        self.engine = engine or video_lighting_engine
        self.animation_service = animation_service
        self._documents: Dict[str, LightingEngineDocument] = {} # clip_id -> LightingEngineDocument
        self._presets: Dict[str, LightingEngineDocument] = {}
        self._undo_stacks: Dict[str, List[LightingEngineDocument]] = {}
        self._redo_stacks: Dict[str, List[LightingEngineDocument]] = {}

        self._init_built_in_presets()
        self.register_capabilities()

    def set_animation_service(self, animation_service: AnimationService) -> None:
        self.animation_service = animation_service

    def _init_built_in_presets(self) -> None:
        """Initializes production lighting and exposure presets."""
        # 1. Studio Portrait Key & Rim
        p1 = LightingEngineDocument(
            document_id="preset_studio_portrait",
            clip_id="preset",
            global_tone=GlobalExposureTonalConfig(exposure_stops=0.2, contrast=1.05, highlights=-5.0, shadows=5.0),
            light_regions=[
                LocalLightRegion(
                    name="Key Light",
                    pos_x=0.35,
                    pos_y=0.35,
                    radius_x=0.3,
                    radius_y=0.3,
                    feather=0.6,
                    intensity=0.8,
                    color_rgb=(1.0, 0.95, 0.88),
                    blend_mode=LightBlendMode.ADD,
                ),
                LocalLightRegion(
                    name="Cool Rim Light",
                    pos_x=0.8,
                    pos_y=0.4,
                    radius_x=0.2,
                    radius_y=0.35,
                    feather=0.4,
                    intensity=0.6,
                    color_rgb=(0.85, 0.92, 1.0),
                    blend_mode=LightBlendMode.SCREEN,
                ),
            ]
        )
        self._presets["studio_portrait"] = p1

        # 2. Golden Sun Flare
        p2 = LightingEngineDocument(
            document_id="preset_sun_leak",
            clip_id="preset",
            global_tone=GlobalExposureTonalConfig(exposure_stops=0.1, temperature=15.0),
            light_regions=[
                LocalLightRegion(
                    name="Sun Leak Flare",
                    light_type=LightType.DIRECTIONAL,
                    pos_x=0.1,
                    pos_y=0.1,
                    direction_angle_deg=45.0,
                    radius_x=0.6,
                    radius_y=0.6,
                    feather=0.8,
                    intensity=0.75,
                    color_rgb=(1.0, 0.82, 0.55),
                    blend_mode=LightBlendMode.SCREEN,
                )
            ]
        )
        self._presets["sun_leak"] = p2

        # 3. High Contrast Noir Flagging
        p3 = LightingEngineDocument(
            document_id="preset_noir_shading",
            clip_id="preset",
            global_tone=GlobalExposureTonalConfig(contrast=1.35, blacks=-15.0, whites=10.0),
            light_regions=[
                LocalLightRegion(
                    name="Dark Vignette / Flag",
                    pos_x=0.5,
                    pos_y=0.5,
                    radius_x=0.45,
                    radius_y=0.45,
                    feather=0.5,
                    intensity=-0.8, # Negative intensity for shading
                    invert_mask=True,
                )
            ]
        )
        self._presets["noir_flagging"] = p3

    # -------------------------------------------------------------------------
    # 1. Document Lifecycle & Undo/Redo
    # -------------------------------------------------------------------------

    def get_or_create_document(self, clip_id: str) -> LightingEngineDocument:
        if clip_id not in self._documents:
            self._documents[clip_id] = LightingEngineDocument(clip_id=clip_id)
            self._undo_stacks[clip_id] = []
            self._redo_stacks[clip_id] = []
        return self._documents[clip_id]

    def update_document(
        self,
        clip_id: str,
        new_doc: LightingEngineDocument,
    ) -> LightingEngineDocument:
        cur = self.get_or_create_document(clip_id)
        # Push current state to undo stack
        self._undo_stacks[clip_id].append(copy.deepcopy(cur))
        if len(self._undo_stacks[clip_id]) > 50:
            self._undo_stacks[clip_id].pop(0)
        self._redo_stacks[clip_id].clear()

        new_doc.clip_id = clip_id
        new_doc.revision = cur.revision + 1
        new_doc.updated_at = time.time()
        self._documents[clip_id] = new_doc
        return new_doc

    def undo(self, clip_id: str) -> Optional[LightingEngineDocument]:
        if not self._undo_stacks.get(clip_id):
            return None
        cur = self.get_or_create_document(clip_id)
        self._redo_stacks[clip_id].append(copy.deepcopy(cur))
        prev = self._undo_stacks[clip_id].pop()
        self._documents[clip_id] = prev
        return prev

    def redo(self, clip_id: str) -> Optional[LightingEngineDocument]:
        if not self._redo_stacks.get(clip_id):
            return None
        cur = self.get_or_create_document(clip_id)
        self._undo_stacks[clip_id].append(copy.deepcopy(cur))
        nxt = self._redo_stacks[clip_id].pop()
        self._documents[clip_id] = nxt
        return nxt

    def apply_preset(self, clip_id: str, preset_name: str) -> LightingEngineDocument:
        if preset_name not in self._presets:
            raise ValueError(f"Preset '{preset_name}' not found. Available: {list(self._presets.keys())}")
        preset_doc = copy.deepcopy(self._presets[preset_name])
        preset_doc.document_id = f"light_doc_{clip_id}"
        return self.update_document(clip_id, preset_doc)

    def list_presets(self) -> List[str]:
        return list(self._presets.keys())

    # -------------------------------------------------------------------------
    # 2. Region Management
    # -------------------------------------------------------------------------

    def add_light_region(self, clip_id: str, region: LocalLightRegion) -> LocalLightRegion:
        doc = self.get_or_create_document(clip_id)
        if len(doc.light_regions) >= 16:
            raise ValueError("Maximum limit of 16 light regions reached for this clip.")
        doc.light_regions.append(region)
        doc.revision += 1
        return region

    def remove_light_region(self, clip_id: str, region_id: str) -> bool:
        doc = self.get_or_create_document(clip_id)
        initial_len = len(doc.light_regions)
        doc.light_regions = [r for r in doc.light_regions if r.region_id != region_id]
        if len(doc.light_regions) < initial_len:
            doc.revision += 1
            return True
        return False

    # -------------------------------------------------------------------------
    # 3. Frame Processing Dispatch
    # -------------------------------------------------------------------------

    def process_frame(
        self,
        clip_id: str,
        frame: VideoFrameBuffer,
        tracking_offset: Optional[Tuple[float, float]] = None,
    ) -> Tuple[VideoFrameBuffer, LightingDiagnostics]:
        doc = self.get_or_create_document(clip_id)
        return self.engine.process_frame(frame, doc, tracking_offset=tracking_offset)

    # -------------------------------------------------------------------------
    # 4. Capability Registration
    # -------------------------------------------------------------------------

    def register_capabilities(self) -> None:
        """Registers Module 29 capabilities accurately into VideoStudioCapabilityRegistry."""
        caps = [
            VideoStudioCapabilityDescriptor(
                id="video.lighting.global_exposure",
                name="Deterministic Video Exposure & Tonal Engine",
                description="Deterministic photographic exposure compensation (stops), highlights/shadows, and midtone gamma.",
                category=VideoStudioCategory.COLOR,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["lighting", "exposure", "color", "tonal"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.lighting.localized_regions",
                name="Parametric Localized Lighting & Relighting Regions",
                description="Radial, directional, and polygon mask lighting regions with falloff feathering and blend equations.",
                category=VideoStudioCategory.COLOR,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["lighting", "relighting", "masks", "blending"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.lighting.scene_aware_relighting",
                name="Scene-Aware AI Relighting Extension",
                description="Scene-aware normal/depth relighting extension interface. Inactive until physical model is loaded.",
                category=VideoStudioCategory.AI,
                implementation_state=ImplementationState.EXPERIMENTAL,
                tags=["lighting", "ai", "relighting", "experimental"],
            ),
        ]

        for cap in caps:
            try:
                video_studio_capability_registry.register(cap)
                logger.info(f"Registered VideoStudio capability: {cap.id} [{cap.category.value}] (State: {cap.implementation_state.value})")
            except Exception as e:
                logger.debug(f"Capability '{cap.id}' notice: {e}")


# Global singleton instance
video_lighting_service = VideoLightingService()
