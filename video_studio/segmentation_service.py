"""OMNIA Video Studio — Object Segmentation, Semantic Masking & Subject Isolation Service (Module 34).

Coordinates:
- Per-clip, per-frame MultiMaskFrameContainer storage and retrieval.
- Non-AI mask ingestion (imported external masks, manual splines, chroma key mattes).
- Undo/redo state management for mask adjustments and refinements.
- Downstream integration contracts:
  * Module 11 (Compositing): Attaches masks to clip/layer CompositingMask.
  * Module 23 (Chroma Keying): Combines chroma key mattes with subject segmentation masks.
  * Module 22 (Tracking): Associates segmentation bounding boxes with tracking targets.
  * Module 32 (Depth): Uses masks to isolate depth slices for 2.5D layer separation.
  * Module 33 (Optical Flow): Drives inter-frame mask propagation.
  * Module 17 (Export): Delivers rendered alpha channels during timeline final export.
- Capability registration in VideoStudioCapabilityRegistry under VideoStudioCategory.COMPOSITING and VideoStudioCategory.AI.
"""

import time
import copy
import logging
from typing import Dict, Any, List, Optional, Tuple

import numpy as np

from video_studio.effects_models import VideoFrameBuffer
from video_studio.compositing_models import CompositingMask, MaskType
from video_studio.segmentation_models import (
    SegmentationWorkflowType,
    SegmentationPromptType,
    MaskCombinationMode,
    MaskRefinementConfig,
    VideoSegmentMask,
    MultiMaskFrameContainer,
    ModelRuntimeDescriptor,
)
from video_studio.segmentation_engine import VideoSegmentationEngine, video_segmentation_engine
from video_studio.registry import video_studio_capability_registry
from video_studio.registry_models import (
    VideoStudioCategory,
    ImplementationState,
    VideoStudioCapabilityDescriptor,
)

logger = logging.getLogger("omnia.video_studio.segmentation_service")


