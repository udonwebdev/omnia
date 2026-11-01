"""OMNIA Video Studio — Video Upscaling, Super-Resolution & Detail Enhancement Service (Module 26).

Coordinates:
- Clip-level UpscaleConfig management.
- Frame upscaling execution with caching and diagnostic telemetry.
- Learned super-resolution capability detection and model validation.
- Integration with Module 8 AnimationService (keyframing scale factor and sharpening amount).
- Capability registration in VideoStudioCapabilityRegistry under VideoStudioCategory.RENDERING / EFFECTS.
"""

import time
import logging
from typing import Dict, Any, List, Optional, Tuple

import cv2
import numpy as np

from video_studio.effects_models import VideoFrameBuffer
from video_studio.upscale_models import (
    UpscaleConfig,
    UpscaleAlgorithm,
    SizingPolicy,
    AspectRatioMode,
    UpscaleQualityMode,
    UpscaleDiagnostics,
)
from video_studio.upscale_engine import (
    VideoUpscaleEngine,
    video_upscale_engine,
)
from video_studio.animation_service import AnimationService
from video_studio.registry import video_studio_capability_registry
from video_studio.registry_models import (
    VideoStudioCategory,
    ImplementationState,
    VideoStudioCapabilityDescriptor,
)

logger = logging.getLogger("omnia.video_studio.upscale_service")


class VideoUpscaleService:
    """Central service managing video upscaling, model validation, and capability registration."""

    def __init__(
        self,
        engine: Optional[VideoUpscaleEngine] = None,
        animation_service: Optional[AnimationService] = None,
    ):
        self.engine = engine or video_upscale_engine
        self.animation_service = animation_service
        self._configs: Dict[str, UpscaleConfig] = {} # clip_id -> UpscaleConfig
        self.register_capabilities()

    def set_animation_service(self, animation_service: AnimationService) -> None:
        self.animation_service = animation_service

    # -------------------------------------------------------------------------
    # 1. Config Lifecycle
    # -------------------------------------------------------------------------

    def get_or_create_config(self, clip_id: str) -> UpscaleConfig:
        if clip_id not in self._configs:
            self._configs[clip_id] = UpscaleConfig()
        return self._configs[clip_id]

    def update_config(self, clip_id: str, config: UpscaleConfig) -> UpscaleConfig:
        self._configs[clip_id] = config
        logger.info(f"Updated upscaling configuration for clip '{clip_id}'.")
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
    ) -> Tuple[VideoFrameBuffer, UpscaleDiagnostics]:
        """Processes and upscales a clip frame using its registered configuration."""
        cfg = self.get_or_create_config(clip_id)
        return self.engine.process_frame(frame, cfg)

    # -------------------------------------------------------------------------
    # 3. Capability Registration
    # -------------------------------------------------------------------------

    def register_capabilities(self) -> None:
        """Registers Module 26 capabilities with OMNIA Video Studio subsystem registry."""
        capabilities = [
            ("video.rendering.spatial_upscale", "Conventional High-Fidelity Resampling", "Lanczos4, Bicubic, Bilinear, and Nearest-Neighbor interpolation", ImplementationState.IMPLEMENTED),
            ("video.rendering.detail_enhancement", "Edge Detail Enhancement & Sharpening", "Unsharp masking with halo overshoot suppression", ImplementationState.IMPLEMENTED),
            ("video.rendering.denoise_integration", "Pre-Upscale Denoise Pipeline Integration", "Module 25 noise removal prior to resolution magnification", ImplementationState.IMPLEMENTED),
            ("video.rendering.learned_super_res", "Learned Super-Resolution Model Runtime", "Model-backed deep learning super-resolution adapter", ImplementationState.EXPERIMENTAL),
        ]
        for cap_id, name, desc, state in capabilities:
            try:
                if video_studio_capability_registry.get(cap_id) is None:
                    desc_model = VideoStudioCapabilityDescriptor(
                        id=cap_id,
                        name=name,
                        description=desc,
                        category=VideoStudioCategory.RENDERING,
                        implementation_state=state,
                    )
                    video_studio_capability_registry.register(desc_model, auth_token="core")
            except Exception as e:
                logger.debug(f"Capability '{cap_id}' registration note: {e}")


# Global singleton
video_upscale_service = VideoUpscaleService()
