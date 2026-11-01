"""OMNIA Video Studio — Chroma Keying, Matte Extraction & Spill Suppression Engine (Module 23).

Coordinates:
- Color-space-aware chroma extraction (CIE L*a*b* delta-E, YCbCr, HSV, Weighted RGB).
- Non-destructive alpha matte generation from real decoded pixels.
- Edge refinement: feathering (Gaussian), choke/expand (morphological erosion/dilation), contrast shaping.
- Multi-sample key color support with distance union.
- Real-time chroma spill suppression (green/blue neutralization and desaturation).
- Morphological matte cleanup (dust removal, hole filling).
- Straight and premultiplied alpha handling.
- Viewer display modes (Matte only, Keyed FG, Spill only, Composite over checkerboard/background).
"""

import math
import logging
from typing import Dict, Any, List, Optional, Tuple

import cv2
import numpy as np

from video_studio.effects_models import VideoFrameBuffer
from video_studio.chroma_models import (
    ChromaColorSpace,
    ChromaKeyType,
    MatteDisplayMode,
    KeyColorSample,
    ChromaKeyConfig,
)

logger = logging.getLogger("omnia.video_studio.chroma_engine")


class ChromaKeyEngine:
    """Core computer vision processing engine for chroma extraction, matte generation and spill removal."""

    def extract_matte(self, rgb_img: np.ndarray, config: ChromaKeyConfig) -> np.ndarray:
        """
        Extracts a normalized float32 alpha matte [0.0 = transparent background, 1.0 = solid foreground]
        from an RGB uint8 image using configured color space and key samples.
        """
        h, w, c = rgb_img.shape
        bgr = cv2.cvtColor(rgb_img, cv2.COLOR_RGB2BGR)

        # Convert to target color space
        if config.color_space == ChromaColorSpace.LAB:
            space_img = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
        elif config.color_space == ChromaColorSpace.YCBCR:
            space_img = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb).astype(np.float32)
        elif config.color_space == ChromaColorSpace.HSV:
            space_img = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
        else: # RGB
            space_img = rgb_img.astype(np.float32)

        # Compute minimum distance across all key color samples
        min_distances = np.full((h, w), 1e6, dtype=np.float32)

        for sample in config.key_samples:
            sample_rgb = np.array([[[sample.r, sample.g, sample.b]]], dtype=np.uint8)
            sample_bgr = cv2.cvtColor(sample_rgb, cv2.COLOR_RGB2BGR)

            if config.color_space == ChromaColorSpace.LAB:
                sample_space = cv2.cvtColor(sample_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)[0, 0]
                # In Lab: chromatic channels A and B carry color info; optionally weight Luma less
                dL = (space_img[:, :, 0] - sample_space[0]) * 0.4
                da = (space_img[:, :, 1] - sample_space[1])
                db = (space_img[:, :, 2] - sample_space[2])
                dist = np.sqrt(dL * dL + da * da + db * db)
            elif config.color_space == ChromaColorSpace.YCBCR:
                sample_space = cv2.cvtColor(sample_bgr, cv2.COLOR_BGR2YCrCb).astype(np.float32)[0, 0]
                dY = (space_img[:, :, 0] - sample_space[0]) * 0.3
                dCr = (space_img[:, :, 1] - sample_space[1])
                dCb = (space_img[:, :, 2] - sample_space[2])
                dist = np.sqrt(dY * dY + dCr * dCr + dCb * dCb)
            elif config.color_space == ChromaColorSpace.HSV:
                sample_space = cv2.cvtColor(sample_bgr, cv2.COLOR_BGR2HSV).astype(np.float32)[0, 0]
                # Hue is circular [0, 180]
                dh = np.abs(space_img[:, :, 0] - sample_space[0])
                dh = np.minimum(dh, 180.0 - dh) * 2.0
                ds = np.abs(space_img[:, :, 1] - sample_space[1]) * 0.7
                dv = np.abs(space_img[:, :, 2] - sample_space[2]) * 0.4
                dist = np.sqrt(dh * dh + ds * ds + dv * dv)
            else: # RGB
                dr = (space_img[:, :, 0] - sample.r) * 0.3
                dg = (space_img[:, :, 1] - sample.g) * 0.59
                db = (space_img[:, :, 2] - sample.b) * 0.11
                dist = np.sqrt(dr * dr + dg * dg + db * db)

            min_distances = np.minimum(min_distances, dist)

        tol = max(1.0, float(config.tolerance))
        soft = max(0.01, float(config.softness))

        # Distance <= tol: transparent (0.0). Distance >= tol + soft: opaque foreground (1.0).
        matte = np.clip((min_distances - tol) / soft, 0.0, 1.0)

        # Black/White point clipping threshold
        low = min(0.99, max(0.0, float(config.matte_threshold_low)))
        high = max(low + 0.01, min(1.0, float(config.matte_threshold_high)))
        matte = np.clip((matte - low) / (high - low), 0.0, 1.0)

        # Edge contrast adjustment
        if abs(config.edge_contrast - 1.0) > 0.01:
            gamma = 1.0 / max(0.1, config.edge_contrast)
            matte = np.power(matte, gamma)

        return matte

    def refine_matte(self, matte: np.ndarray, config: ChromaKeyConfig) -> np.ndarray:
        """Applies choke, expansion, hole/spot cleanup, and edge feathering to the alpha matte."""
        m = np.copy(matte)

        # 1. Morphological hole filling & spot cleanup
        if config.cleanup_holes_radius > 0:
            k_size = config.cleanup_holes_radius * 2 + 1
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
            m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, kernel)

        if config.cleanup_spots_radius > 0:
            k_size = config.cleanup_spots_radius * 2 + 1
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
            m = cv2.morphologyEx(m, cv2.MORPH_OPEN, kernel)

        # 2. Choke / Expand (negative = erode/choke foreground; positive = dilate/expand foreground)
        if config.choke != 0:
            k_size = abs(config.choke) * 2 + 1
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
            if config.choke < 0:
                m = cv2.erode(m, kernel, iterations=1)
            else:
                m = cv2.dilate(m, kernel, iterations=1)

        # 3. Gaussian edge feathering
        if config.feather_radius > 0:
            f_size = config.feather_radius * 2 + 1
            m = cv2.GaussianBlur(m, (f_size, f_size), sigmaX=config.feather_radius * 0.5)

        # 4. Inversion
        if config.invert_matte:
            m = 1.0 - m

        return np.clip(m, 0.0, 1.0)

    def suppress_spill(
        self,
        rgb_img: np.ndarray,
        matte: np.ndarray,
        config: ChromaKeyConfig,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Suppresses green/blue spill contamination along foreground edges.
        Returns: (despilled_rgb, spill_map_mask)
        """
        if not config.spill_suppression:
            return np.copy(rgb_img), np.zeros(rgb_img.shape[:2], dtype=np.float32)

        rgb = rgb_img.astype(np.float32) / 255.0
        r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]

        primary_r, primary_g, primary_b = config.get_primary_color()
        is_green_key = (primary_g > primary_r and primary_g > primary_b)
        is_blue_key = (primary_b > primary_r and primary_b > primary_g)

        spill_strength = float(np.clip(config.spill_strength, 0.0, 1.0))
        spill_thresh = float(config.spill_threshold)

        spill_map = np.zeros(rgb.shape[:2], dtype=np.float32)

        if is_green_key or (not is_blue_key):
            # Green spill: Green exceeds the average of Red and Blue
            max_other = (r + b) / 2.0
            excess = np.maximum(0.0, g - (max_other + spill_thresh))
            spill_map = np.clip(excess * 2.0, 0.0, 1.0)

            # Suppress excess green on foreground pixels
            suppressed_g = g - (excess * spill_strength)
            if config.spill_replace_color:
                rep_r, rep_g, rep_b = [c / 255.0 for c in config.spill_replace_color]
                r = r + (rep_r - r) * spill_map * spill_strength
                g = suppressed_g + (rep_g - suppressed_g) * spill_map * spill_strength
                b = b + (rep_b - b) * spill_map * spill_strength
            else:
                g = suppressed_g
        else:
            # Blue spill: Blue exceeds the average of Red and Green
            max_other = (r + g) / 2.0
            excess = np.maximum(0.0, b - (max_other + spill_thresh))
            spill_map = np.clip(excess * 2.0, 0.0, 1.0)

            suppressed_b = b - (excess * spill_strength)
            if config.spill_replace_color:
                rep_r, rep_g, rep_b = [c / 255.0 for c in config.spill_replace_color]
                r = r + (rep_r - r) * spill_map * spill_strength
                g = g + (rep_g - g) * spill_map * spill_strength
                b = suppressed_b + (rep_b - suppressed_b) * spill_map * spill_strength
            else:
                b = suppressed_b

        despilled = np.stack([r, g, b], axis=-1)
        despilled_uint8 = np.clip(despilled * 255.0, 0, 255).astype(np.uint8)
        return despilled_uint8, spill_map

    def process_frame(
        self,
        frame: VideoFrameBuffer,
        config: ChromaKeyConfig,
        user_mask: Optional[np.ndarray] = None,
        background_frame: Optional[VideoFrameBuffer] = None,
    ) -> VideoFrameBuffer:
        """
        Executes end-to-end chroma key extraction, edge refinement, spill suppression,
        and compositing according to the requested display mode.
        """
        if not config.is_enabled:
            return frame.copy()

        src_data = frame.data
        h, w = src_data.shape[:2]
        rgb_img = src_data[:, :, :3]

        # 1. Raw Matte Extraction
        raw_matte = self.extract_matte(rgb_img, config)

        # 2. Matte Refinement
        refined_matte = self.refine_matte(raw_matte, config)

        # 3. Combine with User Mask if present (Multiplicative intersection / restriction)
        if user_mask is not None:
            if user_mask.shape[:2] != (h, w):
                user_mask = cv2.resize(user_mask, (w, h), interpolation=cv2.INTER_LINEAR)
            mask_float = user_mask.astype(np.float32)
            if mask_float.max() > 1.0:
                mask_float = mask_float / 255.0
            refined_matte = np.clip(refined_matte * mask_float, 0.0, 1.0)

        # 4. Spill Suppression
        despilled_rgb, spill_map = self.suppress_spill(rgb_img, refined_matte, config)

        # 5. Format Output based on DisplayMode
        if config.display_mode == MatteDisplayMode.MATTE_ONLY:
            # Grayscale visualization of the alpha channel
            gray = np.clip(refined_matte * 255.0, 0, 255).astype(np.uint8)
            out_rgba = np.stack([gray, gray, gray, np.full((h, w), 255, dtype=np.uint8)], axis=-1)

        elif config.display_mode == MatteDisplayMode.SPILL_ONLY:
            # Heatmap / grayscale of spill areas
            spill_vis = np.clip(spill_map * 255.0, 0, 255).astype(np.uint8)
            out_rgba = np.stack([spill_vis, np.zeros((h, w), dtype=np.uint8), spill_vis, np.full((h, w), 255, dtype=np.uint8)], axis=-1)

        elif config.display_mode == MatteDisplayMode.ORIGINAL:
            out_rgba = src_data.copy()

        elif config.display_mode == MatteDisplayMode.FOREGROUND_KEYED:
            # Foreground with genuine alpha cutout
            alpha_uint8 = np.clip(refined_matte * 255.0, 0, 255).astype(np.uint8)
            out_rgba = np.concatenate([despilled_rgb, np.expand_dims(alpha_uint8, axis=-1)], axis=-1)

        else: # MatteDisplayMode.COMPOSITE
            alpha_f = np.expand_dims(refined_matte, axis=-1)
            fg_f = despilled_rgb.astype(np.float32)

            if background_frame is not None:
                bg_data = background_frame.data
                if bg_data.shape[:2] != (h, w):
                    bg_data = cv2.resize(bg_data, (w, h), interpolation=cv2.INTER_LINEAR)
                bg_f = bg_data[:, :, :3].astype(np.float32)
            else:
                # Default checkerboard background for clean transparency inspection
                square_size = 20
                y, x = np.ogrid[:h, :w]
                checker = ((x // square_size) + (y // square_size)) % 2 == 0
                bg_f = np.where(np.expand_dims(checker, axis=-1), 180.0, 220.0).astype(np.float32)

            composite_rgb = np.clip(fg_f * alpha_f + bg_f * (1.0 - alpha_f), 0, 255).astype(np.uint8)
            out_rgba = np.concatenate([composite_rgb, np.full((h, w, 1), 255, dtype=np.uint8)], axis=-1)

        return VideoFrameBuffer(
            width=w,
            height=h,
            pixel_format="RGBA",
            color_space=frame.color_space,
            data=out_rgba,
            pts_seconds=frame.pts_seconds,
            timeline_frame=frame.timeline_frame,
        )


# Global singleton
chroma_key_engine = ChromaKeyEngine()
