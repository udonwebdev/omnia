"""OMNIA Video Studio — Frame Interpolation & Frame-Rate Conversion Service (Module 27).

Coordinates:
- Clip and sequence-level FrameRateConversionConfig management.
- Execution of frame-rate conversion across timeline sequences and slow-motion speed ramps.
- Module 15 (Speed Control) and Module 7 (Playback Engine) integration.
- Capability registration in VideoStudioCapabilityRegistry under VideoStudioCategory.TIMELINE / RENDERING.
"""

import time
import logging
from typing import Dict, Any, List, Optional, Tuple

import numpy as np

from video_studio.effects_models import VideoFrameBuffer
from video_studio.interpolation_models import (
    InterpolationMethod,
    SceneCutAction,
    QualityMode,
    RationalFrameRate,
    FrameRateConversionConfig,
    InterpolationDiagnostics,
)
from video_studio.interpolation_engine import (
    VideoInterpolationEngine,
    video_interpolation_engine,
)
from video_studio.registry import video_studio_capability_registry
from video_studio.registry_models import (
    VideoStudioCategory,
    ImplementationState,
    VideoStudioCapabilityDescriptor,
)

logger = logging.getLogger("omnia.video_studio.interpolation_service")


class VideoInterpolationService:
    """Central orchestrator for frame-rate conversion, motion-compensated interpolation, and capability lifecycle."""

    def __init__(
        self,
        engine: Optional[VideoInterpolationEngine] = None,
    ):
        self.engine = engine or video_interpolation_engine
        self._configs: Dict[str, FrameRateConversionConfig] = {} # clip_id or sequence_id -> Config
        self.register_capabilities()

    # -------------------------------------------------------------------------
    # 1. Config Lifecycle
    # -------------------------------------------------------------------------

    def get_or_create_config(self, entity_id: str) -> FrameRateConversionConfig:
        if entity_id not in self._configs:
            self._configs[entity_id] = FrameRateConversionConfig()
        return self._configs[entity_id]

    def update_config(self, entity_id: str, config: FrameRateConversionConfig) -> FrameRateConversionConfig:
        self._configs[entity_id] = config
        logger.info(f"Updated frame-rate conversion configuration for '{entity_id}'.")
        return config

    def remove_config(self, entity_id: str) -> bool:
        if entity_id in self._configs:
            del self._configs[entity_id]
            return True
        return False

    # -------------------------------------------------------------------------
    # 2. Conversion Execution
    # -------------------------------------------------------------------------

    def convert_frames(
        self,
        entity_id: str,
        source_frames: List[VideoFrameBuffer],
        source_timestamps_sec: List[float],
        target_fps: Optional[float] = None,
    ) -> Tuple[List[VideoFrameBuffer], List[float], InterpolationDiagnostics]:
        """Converts an array of frames and timestamps to the target frame rate."""
        cfg = self.get_or_create_config(entity_id)
        if target_fps:
            cfg.target_rate = RationalFrameRate.from_float(target_fps)

        return self.engine.convert_sequence_rate(
            source_frames=source_frames,
            source_timestamps_sec=source_timestamps_sec,
            config=cfg,
        )

    # -------------------------------------------------------------------------
    # 3. Capability Registration
    # -------------------------------------------------------------------------

    def register_capabilities(self) -> None:
        """Registers Module 27 capabilities with OMNIA Video Studio subsystem registry."""
        capabilities = [
            ("video.interpolation.frame_duplication", "Deterministic Frame Duplication", "Nearest-neighbor temporal frame rate conversion", ImplementationState.IMPLEMENTED),
            ("video.interpolation.frame_blending", "Timestamp-Weighted Frame Blending", "Linear crossfade intermediate frame blending", ImplementationState.IMPLEMENTED),
            ("video.interpolation.motion_compensated", "Dense Optical Flow Motion Compensation", "Farneback bi-directional motion-warped frame synthesis", ImplementationState.IMPLEMENTED),
            ("video.interpolation.scene_cut_detection", "Motion-Safe Scene Cut Protection", "Mean Absolute Difference cut detection and morphing prevention", ImplementationState.IMPLEMENTED),
            ("video.interpolation.learned_model", "Learned Neural Frame Interpolation", "RIFE / deep learning model interpolation adapter", ImplementationState.EXPERIMENTAL),
        ]
        for cap_id, name, desc, state in capabilities:
            try:
                if video_studio_capability_registry.get(cap_id) is None:
                    desc_model = VideoStudioCapabilityDescriptor(
                        id=cap_id,
                        name=name,
                        description=desc,
                        category=VideoStudioCategory.TIMELINE,
                        implementation_state=state,
                    )
                    video_studio_capability_registry.register(desc_model, auth_token="core")
            except Exception as e:
                logger.debug(f"Capability '{cap_id}' registration note: {e}")


# Global singleton
video_interpolation_service = VideoInterpolationService()
