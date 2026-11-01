"""OMNIA Video Studio — Depth Estimation, Depth Maps & 2.5D Compositing Service (Module 32).

Coordinates:
- Ingestion, validation, and storage of clip-level depth map sequences (DepthMap).
- Clip-level DepthEffectConfig lifecycle, versioning, and undo/redo stacks.
- Monocular AI estimation interface integration (respecting capability availability).
- Presets for standard depth workflows:
  * Subtle 2.5D Parallax Pan
  * Cinematic Shallow Depth-of-Field (DoF)
  * Near Subject Foreground Isolation (Depth Slice)
  * Background Depth Falloff
- Capability registration in VideoStudioCapabilityRegistry under VideoStudioCategory.COMPOSITING and VideoStudioCategory.AI.
"""

from typing import Dict, Any, List, Optional, Tuple
import logging
import copy
import time
import numpy as np

from video_studio.depth_models import (
    DepthMap,
    DepthEffectConfig,
    DepthDiagnostics,
    DepthEdgeMode,
    DepthRepresentationType,
    DepthMapProvenance,
    MonocularEstimationAdapter,
)
from video_studio.depth_engine import VideoDepthEngine, normalize_depth_map
from video_studio.effects_models import VideoFrameBuffer
from video_studio.registry import video_studio_capability_registry
from video_studio.registry_models import (
    VideoStudioCategory,
    ImplementationState,
    VideoStudioCapabilityDescriptor,
)

logger = logging.getLogger("omnia.video_studio.depth_service")


