"""OMNIA Video Studio — Video Upscaling, Super-Resolution & Detail Enhancement Engine (Module 26).

Coordinates:
- Conventional mathematical resampling:
  1. Lanczos4 (8x8 sinc filter window for ringing-controlled high-fidelity reconstruction).
  2. Bicubic spline interpolation (smooth continuous derivatives).
  3. Bilinear interpolation (fast preview and baseline scaling).
  4. Nearest-Neighbor (pixel-art, retro, or ultra-low overhead).
- Learned Super-Resolution adapter:
  - Supports cv2.dnn / ONNX model inference when runtime model is supplied.
  - Truthful fallback to conventional Lanczos4 when model is not available or cv2.dnn_superres is absent.
- Detail Enhancement & Ringing Suppression:
  - Unsharp masking detail sharpening with halo suppression / overshoot clamping.
- Pre-upscaling Denoise integration with Module 25:
  - Cleans input noise prior to spatial upscaling to prevent amplifying sensor grain into large artifacts.
- Complete alpha transparency preservation:
  - Alpha is independently resampled using high-precision filters to prevent fringe discoloration.
"""

import time
import math
import logging
from typing import Dict, Any, List, Optional, Tuple

import cv2
import numpy as np

from video_studio.effects_models import VideoFrameBuffer
from video_studio.upscale_models import (
    UpscaleAlgorithm,
    SizingPolicy,
    AspectRatioMode,
    UpscaleQualityMode,
    UpscaleConfig,
    UpscaleDiagnostics,
)
from video_studio.denoise_engine import video_denoise_engine
from video_studio.denoise_models import DenoiseConfig, DenoiseMethod

logger = logging.getLogger("omnia.video_studio.upscale_engine")


