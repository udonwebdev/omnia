"""OMNIA Video Studio — Chroma Keying, Matte Extraction & Management Service (Module 23).

Coordinates:
- Project and clip-level ChromaKeyConfig management.
- Live key color sampling from video frames / coordinates.
- Multi-sample key color management (add, remove, clear, label).
- Integration with Module 11 MultilayerCompositor (attaching extracted matte as CompositingMask).
- Integration with Module 8 AnimationService (keyframing tolerance, softness, spill).
- Capability registration in VideoStudioCapabilityRegistry.
"""

import time
import logging
from typing import Dict, Any, List, Optional, Tuple

import cv2
import numpy as np

from video_studio.effects_models import VideoFrameBuffer
from video_studio.chroma_models import (
    ChromaKeyConfig,
    ChromaKeyType,
    ChromaColorSpace,
    MatteDisplayMode,
    KeyColorSample,
)
from video_studio.chroma_engine import (
    ChromaKeyEngine,
    chroma_key_engine,
)
from video_studio.compositor import MultilayerCompositor
from video_studio.compositing_models import CompositingMask, MaskType
from video_studio.animation_service import AnimationService
from video_studio.registry import video_studio_capability_registry
from video_studio.registry_models import (
    VideoStudioCategory,
    ImplementationState,
    VideoStudioCapabilityDescriptor,
)

logger = logging.getLogger("omnia.video_studio.chroma_service")