class VideoDepthService:
    """Central service managing clip depth maps, 2.5D parallax configs, and capability registration."""

    def __init__(self, engine: Optional[VideoDepthEngine] = None):
        self.engine = engine or VideoDepthEngine()
        self.monocular_adapter = MonocularEstimationAdapter()

        # In-memory storage: clip_id -> DepthEffectConfig
        self._configs: Dict[str, DepthEffectConfig] = {}
        # In-memory depth frames: clip_id -> {frame_number: DepthMap}
        self._depth_maps: Dict[str, Dict[int, DepthMap]] = {}

        # Undo / Redo history: clip_id -> List[DepthEffectConfig]
        self._undo_stacks: Dict[str, List[DepthEffectConfig]] = {}
        self._redo_stacks: Dict[str, List[DepthEffectConfig]] = {}

        self._presets: Dict[str, DepthEffectConfig] = {}
        self._init_built_in_presets()
        self.register_capabilities()

    def register_capabilities(self) -> None:
        """Register Module 32 capabilities in VideoStudioCapabilityRegistry."""
        caps = [
            VideoStudioCapabilityDescriptor(
                id="video.depth.map_processing",
                name="Depth Map Import & Range Processing",
                category=VideoStudioCategory.COMPOSITING,
                implementation_state=ImplementationState.IMPLEMENTED,
                version="1.0.0",
                description="Import, normalize, invert, and slice 2D floating-point and grayscale depth maps.",
            ),
            VideoStudioCapabilityDescriptor(
                id="video.depth.compositing_25d",
                name="2.5D Parallax & Depth-of-Field Compositing",
                category=VideoStudioCategory.COMPOSITING,
                implementation_state=ImplementationState.IMPLEMENTED,
                version="1.0.0",
                description="Depth-driven camera parallax coordinate warping, optical defocus blur, and occlusion.",
            ),
            VideoStudioCapabilityDescriptor(
                id="video.depth.estimation_ai",
                name="Monocular AI Depth Estimation",
                category=VideoStudioCategory.AI,
                implementation_state=ImplementationState.EXPERIMENTAL,
                version="1.0.0",
                description="Monocular neural depth estimation interface (requires loaded weights runtime).",
            ),
        ]
        for cap in caps:
            if video_studio_capability_registry.get(cap.id) is not None:
                continue
            video_studio_capability_registry.register(cap, auth_token="core")
        logger.info("Registered Module 32 Video Depth capabilities.")

    def _init_built_in_presets(self) -> None:
        """Populate standard depth compositing workflow presets."""
        self._presets["subtle_parallax_pan"] = DepthEffectConfig(
            config_id="preset_subtle_parallax",
            enabled=True,
            enable_parallax=True,
            parallax_shift_x=12.0,
            parallax_shift_y=0.0,
            parallax_edge_mode=DepthEdgeMode.REPLICATE,
            parallax_focal_plane=0.5,
        )
        self._presets["cinematic_shallow_dof"] = DepthEffectConfig(
            config_id="preset_shallow_dof",
            enabled=True,
            enable_dof=True,
            dof_focus_distance=0.35,
            dof_focal_range=0.08,
            dof_max_blur=18.0,
            dof_feather=0.12,
        )
        self._presets["foreground_subject_isolate"] = DepthEffectConfig(
            config_id="preset_foreground_isolate",
            enabled=True,
            enable_depth_slice=True,
            slice_near=0.0,
            slice_far=0.45,
            slice_feather=0.04,
        )
        self._presets["depth_occlusion_cut"] = DepthEffectConfig(
            config_id="preset_depth_occlusion",
            enabled=True,
            enable_occlusion=True,
            occlusion_layer_depth=0.5,
            occlusion_softness=0.03,
        )

    def get_presets(self) -> Dict[str, Dict[str, Any]]:
        """Return available presets as serialized dicts."""
        return {name: cfg.to_dict() for name, cfg in self._presets.items()}

    def get_config(self, clip_id: str) -> DepthEffectConfig:
        """Retrieve current configuration for a clip, creating default if absent."""
        if clip_id not in self._configs:
            self._configs[clip_id] = DepthEffectConfig(clip_id=clip_id)
        return copy.deepcopy(self._configs[clip_id])

    def set_config(self, clip_id: str, config: DepthEffectConfig) -> DepthEffectConfig:
        """Store new configuration with undo snapshot."""
        current = self.get_config(clip_id)
        if clip_id not in self._undo_stacks:
            self._undo_stacks[clip_id] = []
        self._undo_stacks[clip_id].append(current)
        if len(self._undo_stacks[clip_id]) > 50:
            self._undo_stacks[clip_id].pop(0)

        # Clear redo stack on fresh modification
        self._redo_stacks[clip_id] = []

        cfg = copy.deepcopy(config)
        cfg.clip_id = clip_id
        self._configs[clip_id] = cfg
        return copy.deepcopy(cfg)

    def undo(self, clip_id: str) -> Optional[DepthEffectConfig]:
        """Undo last configuration modification."""
        if not self._undo_stacks.get(clip_id):
            return None
        current = self._configs.get(clip_id, DepthEffectConfig(clip_id=clip_id))
        if clip_id not in self._redo_stacks:
            self._redo_stacks[clip_id] = []
        self._redo_stacks[clip_id].append(current)

        prev = self._undo_stacks[clip_id].pop()
        self._configs[clip_id] = prev
        return copy.deepcopy(prev)

    def redo(self, clip_id: str) -> Optional[DepthEffectConfig]:
        """Redo last undone configuration modification."""
        if not self._redo_stacks.get(clip_id):
            return None
        current = self._configs.get(clip_id, DepthEffectConfig(clip_id=clip_id))
        self._undo_stacks[clip_id].append(current)

        nxt = self._redo_stacks[clip_id].pop()
        self._configs[clip_id] = nxt
        return copy.deepcopy(nxt)

    def ingest_depth_map(
        self,
        clip_id: str,
        frame_number: int,
        data: np.ndarray,
        representation_type: DepthRepresentationType = DepthRepresentationType.NORMALIZED,
        is_inverted: bool = False,
        provenance: DepthMapProvenance = DepthMapProvenance.IMPORTED_FILE,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DepthMap:
        """Store an imported or generated depth map array for a given clip and frame."""
        h, w = data.shape[:2]
        dm = DepthMap(
            clip_id=clip_id,
            frame_number=frame_number,
            width=w,
            height=h,
            data=data,
            representation_type=representation_type,
            is_inverted=is_inverted,
            provenance=provenance,
            metadata=metadata or {},
        )
        if clip_id not in self._depth_maps:
            self._depth_maps[clip_id] = {}
        self._depth_maps[clip_id][frame_number] = dm
        return dm

    def get_depth_map(self, clip_id: str, frame_number: int) -> Optional[DepthMap]:
        """Retrieve stored depth map for a clip at frame_number."""
        clip_maps = self._depth_maps.get(clip_id, {})
        if frame_number in clip_maps:
            return clip_maps[frame_number]
        # Return frame 0 as fallback if only static depth map was ingested
        return clip_maps.get(0, None)

    def apply_preset(self, clip_id: str, preset_name: str) -> Optional[DepthEffectConfig]:
        """Apply a named preset to the clip."""
        if preset_name not in self._presets:
            return None
        preset_cfg = copy.deepcopy(self._presets[preset_name])
        return self.set_config(clip_id, preset_cfg)

    def render_frame(
        self,
        clip_id: str,
        frame_buffer: VideoFrameBuffer,
    ) -> VideoFrameBuffer:
        """Render a single frame buffer using clip's depth configuration."""
        config = self.get_config(clip_id)
        depth_map = self.get_depth_map(clip_id, frame_buffer.timeline_frame)

        processed_data, _ = self.engine.process_frame(
            frame_rgba=frame_buffer.data,
            depth_map=depth_map,
            config=config,
        )

        return VideoFrameBuffer(
            width=frame_buffer.width,
            height=frame_buffer.height,
            data=processed_data,
            pixel_format=frame_buffer.pixel_format,
            timeline_frame=frame_buffer.timeline_frame,
            color_space=frame_buffer.color_space,
        )


video_depth_service = VideoDepthService()
