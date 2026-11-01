"""OMNIA Video Studio — Lens Distortion, Optical Correction & Lens Profile Engine (Module 30).

Implements:
1. Inverse coordinate remapping using Brown-Conrady radial and tangential distortion models.
2. Channel-aware lateral chromatic aberration correction (radial red/blue channel warp).
3. Optical vignetting correction with radial gain modeling.
4. Safe border policies: CLAMP_EDGE, TRANSPARENT, REFLECT, and CROP_TO_VALID.
5. Alpha preservation and OpenCV remap acceleration.
"""

from typing import Dict, Any, List, Optional, Tuple
import time
import logging
import math
import numpy as np
import cv2

from video_studio.effects_models import VideoFrameBuffer
from video_studio.lens_models import (
    LensCorrectionConfig,
    LensModelType,
    BorderHandlingMode,
    LensDiagnostics,
)

logger = logging.getLogger("omnia.video_studio.lens_engine")


class VideoLensEngine:
    """Production-grade optical correction engine for geometric distortion, CA, and vignetting."""

    def __init__(self):
        # Cache for distortion map grids: (width, height, cache_key) -> (map_x, map_y)
        self._map_cache: Dict[Tuple[int, int, str], Tuple[np.ndarray, np.ndarray]] = {}

    def clear_cache(self) -> None:
        self._map_cache.clear()

    # -------------------------------------------------------------------------
    # 1. Coordinate Distortion Remapping
    # -------------------------------------------------------------------------

    def build_distortion_maps(
        self,
        width: int,
        height: int,
        config: LensCorrectionConfig,
        radial_scale: float = 1.0,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Builds float32 inverse coordinate lookup maps (map_x, map_y) for cv2.remap.
        
        The Brown-Conrady model maps undistorted normalized coordinates (x_u, y_u)
        to distorted coordinates in the source image (x_d, y_d):
        r^2 = x_u^2 + y_u^2
        radial = 1 + k1*r^2 + k2*r^4 + k3*r^6
        x_d = x_u * radial + (2*p1*x_u*y_u + p2*(r^2 + 2*x_u^2))
        y_d = y_u * radial + (p1*(r^2 + 2*y_u^2) + 2*p2*x_u*y_u)
        """
        # Principal point in pixels
        cx = float(config.center_x * width)
        cy = float(config.center_y * height)

        # Scale factor (e.g. half diagonal) for normalization
        diag = math.sqrt(width * width + height * height) / 2.0
        if diag < 1.0:
            diag = 1.0

        # Effective coefficients scaled by correction strength
        s = float(config.strength)
        k1 = float(config.k1 * s * radial_scale)
        k2 = float(config.k2 * s * radial_scale)
        k3 = float(config.k3 * s * radial_scale)
        p1 = float(config.p1 * s)
        p2 = float(config.p2 * s)

        # Build output pixel coordinate grid
        y_indices, x_indices = np.indices((height, width), dtype=np.float32)

        # If CROP_TO_VALID framing is requested, apply auto_crop_scale zoom around center
        if config.border_mode == BorderHandlingMode.CROP_TO_VALID and config.auto_crop_scale > 1.0:
            zoom = config.auto_crop_scale
            x_u = ((x_indices - cx) / zoom) / diag
            y_u = ((y_indices - cy) / zoom) / diag
        else:
            x_u = (x_indices - cx) / diag
            y_u = (y_indices - cy) / diag

        r2 = x_u * x_u + y_u * y_u

        # Radial term
        if config.model_type == LensModelType.FISHEYE_EQUIDISTANT:
            # Equidistant fisheye approximation: theta = atan(r), r_d = theta * (1 + k1*theta^2 + ...)
            r = np.sqrt(np.maximum(r2, 1e-8))
            theta = np.arctan(r)
            theta2 = theta * theta
            radial_term = np.where(r > 1e-5, (theta / r) * (1.0 + k1 * theta2 + k2 * (theta2 ** 2)), 1.0)
            x_d = x_u * radial_term
            y_d = y_u * radial_term
        else:
            # Standard Brown-Conrady polynomial
            radial_term = 1.0 + k1 * r2 + k2 * (r2 * r2) + k3 * (r2 * r2 * r2)
            # Tangential term
            tangential_x = 2.0 * p1 * x_u * y_u + p2 * (r2 + 2.0 * x_u * x_u)
            tangential_y = p1 * (r2 + 2.0 * y_u * y_u) + 2.0 * p2 * x_u * y_u

            x_d = x_u * radial_term + tangential_x
            y_d = y_u * radial_term + tangential_y

        # Denormalize back to pixel coordinates in source image
        map_x = (x_d * diag + cx).astype(np.float32)
        map_y = (y_d * diag + cy).astype(np.float32)

        return map_x, map_y

    # -------------------------------------------------------------------------
    # 2. Vignetting Correction
    # -------------------------------------------------------------------------

    def apply_vignetting_correction(
        self,
        rgb: np.ndarray,
        config: LensCorrectionConfig,
    ) -> np.ndarray:
        """Applies radial exposure compensation to counter optical falloff."""
        if not config.enable_vignette_correction or abs(config.vignette_gain) < 1e-4:
            return rgb

        h, w = rgb.shape[:2]
        cx = float(config.center_x * w)
        cy = float(config.center_y * h)
        diag = math.sqrt(w * w + h * h) / 2.0

        y_indices, x_indices = np.indices((h, w), dtype=np.float32)
        r = np.sqrt((x_indices - cx) ** 2 + (y_indices - cy) ** 2) / diag # 0 at center, ~1 at corners

        # Smooth polynomial falloff curve shaped by midpoint
        mid = float(np.clip(config.vignette_midpoint, 0.1, 0.9))
        falloff = (r / mid) ** 2.0 / (1.0 + (r / mid) ** 2.0)
        
        # Gain multiplier (clamped to prevent noise explosion)
        gain_map = 1.0 + falloff * float(np.clip(config.vignette_gain, 0.0, 3.0))
        gain_map_3d = np.expand_dims(gain_map, axis=-1)

        corrected = rgb * gain_map_3d
        return np.clip(corrected, 0.0, 1.0)

    # -------------------------------------------------------------------------
    # 3. Master Frame Processing
    # -------------------------------------------------------------------------

    def process_frame(
        self,
        frame: VideoFrameBuffer,
        config: LensCorrectionConfig,
    ) -> Tuple[VideoFrameBuffer, LensDiagnostics]:
        """Applies optical geometric distortion, chromatic aberration, and vignetting corrections."""
        start_time = time.perf_counter()

        diagnostics = LensDiagnostics(
            clip_id=config.clip_id,
            frame_number=getattr(frame, "timeline_frame", 0),
            status="SUCCESS",
        )

        if not config.is_enabled or frame.data is None:
            diagnostics.processing_time_ms = (time.perf_counter() - start_time) * 1000.0
            return frame, diagnostics

        out = frame.copy()
        raw = out.data
        h, w = raw.shape[:2]

        has_alpha = (raw.shape[2] == 4)
        rgb = raw[:, :, :3].astype(np.float32) / 255.0
        alpha = raw[:, :, 3:] if has_alpha else None

        # Determine OpenCV border mode
        if config.border_mode == BorderHandlingMode.CLAMP_EDGE:
            cv_border = cv2.BORDER_REPLICATE
            border_val = 0
        elif config.border_mode == BorderHandlingMode.REFLECT:
            cv_border = cv2.BORDER_REFLECT
            border_val = 0
        elif config.border_mode == BorderHandlingMode.TRANSPARENT:
            cv_border = cv2.BORDER_CONSTANT
            border_val = 0
        else: # CROP_TO_VALID
            cv_border = cv2.BORDER_REPLICATE
            border_val = 0

        # Step 1: Geometric Distortion & Chromatic Aberration Remapping
        has_distortion = (
            abs(config.k1) > 1e-5 or abs(config.k2) > 1e-5 or abs(config.k3) > 1e-5 or
            abs(config.p1) > 1e-5 or abs(config.p2) > 1e-5
        )

        if has_distortion or config.enable_ca_correction:
            diagnostics.distortion_applied = has_distortion

            if config.enable_ca_correction and (abs(config.ca_red_displacement) > 1e-4 or abs(config.ca_blue_displacement) > 1e-4):
                # Channel-aware lateral chromatic aberration warping
                diagnostics.ca_corrected = True
                
                # Green channel: baseline reference map
                map_x_g, map_y_g = self.build_distortion_maps(w, h, config, radial_scale=1.0)
                # Red channel: scaled radial distortion
                red_scale = 1.0 + (config.ca_red_displacement / 100.0)
                map_x_r, map_y_r = self.build_distortion_maps(w, h, config, radial_scale=red_scale)
                # Blue channel: scaled radial distortion
                blue_scale = 1.0 + (config.ca_blue_displacement / 100.0)
                map_x_b, map_y_b = self.build_distortion_maps(w, h, config, radial_scale=blue_scale)

                # Remap each channel independently
                r_warped = cv2.remap(rgb[:, :, 0], map_x_r, map_y_r, interpolation=cv2.INTER_LINEAR, borderMode=cv_border, borderValue=border_val)
                g_warped = cv2.remap(rgb[:, :, 1], map_x_g, map_y_g, interpolation=cv2.INTER_LINEAR, borderMode=cv_border, borderValue=border_val)
                b_warped = cv2.remap(rgb[:, :, 2], map_x_b, map_y_b, interpolation=cv2.INTER_LINEAR, borderMode=cv_border, borderValue=border_val)
                rgb = np.stack([r_warped, g_warped, b_warped], axis=-1)

                # Warp alpha with baseline map
                if has_alpha:
                    alpha_warped = cv2.remap(alpha, map_x_g, map_y_g, interpolation=cv2.INTER_LINEAR, borderMode=cv_border, borderValue=0)
                    if alpha_warped.ndim == 2:
                        alpha_warped = np.expand_dims(alpha_warped, axis=-1)
                    if config.border_mode == BorderHandlingMode.TRANSPARENT:
                        out_of_bounds = (map_x_g < 0) | (map_x_g >= w) | (map_y_g < 0) | (map_y_g >= h)
                        alpha_warped[out_of_bounds] = 0
                    alpha = alpha_warped

                # Max displacement telemetry
                diff_x = np.abs(map_x_g - np.indices((h, w), dtype=np.float32)[1])
                diff_y = np.abs(map_y_g - np.indices((h, w), dtype=np.float32)[0])
                diagnostics.max_displacement_pixels = float(np.max(np.sqrt(diff_x * diff_x + diff_y * diff_y)))

            else:
                # Monolithic full RGB remap
                map_x, map_y = self.build_distortion_maps(w, h, config, radial_scale=1.0)
                rgb = cv2.remap(rgb, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv_border, borderValue=border_val)

                if has_alpha:
                    alpha_warped = cv2.remap(alpha, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv_border, borderValue=0)
                    if alpha_warped.ndim == 2:
                        alpha_warped = np.expand_dims(alpha_warped, axis=-1)
                    if config.border_mode == BorderHandlingMode.TRANSPARENT:
                        out_of_bounds = (map_x < 0) | (map_x >= w) | (map_y < 0) | (map_y >= h)
                        alpha_warped[out_of_bounds] = 0
                    alpha = alpha_warped

                # Max displacement telemetry
                y_grid, x_grid = np.indices((h, w), dtype=np.float32)
                diff_x = np.abs(map_x - x_grid)
                diff_y = np.abs(map_y - y_grid)
                diagnostics.max_displacement_pixels = float(np.max(np.sqrt(diff_x * diff_x + diff_y * diff_y)))
                diagnostics.unmapped_border_pixels_pct = float(np.mean((map_x < 0) | (map_x >= w) | (map_y < 0) | (map_y >= h)) * 100.0)

        # Step 2: Optical Vignetting Correction
        if config.enable_vignette_correction:
            rgb = self.apply_vignetting_correction(rgb, config)
            diagnostics.vignette_corrected = True

        # Reassemble frame
        clamped_uint8 = np.clip(rgb * 255.0, 0, 255).astype(np.uint8)
        if has_alpha:
            out.data = np.concatenate([clamped_uint8, alpha], axis=-1)
        else:
            out.data = clamped_uint8

        diagnostics.processing_time_ms = (time.perf_counter() - start_time) * 1000.0
        return out, diagnostics


# Global singleton instance
video_lens_engine = VideoLensEngine()
