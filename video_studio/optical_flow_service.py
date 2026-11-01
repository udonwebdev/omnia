"""OMNIA Video Studio — Optical Flow & Motion Vector Service (Module 33).

Coordinates:
- In-memory lifecycle, caching, and retrieval of MotionVectorField instances.
- Cancellable background motion analysis jobs for assets and clip sequences.
- Integration contracts with downstream Video Studio subsystems:
  * Module 15 (Time Remapping / Speed): Provides motion vectors for motion-aware speed remapping.
  * Module 21 (Stabilization): Feeds validated dense/sparse motion vectors to stabilization pipelines.
  * Module 22 (Tracking): Exposes reusable flow fields to avoid redundant per-frame feature recomputation.
  * Module 25 (Denoising): Supplies motion-aligned vector fields for motion-compensated temporal accumulation.
  * Module 27 (Frame Interpolation): Supplies forward/backward optical flow fields for bi-directional warping.
  * Module 28 (Motion Blur): Delivers localized vector displacement for directional point-spread function synthesis.
  * Module 32 (Depth Processing): Provides inter-frame coordinate alignment for temporal depth map stabilization.
- Capability registration in VideoStudioCapabilityRegistry under VideoStudioCategory.MOTION and VideoStudioCategory.AI.
"""

import time
import copy
import logging
from typing import Dict, Any, List, Optional, Tuple, Callable

import numpy as np

from video_studio.effects_models import VideoFrameBuffer
from video_studio.optical_flow_models import (
    MotionVectorField,
    MotionVectorFieldType,
    FlowAlgorithmType,
    FlowQualityPreset,
    FlowDirection,
    FlowFieldStatus,
    MotionAnalysisConfig,
)
from video_studio.optical_flow_engine import OpticalFlowEngine, optical_flow_engine
from video_studio.registry import video_studio_capability_registry
from video_studio.registry_models import (
    VideoStudioCategory,
    ImplementationState,
    VideoStudioCapabilityDescriptor,
)

logger = logging.getLogger("omnia.video_studio.optical_flow_service")


