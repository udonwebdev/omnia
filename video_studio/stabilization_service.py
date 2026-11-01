"""OMNIA Video Studio — Video Stabilization & Camera Correction Service (Module 21).

Coordinates:
- Asynchronous motion analysis coordination and cache lookup.
- Non-destructive clip-level stabilization configuration (smoothing radius, auto-crop zoom).
- Seamless integration with Module 10 effects pipeline and Module 7/17 rendering.
- Module 1 Capability Registry integration.
"""

import os
import time
import uuid
import logging
from typing import Dict, Any, List, Optional, Tuple

from video_studio.stabilization_models import (
    MotionModelType,
    StabilizationMode,
    StabilizationConfig,
    MotionAnalysisReport,
    CorrectiveTransform,
)
from video_studio.motion_analysis_engine import motion_analysis_engine, MotionAnalysisEngine
from video_studio.stabilization_engine import stabilization_engine, StabilizationEngine
from video_studio.media_models import MediaAsset
from video_studio.media_library import media_library_registry
from video_studio.effects_models import VideoFrameBuffer
from video_studio.registry import video_studio_capability_registry
from video_studio.registry_models import (
    VideoStudioCategory,
    ImplementationState,
    VideoStudioCapabilityDescriptor,
)

logger = logging.getLogger("omnia.video_studio.stabilization_service")


class StabilizationService:
    """Central service managing video motion analysis, stabilization configuration, and frame processing."""

    def __init__(
        self,
        analysis_eng: Optional[MotionAnalysisEngine] = None,
        stab_eng: Optional[StabilizationEngine] = None,
    ):
        self.analysis_engine = analysis_eng or motion_analysis_engine
        self.stabilization_engine = stab_eng or stabilization_engine
        # Clip-level stabilization settings: {clip_item_id: StabilizationConfig}
        self._clip_configs: Dict[str, StabilizationConfig] = {}
        # Precalculated corrective transforms: {clip_item_id: List[CorrectiveTransform]}
        self._clip_corrections: Dict[str, List[CorrectiveTransform]] = {}
        self._register_capabilities()

    def _register_capabilities(self) -> None:
        """Registers Module 21 Stabilization capabilities into the global registry."""
        caps = [
            VideoStudioCapabilityDescriptor(
                id="video.stabilization.motion_analysis",
                name="Video Motion Analysis Engine",
                description="Shi-Tomasi corner detection, Lucas-Kanade optical flow, and RANSAC camera motion estimation",
                category=VideoStudioCategory.TRACKING,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["motion", "optical_flow", "tracking", "features"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.stabilization.camera_smoothing",
                name="Camera Trajectory Smoothing",
                description="Temporal Gaussian moving-window camera path smoothing with scene cut boundary isolation",
                category=VideoStudioCategory.MOTION,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["stabilize", "smooth", "trajectory"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.stabilization.crop_compensation",
                name="Adaptive Crop & Zoom Compensation",
                description="Dynamic affine warping with aspect-ratio preserved boundary zoom and edge replication",
                category=VideoStudioCategory.COMPOSITING,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["crop", "zoom", "warp_affine"],
            ),
        ]
        for cap in caps:
            try:
                video_studio_capability_registry.register(cap, auth_token="core")
            except Exception as e:
                logger.debug(f"Capability '{cap.id}' note: {e}")

    # --------------------------------------------------------------------------
    # Motion Analysis & Configuration
    # --------------------------------------------------------------------------

    def analyze_clip(
        self,
        clip_id: str,
        asset: MediaAsset,
        motion_model: MotionModelType = MotionModelType.SIMILARITY,
    ) -> MotionAnalysisReport:
        """Runs motion analysis on source media asset, caches report, and builds default corrections."""
        report = self.analysis_engine.analyze_asset_motion(
            file_path=asset.file_location,
            asset_id=asset.asset_id,
            motion_model=motion_model,
        )

        # Ensure clip has a default configuration
        if clip_id not in self._clip_configs:
            self._clip_configs[clip_id] = StabilizationConfig(
                is_enabled=True,
                motion_model=motion_model,
            )

        # Precompute corrective transforms for fast playback/rendering
        self._recompute_corrections(clip_id, report)
        return report

    def get_analysis_report(self, asset_id: str) -> Optional[MotionAnalysisReport]:
        return self.analysis_engine.get_cached_report(asset_id)

    def get_clip_config(self, clip_id: str) -> StabilizationConfig:
        if clip_id not in self._clip_configs:
            self._clip_configs[clip_id] = StabilizationConfig(is_enabled=False)
        return self._clip_configs[clip_id]

    def update_clip_config(
        self,
        clip_id: str,
        asset_id: str,
        config: StabilizationConfig,
    ) -> StabilizationConfig:
        """Updates stabilization parameters for a clip and refreshes corrective transforms."""
        self._clip_configs[clip_id] = config
        report = self.get_analysis_report(asset_id)
        if report:
            self._recompute_corrections(clip_id, report)
        return config

    def _recompute_corrections(self, clip_id: str, report: MotionAnalysisReport) -> None:
        cfg = self.get_clip_config(clip_id)
        corrections = self.stabilization_engine.compute_corrective_transforms(report, cfg)
        self._clip_corrections[clip_id] = corrections

    # --------------------------------------------------------------------------
    # Frame Processing (Effects Pipeline Hook)
    # --------------------------------------------------------------------------

    def process_frame(
        self,
        clip_id: str,
        frame_buf: VideoFrameBuffer,
        source_frame: int,
    ) -> VideoFrameBuffer:
        """Applies stabilization warp to a video frame if enabled for the clip."""
        cfg = self.get_clip_config(clip_id)
        if not cfg.is_enabled:
            return frame_buf

        corrections = self._clip_corrections.get(clip_id)
        if not corrections:
            return frame_buf

        # Lookup correction for source_frame
        idx = max(0, min(source_frame, len(corrections) - 1))
        corr = corrections[idx]

        return self.stabilization_engine.apply_stabilization_to_frame(
            frame_buf=frame_buf,
            correction=corr,
            border_fill=cfg.border_fill,
        )


# Global singleton
stabilization_service = StabilizationService()
