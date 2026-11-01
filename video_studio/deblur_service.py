"""OMNIA Video Studio — Video Deblurring & Motion Blur Processing Service (Module 28).

Coordinates:
- Clip-level DeblurConfig management.
- Integration with Module 21 (Motion Analysis) and Module 22 (Motion Tracking) vectors for motion blur synthesis.
- Integration with Module 8 (AnimationService) for keyframed blur length and angles.
- Capability registration in VideoStudioCapabilityRegistry under VideoStudioCategory.EFFECTS.
"""

import time
import logging
from typing import Dict, Any, List, Optional, Tuple

import numpy as np

from video_studio.effects_models import VideoFrameBuffer
from video_studio.deblur_models import (
    DeblurConfig,
    BlurOperationType,
    BlurKernelType,
    ShutterAngleMode,
    DeblurMethod,
    DeblurDiagnostics,
)
from video_studio.deblur_engine import (
    VideoDeblurEngine,
    video_deblur_engine,
)
from video_studio.animation_service import AnimationService
from video_studio.registry import video_studio_capability_registry
from video_studio.registry_models import (
    VideoStudioCategory,
    ImplementationState,
    VideoStudioCapabilityDescriptor,
)

logger = logging.getLogger("omnia.video_studio.deblur_service")


class VideoDeblurService:
    """Central service orchestrating video deblurring restoration, motion blur generation, and capability lifecycle."""

    def __init__(
        self,
        engine: Optional[VideoDeblurEngine] = None,
        animation_service: Optional[AnimationService] = None,
    ):
        self.engine = engine or video_deblur_engine
        self.animation_service = animation_service
        self._configs: Dict[str, DeblurConfig] = {} # clip_id -> DeblurConfig
        self.register_capabilities()

    def set_animation_service(self, animation_service: AnimationService) -> None:
        self.animation_service = animation_service

    # -------------------------------------------------------------------------
    # 1. Config Lifecycle
    # -------------------------------------------------------------------------

    def get_or_create_config(self, clip_id: str) -> DeblurConfig:
        if clip_id not in self._configs:
            self._configs[clip_id] = DeblurConfig()
        return self._configs[clip_id]

    def update_config(self, clip_id: str, config: DeblurConfig) -> DeblurConfig:
        self._configs[clip_id] = config
        logger.info(f"Updated deblur / motion blur configuration for clip '{clip_id}'.")
        return config

    def remove_config(self, clip_id: str) -> bool:
        if clip_id in self._configs:
            del self._configs[clip_id]
            return True
        return False

    # -------------------------------------------------------------------------
    # 2. Frame Processing Execution
    # -------------------------------------------------------------------------

    def process_clip_frame(
        self,
        clip_id: str,
        frame: VideoFrameBuffer,
        motion_vector: Optional[Tuple[float, float]] = None,
    ) -> Tuple[VideoFrameBuffer, DeblurDiagnostics]:
        """Processes a clip frame with its registered deblur/motion-blur configuration."""
        cfg = self.get_or_create_config(clip_id)
        return self.engine.process_frame(frame, cfg, motion_vector=motion_vector)

    # -------------------------------------------------------------------------
    # 3. Capability Registration
    # -------------------------------------------------------------------------

    def register_capabilities(self) -> None:
        """Registers Module 28 capabilities with OMNIA Video Studio subsystem registry."""
        capabilities = [
            ("video.effects.deblur_wiener", "Wiener Deconvolution Restoration", "Frequency-domain deblurring with Gibbs ringing suppression", ImplementationState.IMPLEMENTED),
            ("video.effects.motion_blur_generation", "Camera Shutter Motion Blur Generation", "Shutter-angle simulation and directional motion trails", ImplementationState.IMPLEMENTED),
            ("video.effects.motion_blur_reduction", "Velocity-Aware Motion Blur Reduction", "Directional deconvolution guided by tracking vectors", ImplementationState.IMPLEMENTED),
        ]
        for cap_id, name, desc, state in capabilities:
            try:
                if video_studio_capability_registry.get(cap_id) is None:
                    desc_model = VideoStudioCapabilityDescriptor(
                        id=cap_id,
                        name=name,
                        description=desc,
                        category=VideoStudioCategory.MOTION,
                        implementation_state=state,
                    )
                    video_studio_capability_registry.register(desc_model, auth_token="core")
            except Exception as e:
                logger.debug(f"Capability '{cap_id}' registration note: {e}")


# Global singleton
video_deblur_service = VideoDeblurService()
