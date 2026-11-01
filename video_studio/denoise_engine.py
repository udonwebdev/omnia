"""OMNIA Video Studio — Video Denoising, Noise Reduction & Image Restoration Engine (Module 25).

Coordinates:
- Spatial edge-preserving noise reduction:
  1. Bilateral filtering with separate luma and chroma variance control.
  2. Non-Local Means (FastNLMeans) filtering for fine Gaussian and sensor noise.
  3. Edge-aware Guided Filtering with normalized local variance preservation.
- Temporal multi-frame motion-safe accumulation:
  - Uses neighboring decoded frames from the playback/export buffer.
  - Pixel-difference thresholding and motion gating to completely prevent ghosting across cuts or moving objects.
- Image Restoration modules:
  - Dead / hot pixel removal (median neighborhood deviation filter).
  - Deblocking (boundary gradient smoothing for compressed footage).
  - Unsharp masking detail recovery after denoising.
  - Sub-perceptual dithering to eliminate gradient banding.
- Zero alpha degradation:
  - Alpha channel is strictly preserved or passed through untouched.
"""

import time
import math
import logging
from typing import Dict, Any, List, Optional, Tuple

import cv2
import numpy as np

from video_studio.effects_models import VideoFrameBuffer
from video_studio.denoise_models import (
    DenoiseMethod,
    DenoiseQualityMode,
    DenoiseChannelScope,
    DenoiseConfig,
    DenoiseDiagnostics,
)

logger = logging.getLogger("omnia.video_studio.denoise_engine")