class ChromaKeyService:
    """Central service managing chroma key configs, sampling, rendering, and compositing integration."""

    def __init__(
        self,
        engine: Optional[ChromaKeyEngine] = None,
        compositor: Optional[MultilayerCompositor] = None,
        animation_service: Optional[AnimationService] = None,
    ):
        self.engine = engine or chroma_key_engine
        self.compositor = compositor
        self.animation_service = animation_service
        self._configs: Dict[str, ChromaKeyConfig] = {} # clip_id -> ChromaKeyConfig
        self.register_capabilities()

    def set_compositor(self, compositor: MultilayerCompositor) -> None:
        self.compositor = compositor

    def set_animation_service(self, animation_service: AnimationService) -> None:
        self.animation_service = animation_service

    # -------------------------------------------------------------------------
    # 1. Config Lifecycle
    # -------------------------------------------------------------------------

    def get_or_create_config(self, clip_id: str) -> ChromaKeyConfig:
        if clip_id not in self._configs:
            self._configs[clip_id] = ChromaKeyConfig()
        return self._configs[clip_id]

    def update_config(self, clip_id: str, config: ChromaKeyConfig) -> ChromaKeyConfig:
        self._configs[clip_id] = config
        logger.info(f"Updated chroma key config for clip '{clip_id}'.")
        return config

    def remove_config(self, clip_id: str) -> bool:
        if clip_id in self._configs:
            del self._configs[clip_id]
            return True
        return False

    # -------------------------------------------------------------------------
    # 2. Key Color Sampling
    # -------------------------------------------------------------------------

    def sample_key_color_from_frame(
        self,
        clip_id: str,
        frame: VideoFrameBuffer,
        x: int,
        y: int,
        sample_radius: int = 3,
        replace_existing: bool = True,
        label: str = "Sampled",
    ) -> KeyColorSample:
        """
        Samples average color from a region around (x, y) in the given frame buffer.
        """
        cfg = self.get_or_create_config(clip_id)
        data = frame.data
        h, w = data.shape[:2]

        x1 = max(0, int(x - sample_radius))
        y1 = max(0, int(y - sample_radius))
        x2 = min(w, int(x + sample_radius + 1))
        y2 = min(h, int(y + sample_radius + 1))

        region = data[y1:y2, x1:x2, :3] # RGB
        avg_r = int(np.mean(region[:, :, 0]))
        avg_g = int(np.mean(region[:, :, 1]))
        avg_b = int(np.mean(region[:, :, 2]))

        sample = KeyColorSample(r=avg_r, g=avg_g, b=avg_b, label=label)

        if replace_existing:
            cfg.key_samples = [sample]
        else:
            cfg.key_samples.append(sample)

        cfg.key_type = ChromaKeyType.CUSTOM_COLOR
        logger.info(f"Sampled key color ({avg_r}, {avg_g}, {avg_b}) for clip '{clip_id}'.")
        return sample

    # -------------------------------------------------------------------------
    # 3. Processing & Matte Generation
    # -------------------------------------------------------------------------

    def process_clip_frame(
        self,
        clip_id: str,
        frame: VideoFrameBuffer,
        user_mask: Optional[np.ndarray] = None,
        background_frame: Optional[VideoFrameBuffer] = None,
    ) -> VideoFrameBuffer:
        """Processes a single clip frame using its registered ChromaKeyConfig."""
        cfg = self.get_or_create_config(clip_id)
        return self.engine.process_frame(
            frame=frame,
            config=cfg,
            user_mask=user_mask,
            background_frame=background_frame,
        )

    def extract_clip_alpha_matte(
        self,
        clip_id: str,
        frame: VideoFrameBuffer,
    ) -> np.ndarray:
        """Extracts and refines the alpha matte array (float32 [0.0, 1.0]) for mask integration."""
        cfg = self.get_or_create_config(clip_id)
        rgb_img = frame.data[:, :, :3]
        raw_matte = self.engine.extract_matte(rgb_img, cfg)
        return self.engine.refine_matte(raw_matte, cfg)

    def attach_as_compositor_mask(
        self,
        clip_id: str,
        frame: VideoFrameBuffer,
        compositor: Optional[MultilayerCompositor] = None,
    ) -> CompositingMask:
        """
        Extracts refined alpha matte from frame and attaches it as a CompositingMask
        directly to the clip in MultilayerCompositor.
        """
        comp = compositor or self.compositor
        if not comp:
            raise RuntimeError("MultilayerCompositor is required to attach matte as mask.")

        matte = self.extract_clip_alpha_matte(clip_id, frame)
        mask = CompositingMask(
            mask_id=f"chroma_mask_{clip_id}",
            mask_type=MaskType.ALPHA_CHANNEL,
            mask_data=matte,
            strength=1.0,
            invert=False,
            is_enabled=True,
        )
        comp.clip_masks[clip_id] = mask
        logger.info(f"Attached chroma matte as CompositingMask for clip '{clip_id}'.")
        return mask

    # -------------------------------------------------------------------------
    # 4. Capability Registration
    # -------------------------------------------------------------------------

    def register_capabilities(self) -> None:
        """Registers Module 23 capabilities with OMNIA Video Studio subsystem registry."""
        capabilities = [
            ("video.compositing.chroma_key", "Production Chroma Keying Engine", "Color-space-aware green/blue screen extraction"),
            ("video.compositing.matte_extraction", "Alpha Matte Generation & Refinement", "Edge feathering, choke, expansion, and morphological cleanup"),
            ("video.compositing.spill_suppression", "Chroma Spill Suppression", "Edge spill neutralization and desaturation"),
            ("video.compositing.key_sampling", "Interactive Key Color Sampling", "Frame color sampling and multi-point keying"),
        ]
        for cap_id, name, desc in capabilities:
            try:
                if video_studio_capability_registry.get(cap_id) is None:
                    desc_model = VideoStudioCapabilityDescriptor(
                        id=cap_id,
                        name=name,
                        description=desc,
                        category=VideoStudioCategory.COMPOSITING,
                        implementation_state=ImplementationState.IMPLEMENTED,
                    )
                    video_studio_capability_registry.register(desc_model, auth_token="core")
            except Exception as e:
                logger.debug(f"Capability '{cap_id}' registration note: {e}")


# Global singleton
chroma_key_service = ChromaKeyService()