class VideoSegmentationService:
    """Central service managing video segmentation masks, propagation, and downstream consumers."""

    def __init__(self, engine: Optional[VideoSegmentationEngine] = None):
        self.engine = engine or video_segmentation_engine
        # Storage: clip_id -> {frame_number: MultiMaskFrameContainer}
        self._clip_frames: Dict[str, Dict[int, MultiMaskFrameContainer]] = {}
        # Undo / Redo history: clip_id -> List[Dict[int, MultiMaskFrameContainer]]
        self._undo_stacks: Dict[str, List[Dict[int, MultiMaskFrameContainer]]] = {}
        self._redo_stacks: Dict[str, List[Dict[int, MultiMaskFrameContainer]]] = {}

        self.register_capabilities()

    def register_capabilities(self) -> None:
        """Register Module 34 capabilities into VideoStudioCapabilityRegistry."""
        caps = [
            VideoStudioCapabilityDescriptor(
                id="video.segmentation.mask_refinement",
                name="Semantic Mask Refinement & Edge Matting",
                category=VideoStudioCategory.COMPOSITING,
                implementation_state=ImplementationState.IMPLEMENTED,
                version="1.0.0",
                description="Morphological erosion, dilation, edge-aware bilateral feathering, hole filling, and multi-matte boolean combinations.",
                tags=["segmentation", "mask", "refinement", "feathering"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.segmentation.temporal_propagation",
                name="Optical-Flow-Assisted Mask Propagation",
                category=VideoStudioCategory.COMPOSITING,
                implementation_state=ImplementationState.IMPLEMENTED,
                version="1.0.0",
                description="Inter-frame mask propagation powered by Module 33 dense optical flow with scene-cut reset protection.",
                tags=["segmentation", "propagation", "optical_flow", "temporal"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.segmentation.ai_inference",
                name="AI Subject & Object Segmentation",
                category=VideoStudioCategory.AI,
                implementation_state=ImplementationState.EXPERIMENTAL,
                version="1.0.0",
                description="Interactive point and box promptable neural segmentation runtime (requires downloaded model weights).",
                tags=["segmentation", "ai", "sam", "promptable"],
            ),
        ]
        for cap in caps:
            if video_studio_capability_registry.get(cap.id) is not None:
                continue
            video_studio_capability_registry.register(cap, auth_token="core")
        logger.info("Registered Module 34 Segmentation capabilities.")

    # -------------------------------------------------------------------------
    # Container & Mask Lifecycle
    # -------------------------------------------------------------------------

    def get_or_create_frame_container(
        self,
        clip_id: str,
        frame_number: int,
        pts_seconds: float = 0.0,
    ) -> MultiMaskFrameContainer:
        """Retrieve or create container holding masks for a specific frame."""
        if clip_id not in self._clip_frames:
            self._clip_frames[clip_id] = {}
        if frame_number not in self._clip_frames[clip_id]:
            self._clip_frames[clip_id][frame_number] = MultiMaskFrameContainer(
                frame_index=frame_number,
                pts_seconds=pts_seconds,
                clip_id=clip_id,
                masks=[],
            )
        return self._clip_frames[clip_id][frame_number]

    def add_mask(
        self,
        clip_id: str,
        frame_number: int,
        mask: VideoSegmentMask,
    ) -> VideoSegmentMask:
        """Add a mask to a frame with undo history snapshot."""
        self._push_undo(clip_id)
        container = self.get_or_create_frame_container(clip_id, frame_number)
        container.masks.append(mask)
        return mask

    def ingest_imported_mask(
        self,
        clip_id: str,
        frame_number: int,
        mask_data: np.ndarray,
        label: str = "imported_matte",
    ) -> VideoSegmentMask:
        """Ingest externally supplied or rendered mask array."""
        h, w = mask_data.shape[:2]
        norm_data = mask_data.astype(np.float32)
        if norm_data.ndim == 3:
            norm_data = norm_data[:, :, 0]
        if np.max(norm_data) > 1.0:
            norm_data /= 255.0
        norm_data = np.clip(norm_data, 0.0, 1.0)

        mask = VideoSegmentMask(
            label=label,
            workflow=SegmentationWorkflowType.IMPORTED_MASK,
            width=w,
            height=h,
            data=norm_data,
        )
        return self.add_mask(clip_id, frame_number, mask)

    # -------------------------------------------------------------------------
    # Undo / Redo
    # -------------------------------------------------------------------------

    def _push_undo(self, clip_id: str) -> None:
        if clip_id not in self._undo_stacks:
            self._undo_stacks[clip_id] = []
        cur = copy.deepcopy(self._clip_frames.get(clip_id, {}))
        self._undo_stacks[clip_id].append(cur)
        if len(self._undo_stacks[clip_id]) > 50:
            self._undo_stacks[clip_id].pop(0)
        self._redo_stacks[clip_id] = []

    def undo(self, clip_id: str) -> bool:
        if not self._undo_stacks.get(clip_id):
            return False
        cur = copy.deepcopy(self._clip_frames.get(clip_id, {}))
        if clip_id not in self._redo_stacks:
            self._redo_stacks[clip_id] = []
        self._redo_stacks[clip_id].append(cur)
        self._clip_frames[clip_id] = self._undo_stacks[clip_id].pop()
        return True

    def redo(self, clip_id: str) -> bool:
        if not self._redo_stacks.get(clip_id):
            return False
        cur = copy.deepcopy(self._clip_frames.get(clip_id, {}))
        self._undo_stacks[clip_id].append(cur)
        self._clip_frames[clip_id] = self._redo_stacks[clip_id].pop()
        return True

    # -------------------------------------------------------------------------
    # Downstream Integrations
    # -------------------------------------------------------------------------

    def export_as_compositing_mask(
        self,
        clip_id: str,
        frame_number: int,
        combination_mode: MaskCombinationMode = MaskCombinationMode.UNION,
    ) -> Optional[CompositingMask]:
        """Convert segmented masks into a Module 11 CompositingMask."""
        container = self.get_or_create_frame_container(clip_id, frame_number)
        combined_data = container.composite_combined_mask(mode=combination_mode)
        if combined_data is None:
            return None

        # Scale float32 to uint8 for CompositingMask
        uint8_matte = (combined_data * 255.0).astype(np.uint8)
        return CompositingMask(
            mask_id=f"seg_mask_{clip_id}_{frame_number}",
            mask_type=MaskType.GRAYSCALE_LUMA,
            mask_data=uint8_matte,
            strength=1.0,
            is_enabled=True,
        )

    def combine_with_chroma_matte(
        self,
        chroma_matte_uint8: np.ndarray,
        clip_id: str,
        frame_number: int,
        mode: MaskCombinationMode = MaskCombinationMode.INTERSECT,
    ) -> np.ndarray:
        """Combine Module 23 Chroma Key matte with segmentation mask."""
        container = self.get_or_create_frame_container(clip_id, frame_number)
        seg_matte = container.composite_combined_mask()
        chroma_f32 = chroma_matte_uint8.astype(np.float32) / 255.0

        if seg_matte is None:
            return chroma_matte_uint8

        combined_f32 = self.engine.combine_masks(chroma_f32, seg_matte, mode=mode)
        return (combined_f32 * 255.0).astype(np.uint8)

    def apply_mask_to_frame_alpha(
        self,
        frame_rgba: VideoFrameBuffer,
        clip_id: str,
        combination_mode: MaskCombinationMode = MaskCombinationMode.UNION,
    ) -> VideoFrameBuffer:
        """Modulate frame RGBA buffer alpha channel with segmentation masks."""
        container = self.get_or_create_frame_container(clip_id, frame_rgba.timeline_frame)
        mask_f32 = container.composite_combined_mask(mode=combination_mode)
        if mask_f32 is None:
            return frame_rgba

        h, w = frame_rgba.height, frame_rgba.width
        if mask_f32.shape[:2] != (h, w):
            import cv2
            mask_f32 = cv2.resize(mask_f32, (w, h), interpolation=cv2.INTER_LINEAR)

        data = frame_rgba.data.copy()
        if data.shape[2] == 4:
            orig_alpha = data[:, :, 3].astype(np.float32) / 255.0
            new_alpha = np.clip(orig_alpha * mask_f32 * 255.0, 0, 255).astype(np.uint8)
            data[:, :, 3] = new_alpha
        else:
            new_alpha = np.clip(mask_f32 * 255.0, 0, 255).astype(np.uint8)
            data = np.concatenate([data, new_alpha[:, :, np.newaxis]], axis=2)

        return VideoFrameBuffer(
            width=w,
            height=h,
            data=data,
            pixel_format=frame_rgba.pixel_format,
            timeline_frame=frame_rgba.timeline_frame,
            color_space=frame_rgba.color_space,
        )


video_segmentation_service = VideoSegmentationService()