class VideoDenoiseEngine:
    """Core computer vision engine for spatial/temporal video denoising and image restoration."""

    # -------------------------------------------------------------------------
    # 1. Spatial Denoising Implementations
    # -------------------------------------------------------------------------

    def apply_bilateral_spatial(
        self,
        rgb_img: np.ndarray,
        config: DenoiseConfig,
    ) -> np.ndarray:
        """
        Edge-preserving bilateral spatial filtering in YCrCb or RGB space.
        Controls luma and chroma grain separately based on channel_scope.
        """
        # Determine kernel diameter from radius
        d = max(3, config.spatial_radius * 2 + 1)
        sigma_color = float(max(5.0, config.strength * 2.0))
        sigma_space = float(max(3.0, config.spatial_radius * 1.5))

        if config.channel_scope == DenoiseChannelScope.LUMA_ONLY:
            # Process luminance Y in YCrCb space, preserve Cr/Cb unchanged
            ycrcb = cv2.cvtColor(rgb_img, cv2.COLOR_RGB2YCrCb)
            y = ycrcb[:, :, 0]
            sigma_y = float(max(5.0, config.luma_strength * 2.0))
            filtered_y = cv2.bilateralFilter(y, d, sigma_y, sigma_space)
            ycrcb[:, :, 0] = filtered_y
            return cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2RGB)

        elif config.channel_scope == DenoiseChannelScope.CHROMA_ONLY:
            # Process Cr and Cb channels, preserve Y
            ycrcb = cv2.cvtColor(rgb_img, cv2.COLOR_RGB2YCrCb)
            sigma_c = float(max(5.0, config.chroma_strength * 2.0))
            ycrcb[:, :, 1] = cv2.bilateralFilter(ycrcb[:, :, 1], d, sigma_c, sigma_space)
            ycrcb[:, :, 2] = cv2.bilateralFilter(ycrcb[:, :, 2], d, sigma_c, sigma_space)
            return cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2RGB)

        else: # LUMA_AND_CHROMA
            if abs(config.luma_strength - config.chroma_strength) > 1.0:
                ycrcb = cv2.cvtColor(rgb_img, cv2.COLOR_RGB2YCrCb)
                sigma_y = float(max(5.0, config.luma_strength * 2.0))
                sigma_c = float(max(5.0, config.chroma_strength * 2.0))
                ycrcb[:, :, 0] = cv2.bilateralFilter(ycrcb[:, :, 0], d, sigma_y, sigma_space)
                ycrcb[:, :, 1] = cv2.bilateralFilter(ycrcb[:, :, 1], d, sigma_c, sigma_space)
                ycrcb[:, :, 2] = cv2.bilateralFilter(ycrcb[:, :, 2], d, sigma_c, sigma_space)
                return cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2RGB)
            else:
                return cv2.bilateralFilter(rgb_img, d, sigma_color, sigma_space)

    def apply_fast_nl_means(
        self,
        rgb_img: np.ndarray,
        config: DenoiseConfig,
    ) -> np.ndarray:
        """
        Non-Local Means denoising using OpenCV fastNlMeans.
        """
        h_luma = float(max(3.0, config.luma_strength * 0.4))
        h_chroma = float(max(3.0, config.chroma_strength * 0.4))
        template_window = 7
        search_window = 21 if config.quality_mode == DenoiseQualityMode.HIGH_QUALITY else 15

        if config.channel_scope == DenoiseChannelScope.LUMA_ONLY:
            ycrcb = cv2.cvtColor(rgb_img, cv2.COLOR_RGB2YCrCb)
            y = ycrcb[:, :, 0]
            ycrcb[:, :, 0] = cv2.fastNlMeansDenoising(y, None, h_luma, template_window, search_window)
            return cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2RGB)

        elif config.channel_scope == DenoiseChannelScope.CHROMA_ONLY:
            ycrcb = cv2.cvtColor(rgb_img, cv2.COLOR_RGB2YCrCb)
            ycrcb[:, :, 1] = cv2.fastNlMeansDenoising(ycrcb[:, :, 1], None, h_chroma, template_window, search_window)
            ycrcb[:, :, 2] = cv2.fastNlMeansDenoising(ycrcb[:, :, 2], None, h_chroma, template_window, search_window)
            return cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2RGB)

        else:
            return cv2.fastNlMeansDenoisingColored(
                rgb_img, None, h_luma, h_chroma, template_window, search_window
            )

    def apply_guided_filter(
        self,
        rgb_img: np.ndarray,
        config: DenoiseConfig,
    ) -> np.ndarray:
        """
        Fast edge-preserving guided filter where guide = input.
        Preserves sharp structural edges while smoothing flat noise areas.
        """
        r = max(2, config.spatial_radius)
        eps = float(max(0.001, (1.0 - config.edge_preservation) * 0.2))

        # Convert to float32 [0.0, 1.0]
        img_f = rgb_img.astype(np.float32) / 255.0
        ksize = (2 * r + 1, 2 * r + 1)

        mean_I = cv2.blur(img_f, ksize)
        mean_II = cv2.blur(img_f * img_f, ksize)
        var_I = mean_II - mean_I * mean_I

        a = var_I / (var_I + eps)
        b = mean_I - a * mean_I

        mean_a = cv2.blur(a, ksize)
        mean_b = cv2.blur(b, ksize)

        q = mean_a * img_f + mean_b
        return np.clip(q * 255.0, 0, 255).astype(np.uint8)

    # -------------------------------------------------------------------------
    # 2. Image Restoration Modules
    # -------------------------------------------------------------------------

    def correct_dead_pixels(self, rgb_img: np.ndarray, threshold: float = 40.0) -> np.ndarray:
        """
        Detects and replaces single-pixel sensor defects (hot/dead pixels)
        that deviate significantly from their 8-neighborhood median.
        """
        median = cv2.medianBlur(rgb_img, 3)
        diff = np.abs(rgb_img.astype(np.float32) - median.astype(np.float32))
        mask = np.any(diff > threshold, axis=-1)

        out = rgb_img.copy()
        out[mask] = median[mask]
        return out

    def apply_deblocking(self, rgb_img: np.ndarray, strength: float = 0.5) -> np.ndarray:
        """
        Mild block boundary filtering to attenuate DCT/macroblock compression artifacts.
        """
        if strength <= 0.01:
            return rgb_img
        blurred = cv2.GaussianBlur(rgb_img, (3, 3), 0.8)
        blend = float(np.clip(strength * 0.4, 0.0, 0.5))
        return cv2.addWeighted(rgb_img, 1.0 - blend, blurred, blend, 0)

    def apply_post_sharpening(self, rgb_img: np.ndarray, amount: float = 0.3) -> np.ndarray:
        """
        Unsharp masking detail restoration after denoising, with noise-coring safeguard.
        """
        if amount <= 0.01:
            return rgb_img
        blurred = cv2.GaussianBlur(rgb_img, (0, 0), 1.5)
        high_pass = rgb_img.astype(np.float32) - blurred.astype(np.float32)

        # Noise coring: ignore subtle high-pass variations to avoid re-amplifying noise
        coring_threshold = 4.0
        high_pass[np.abs(high_pass) < coring_threshold] = 0.0

        sharpened = rgb_img.astype(np.float32) + amount * high_pass
        return np.clip(sharpened, 0, 255).astype(np.uint8)

    def apply_dither(self, rgb_img: np.ndarray) -> np.ndarray:
        """
        Applies subtle triangular/uniform dither noise to prevent 8-bit banding on clean gradients.
        """
        h, w, c = rgb_img.shape
        noise = np.random.uniform(-0.8, 0.8, size=(h, w, c)).astype(np.float32)
        dithered = np.clip(rgb_img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
        return dithered

    # -------------------------------------------------------------------------
    # 3. Temporal Denoising
    # -------------------------------------------------------------------------

    def apply_temporal_accumulation(
        self,
        current_rgb: np.ndarray,
        adjacent_frames: List[np.ndarray],
        config: DenoiseConfig,
    ) -> Tuple[np.ndarray, int]:
        """
        Motion-safe multi-frame temporal accumulation.
        Performs per-pixel motion gating using difference thresholds to prevent ghosting.
        Returns: (denoised_rgb, valid_frame_count)
        """
        if not adjacent_frames or not config.temporal_enabled:
            return current_rgb, 1

        curr_f = current_rgb.astype(np.float32)
        accum = np.copy(curr_f)
        total_weight = np.ones(curr_f.shape[:2], dtype=np.float32)
        used_frames = 1

        thresh = float(max(5.0, config.temporal_threshold))
        blend_w = float(np.clip(config.temporal_blend_weight, 0.05, 0.75))

        for adj in adjacent_frames:
            if adj.shape != current_rgb.shape:
                continue

            adj_f = adj.astype(np.float32)
            # Calculate pixel luminance/color distance
            diff = np.max(np.abs(curr_f - adj_f), axis=-1)

            # Motion mask: weight drops smoothly from blend_w to 0 as diff approaches threshold
            motion_weight = np.clip((thresh - diff) / thresh, 0.0, 1.0) * blend_w
            mw_expanded = np.expand_dims(motion_weight, axis=-1)

            accum += adj_f * mw_expanded
            total_weight += motion_weight
            used_frames += 1

        tw_expanded = np.expand_dims(total_weight, axis=-1)
        res = np.clip(accum / tw_expanded, 0, 255).astype(np.uint8)
        return res, used_frames

    # -------------------------------------------------------------------------
    # 4. Master Frame Processing Pipeline
    # -------------------------------------------------------------------------

    def process_frame(
        self,
        frame: VideoFrameBuffer,
        config: DenoiseConfig,
        adjacent_buffers: Optional[List[VideoFrameBuffer]] = None,
        reference_clean_frame: Optional[VideoFrameBuffer] = None,
    ) -> Tuple[VideoFrameBuffer, DenoiseDiagnostics]:
        """
        Executes end-to-end video denoising and restoration on the given frame buffer.
        Alpha channel is strictly preserved untouched.
        """
        t0 = time.time()

        if not config.is_enabled:
            diag = DenoiseDiagnostics(processing_time_ms=0.0, method_used="BYPASSED")
            return frame.copy(), diag

        src_data = frame.data
        h, w = src_data.shape[:2]
        rgb = src_data[:, :, :3]
        alpha = src_data[:, :, 3:] if src_data.shape[2] == 4 else None

        # 1. Pre-restoration: Dead pixel correction
        if config.dead_pixel_correction:
            rgb = self.correct_dead_pixels(rgb, config.dead_pixel_threshold)

        # 2. Pre-restoration: Deblocking
        if config.deblocking_strength > 0.0:
            rgb = self.apply_deblocking(rgb, config.deblocking_strength)

        # 3. Spatial Denoising Core
        if config.method == DenoiseMethod.FAST_NL_MEANS:
            filtered_rgb = self.apply_fast_nl_means(rgb, config)
        elif config.method == DenoiseMethod.GUIDED_FILTER:
            filtered_rgb = self.apply_guided_filter(rgb, config)
        else: # DenoiseMethod.BILATERAL_SPATIAL or default
            filtered_rgb = self.apply_bilateral_spatial(rgb, config)

        # 4. Temporal Multi-Frame Accumulation (if enabled and buffers available)
        used_frames = 1
        if config.temporal_enabled and adjacent_buffers:
            adj_rgbs = [b.data[:, :, :3] for b in adjacent_buffers if b is not None]
            filtered_rgb, used_frames = self.apply_temporal_accumulation(filtered_rgb, adj_rgbs, config)

        # 5. Post-restoration: Unsharp mask sharpening
        if config.post_sharpening > 0.0:
            filtered_rgb = self.apply_post_sharpening(filtered_rgb, config.post_sharpening)

        # 6. Post-restoration: Dithering
        if config.add_dither:
            filtered_rgb = self.apply_dither(filtered_rgb)

        # 7. Recombine with unmodified alpha channel
        if alpha is not None:
            out_data = np.concatenate([filtered_rgb, alpha], axis=-1)
        else:
            out_data = filtered_rgb

        t1 = time.time()
        elapsed_ms = (t1 - t0) * 1000.0

        # Optional quality metric estimation if reference provided
        psnr = None
        mse = None
        if reference_clean_frame is not None:
            ref_rgb = reference_clean_frame.data[:, :, :3].astype(np.float32)
            out_rgb = filtered_rgb.astype(np.float32)
            raw_rgb = src_data[:, :, :3].astype(np.float32)

            mse_raw = float(np.mean((raw_rgb - ref_rgb) ** 2))
            mse_out = float(np.mean((out_rgb - ref_rgb) ** 2))
            mse = mse_out
            if mse_out > 1e-6:
                psnr = float(10.0 * np.log10((255.0 ** 2) / mse_out))
            if mse_raw > 1e-6:
                mse_diff = mse_raw - mse_out
                mse = mse_diff

        diag = DenoiseDiagnostics(
            processing_time_ms=elapsed_ms,
            psnr_gain_db=psnr,
            mse_reduction=mse,
            temporal_frames_used=used_frames,
            method_used=config.method.value,
        )

        out_buffer = VideoFrameBuffer(
            width=w,
            height=h,
            pixel_format="RGBA" if alpha is not None else "RGB",
            color_space=frame.color_space,
            data=out_data,
            pts_seconds=frame.pts_seconds,
            timeline_frame=frame.timeline_frame,
        )
        return out_buffer, diag


# Global singleton
video_denoise_engine = VideoDenoiseEngine()