class VideoOpticalFlowService:
    """Central service coordinating optical flow estimation, caching, and downstream consumers."""

    def __init__(self, engine: Optional[OpticalFlowEngine] = None):
        self.engine = engine or optical_flow_engine
        # In-memory motion cache: key -> MotionVectorField
        # Key format: f"{asset_id}_{src_idx}_{tgt_idx}_{algo}_{preset}"
        self._cache: Dict[str, MotionVectorField] = {}
        self._max_cache_entries = 200

        self.register_capabilities()

    def register_capabilities(self) -> None:
        """Register Module 33 capabilities into VideoStudioCapabilityRegistry."""
        caps = [
            VideoStudioCapabilityDescriptor(
                id="video.motion.dense_optical_flow",
                name="Dense Optical Flow Estimation",
                category=VideoStudioCategory.MOTION,
                implementation_state=ImplementationState.IMPLEMENTED,
                version="1.0.0",
                description="Pixel-dense Gunnar Farneback and DIS optical flow with forward-backward consistency verification.",
                tags=["motion", "optical_flow", "dense", "vectors"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.motion.sparse_feature_flow",
                name="Sparse Feature Optical Flow Tracking",
                category=VideoStudioCategory.MOTION,
                implementation_state=ImplementationState.IMPLEMENTED,
                version="1.0.0",
                description="Pyramidal Lucas-Kanade sparse motion tracking with Shi-Tomasi feature selection.",
                tags=["motion", "tracking", "sparse", "lucas_kanade"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.motion.ai_neural_flow",
                name="Deep Neural Optical Flow (RAFT / FlowNet)",
                category=VideoStudioCategory.AI,
                implementation_state=ImplementationState.EXPERIMENTAL,
                version="1.0.0",
                description="Deep learning neural motion estimation adapter interface (requires loaded model runtime).",
                tags=["motion", "ai", "raft", "neural"],
            ),
        ]
        for cap in caps:
            if video_studio_capability_registry.get(cap.id) is not None:
                continue
            video_studio_capability_registry.register(cap, auth_token="core")
        logger.info("Registered Module 33 Optical Flow capabilities.")

    # -------------------------------------------------------------------------
    # Cache Management
    # -------------------------------------------------------------------------

    def _make_cache_key(
        self,
        asset_id: str,
        src_idx: int,
        tgt_idx: int,
        config: MotionAnalysisConfig,
    ) -> str:
        return f"{asset_id}_{src_idx}_{tgt_idx}_{config.algorithm.value}_{config.quality_preset.value}"

    def get_cached_flow(
        self,
        asset_id: str,
        src_idx: int,
        tgt_idx: int,
        config: Optional[MotionAnalysisConfig] = None,
    ) -> Optional[MotionVectorField]:
        """Retrieve previously estimated motion field from cache."""
        cfg = config or MotionAnalysisConfig()
        key = self._make_cache_key(asset_id, src_idx, tgt_idx, cfg)
        return self._cache.get(key)

    def cache_flow(self, field: MotionVectorField, config: MotionAnalysisConfig) -> None:
        """Store motion field in cache, enforcing memory limits."""
        key = self._make_cache_key(field.asset_id, field.source_frame_index, field.target_frame_index, config)
        if len(self._cache) >= self._max_cache_entries:
            # Drop oldest entry
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        self._cache[key] = field

    def clear_cache(self) -> None:
        """Clear motion vector cache."""
        self._cache.clear()

    # -------------------------------------------------------------------------
    # Core Estimation Execution
    # -------------------------------------------------------------------------

    def estimate_inter_frame_motion(
        self,
        frame_a: VideoFrameBuffer,
        frame_b: VideoFrameBuffer,
        config: Optional[MotionAnalysisConfig] = None,
        use_cache: bool = True,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> MotionVectorField:
        """Estimate motion vectors between two frames with caching and cancellation support."""
        if cancel_check is not None and cancel_check():
            raise TimeoutError("Motion analysis job cancelled by caller.")

        cfg = config or MotionAnalysisConfig()
        asset_id = getattr(frame_a, "asset_id", "default_asset")

        if use_cache:
            cached = self.get_cached_flow(asset_id, frame_a.timeline_frame, frame_b.timeline_frame, cfg)
            if cached is not None:
                return cached

        if cfg.algorithm == FlowAlgorithmType.PYRAMIDAL_LK_SPARSE:
            result = self.engine.compute_sparse_flow(frame_a, frame_b)
        else:
            result = self.engine.compute_dense_flow(frame_a, frame_b, config=cfg)

        if use_cache and result.status == FlowFieldStatus.VALID:
            self.cache_flow(result, cfg)

        return result

    # -------------------------------------------------------------------------
    # Downstream Integration Helpers
    # -------------------------------------------------------------------------

    def get_motion_for_interpolation(
        self,
        frame_a: VideoFrameBuffer,
        frame_b: VideoFrameBuffer,
        quality: FlowQualityPreset = FlowQualityPreset.STUDIO_HIGH_QUALITY,
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], FlowFieldStatus]:
        """Provides verified forward and backward flow fields for Module 27 frame interpolation.
        
        Returns:
            Tuple of (flow_forward (H,W,2), flow_backward (H,W,2), status)
        """
        cfg = MotionAnalysisConfig(
            algorithm=FlowAlgorithmType.FARNEBACK_DENSE,
            quality_preset=quality,
            direction=FlowDirection.BIDIRECTIONAL,
        )
        field = self.estimate_inter_frame_motion(frame_a, frame_b, config=cfg)
        return field.dense_flow, field.backward_flow, field.status

    def get_motion_for_denoising(
        self,
        frame_current: VideoFrameBuffer,
        frame_adjacent: VideoFrameBuffer,
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Provides dense motion vector field and confidence map for Module 25 motion-compensated denoising.
        
        Returns:
            Tuple of (flow_to_adjacent (H,W,2), confidence_map (H,W))
        """
        cfg = MotionAnalysisConfig(
            algorithm=FlowAlgorithmType.FARNEBACK_DENSE,
            quality_preset=FlowQualityPreset.BALANCED,
            direction=FlowDirection.FORWARD,
        )
        field = self.estimate_inter_frame_motion(frame_current, frame_adjacent, config=cfg)
        return field.dense_flow, field.confidence_map

    def get_motion_for_motion_blur(
        self,
        frame_a: VideoFrameBuffer,
        frame_b: VideoFrameBuffer,
    ) -> Optional[Tuple[float, float]]:
        """Calculates dominant mean motion vector for Module 28 directional motion blur."""
        cfg = MotionAnalysisConfig(
            algorithm=FlowAlgorithmType.FARNEBACK_DENSE,
            quality_preset=FlowQualityPreset.FAST_PREVIEW,
            downscale_factor=0.5,
        )
        field = self.estimate_inter_frame_motion(frame_a, frame_b, config=cfg)
        if field.dense_flow is None or field.status != FlowFieldStatus.VALID:
            return None

        mean_dx = float(np.mean(field.dense_flow[:, :, 0]))
        mean_dy = float(np.mean(field.dense_flow[:, :, 1]))
        return mean_dx, mean_dy

    def get_motion_for_stabilization(
        self,
        frame_a: VideoFrameBuffer,
        frame_b: VideoFrameBuffer,
    ) -> List[Tuple[float, float, float, float, float]]:
        """Supplies verified motion points (x, y, dx, dy, confidence) to Module 21 stabilization."""
        field = self.engine.compute_sparse_flow(frame_a, frame_b)
        return [
            (v.x, v.y, v.dx, v.dy, v.confidence)
            for v in field.sparse_vectors
            if v.status == "TRACKED"
        ]


video_optical_flow_service = VideoOpticalFlowService()