class VideoUpscaleEngine:
    """Core computer vision engine for spatial upscaling, super-resolution, and detail enhancement."""

    def __init__(self):
        self._learned_sr_available = hasattr(cv2, "dnn_superres")

    @property
    def is_learned_super_res_available(self) -> bool:
        return self._learned_sr_available

    # -------------------------------------------------------------------------
    # 1. Detail Enhancement & Ringing Suppression
    # -------------------------------------------------------------------------

    def apply_detail_enhancement(
        self,
        rgb_img: np.ndarray,
        amount: float = 0.25,
        radius: float = 1.0,
        suppress_halo: bool = True,
    ) -> np.ndarray:
        """
        Unsharp masking edge detail recovery with halo suppression and overshoot clamping.
        """
        if amount <= 0.01:
            return rgb_img

        ksize = int(max(3, round(radius * 4 + 1)))
        if ksize % 2 == 0:
            ksize += 1

        blurred = cv2.GaussianBlur(rgb_img, (ksize, ksize), radius)
        high_pass = rgb_img.astype(np.float32) - blurred.astype(np.float32)

        if suppress_halo:
            # Clamp high-pass magnitude to avoid high-contrast white/black ringing rings
            max_overshoot = 25.0
            high_pass = np.clip(high_pass, -max_overshoot, max_overshoot)

        sharpened = rgb_img.astype(np.float32) + amount * high_pass
        return np.clip(sharpened, 0, 255).astype(np.uint8)

    # -------------------------------------------------------------------------
    # 2. Resampling Kernels
    # -------------------------------------------------------------------------

    def resample_image(
        self,
        img: np.ndarray,
        target_w: int,
        target_h: int,
        algorithm: UpscaleAlgorithm,
    ) -> np.ndarray:
        """
        Applies requested interpolation filter to resize image array (H, W, C).
        """
        if algorithm == UpscaleAlgorithm.NEAREST_NEIGHBOR:
            interp = cv2.INTER_NEAREST
        elif algorithm == UpscaleAlgorithm.BILINEAR:
            interp = cv2.INTER_LINEAR
        elif algorithm == UpscaleAlgorithm.BICUBIC:
            interp = cv2.INTER_CUBIC
        else: # LANCZOS4 or default
            interp = cv2.INTER_LANCZOS4

        return cv2.resize(img, (target_w, target_h), interpolation=interp)

    # -------------------------------------------------------------------------
    # 3. Learned Super-Resolution Model Execution (if available)
    # -------------------------------------------------------------------------

    def run_learned_super_resolution(
        self,
        rgb_img: np.ndarray,
        target_w: int,
        target_h: int,
        config: UpscaleConfig,
    ) -> Tuple[np.ndarray, bool]:
        """
        Executes model-backed super-resolution if model and runtime exist;
        otherwise provides truthful fallback to Lanczos4 reconstruction.
        Returns: (output_rgb, model_executed_bool)
        """
        if not self._learned_sr_available or not config.model_path:
            # Truthful fallback: Lanczos4
            res = self.resample_image(rgb_img, target_w, target_h, UpscaleAlgorithm.LANCZOS4)
            return res, False

        try:
            sr = cv2.dnn_superres.DnnSuperResImpl_create() # type: ignore
            model_name = (config.model_name or "espcn").lower()
            scale = int(round(config.scale_factor)) if config.scale_factor in [2, 3, 4] else 2
            sr.readModel(config.model_path)
            sr.setModel(model_name, scale)
            if config.use_gpu:
                sr.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
                sr.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)

            upscaled = sr.upsample(rgb_img)
            # If target dimensions differ from model's fixed scale factor, adapt cleanly
            if upscaled.shape[1] != target_w or upscaled.shape[0] != target_h:
                upscaled = cv2.resize(upscaled, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)
            return upscaled, True
        except Exception as e:
            logger.warning(f"Learned super-resolution failed, falling back to Lanczos4: {e}")
            res = self.resample_image(rgb_img, target_w, target_h, UpscaleAlgorithm.LANCZOS4)
            return res, False

    # -------------------------------------------------------------------------
    # 4. Master Frame Processing Pipeline
    # -------------------------------------------------------------------------

    def process_frame(
        self,
        frame: VideoFrameBuffer,
        config: UpscaleConfig,
    ) -> Tuple[VideoFrameBuffer, UpscaleDiagnostics]:
        """
        Processes frame buffer through pre-denoising, spatial upscaling, and detail enhancement.
        Preserves alpha channel with dedicated resampling.
        """
        t0 = time.time()
        src_data = frame.data
        src_h, src_w = src_data.shape[:2]

        if not config.is_enabled:
            diag = UpscaleDiagnostics(
                input_width=src_w,
                input_height=src_h,
                output_width=src_w,
                output_height=src_h,
                scale_factor_x=1.0,
                scale_factor_y=1.0,
                processing_time_ms=0.0,
                algorithm_used="BYPASSED",
                backend="CPU",
                model_inference=False,
            )
            return frame.copy(), diag

        target_w, target_h = config.calculate_target_size(src_w, src_h)

        rgb = src_data[:, :, :3]
        has_alpha = (src_data.shape[2] == 4)
        alpha = src_data[:, :, 3] if has_alpha else None

        # 1. Optional Pre-upscale Denoising (Module 25 Integration)
        if config.pre_denoise and config.denoise_strength > 0:
            denoise_cfg = DenoiseConfig(
                method=DenoiseMethod.BILATERAL_SPATIAL,
                strength=config.denoise_strength,
                spatial_radius=3,
                is_enabled=True,
            )
            denoised_buf, _ = video_denoise_engine.process_frame(
                VideoFrameBuffer(width=src_w, height=src_h, data=rgb),
                denoise_cfg,
            )
            rgb = denoised_buf.data[:, :, :3]

        # 2. Upscaling Core (Spatial or Learned)
        model_executed = False
        if config.algorithm == UpscaleAlgorithm.LEARNED_SUPER_RES:
            upscaled_rgb, model_executed = self.run_learned_super_resolution(
                rgb, target_w, target_h, config
            )
        else:
            upscaled_rgb = self.resample_image(
                rgb, target_w, target_h, config.algorithm
            )

        # 3. Post-Upscale Detail Enhancement
        if config.detail_enhancement and config.sharpen_amount > 0.0:
            upscaled_rgb = self.apply_detail_enhancement(
                upscaled_rgb,
                amount=config.sharpen_amount,
                radius=config.sharpen_radius,
                suppress_halo=config.halo_suppression,
            )

        # 4. Alpha Resampling & Recombination
        if has_alpha and alpha is not None:
            # Resample alpha using linear/lanczos4 to prevent harsh stair-stepping
            upscaled_alpha = cv2.resize(
                alpha, (target_w, target_h), interpolation=cv2.INTER_LINEAR
            )
            out_data = np.concatenate(
                [upscaled_rgb, np.expand_dims(upscaled_alpha, axis=-1)], axis=-1
            )
        else:
            out_data = upscaled_rgb

        t1 = time.time()
        elapsed_ms = (t1 - t0) * 1000.0

        diag = UpscaleDiagnostics(
            input_width=src_w,
            input_height=src_h,
            output_width=target_w,
            output_height=target_h,
            scale_factor_x=target_w / max(1.0, src_w),
            scale_factor_y=target_h / max(1.0, src_h),
            processing_time_ms=elapsed_ms,
            algorithm_used=config.algorithm.value,
            backend="GPU" if (model_executed and config.use_gpu) else "CPU",
            model_inference=model_executed,
        )

        out_buffer = VideoFrameBuffer(
            width=target_w,
            height=target_h,
            pixel_format="RGBA" if has_alpha else "RGB",
            color_space=frame.color_space,
            data=out_data,
            pts_seconds=frame.pts_seconds,
            timeline_frame=frame.timeline_frame,
        )
        return out_buffer, diag


# Global singleton
video_upscale_engine = VideoUpscaleEngine()
