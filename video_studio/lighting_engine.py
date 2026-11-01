"""OMNIA Video Studio — Lighting, Exposure & Relighting Engine (Module 29).

Implements:
1. Deterministic image-space global exposure, contrast, highlights, shadows, whites, blacks, gamma, and color temperature.
2. Parametric local lighting regions: radial, directional, and polygon masks with feathering and blend modes.
3. Extension interface for scene-aware relighting with clean fallback.
4. Alpha channel preservation and zero color shift distortion.
"""

from typing import Dict, Any, List, Optional, Tuple
import time
import logging
import math
import numpy as np
import cv2

from video_studio.effects_models import VideoFrameBuffer
from video_studio.lighting_models import (
    LightingEngineDocument,
    GlobalExposureTonalConfig,
    LocalLightRegion,
    LightType,
    LightBlendMode,
    RelightingEngineMode,
    LightingDiagnostics,
)

logger = logging.getLogger("omnia.video_studio.lighting_engine")


def apply_light_blend(
    base: np.ndarray,
    light: np.ndarray,
    mode: LightBlendMode,
    opacity: float = 1.0,
) -> np.ndarray:
    """Combines a base image [0, 1] with an illumination layer [0, 1] using light blend equations.
    Both base and light are float32 (H, W, 3).
    """
    if mode == LightBlendMode.ADD:
        # Linear Dodge: base + light
        blended = base + light
    elif mode == LightBlendMode.SCREEN:
        # Screen: 1 - (1 - base) * (1 - light)
        blended = 1.0 - (1.0 - base) * (1.0 - light)
    elif mode == LightBlendMode.SOFT_LIGHT:
        # Pegtop / Photoshop Soft Light:
        # If light <= 0.5: 2 * base * light + base^2 * (1 - 2*light)
        # If light > 0.5:  2 * base * (1 - light) + sqrt(base) * (2*light - 1)
        blended = np.where(
            light <= 0.5,
            2.0 * base * light + (base ** 2) * (1.0 - 2.0 * light),
            2.0 * base * (1.0 - light) + np.sqrt(np.maximum(base, 0.0)) * (2.0 * light - 1.0)
        )
    elif mode == LightBlendMode.OVERLAY:
        # Overlay: Screen if base > 0.5 else Multiply
        blended = np.where(
            base <= 0.5,
            2.0 * base * light,
            1.0 - 2.0 * (1.0 - base) * (1.0 - light)
        )
    elif mode == LightBlendMode.MULTIPLY:
        # Multiply / Shading
        blended = base * light
    elif mode == LightBlendMode.COLOR_DODGE:
        # Color Dodge: base / (1 - light)
        blended = np.where(light >= 0.999, 1.0, base / np.maximum(1.0 - light, 1e-4))
    else:
        blended = base + light

    if opacity < 1.0:
        return np.clip((1.0 - opacity) * base + opacity * blended, 0.0, 1.0)
    return np.clip(blended, 0.0, 1.0)


class VideoLightingEngine:
    """Core image processing engine for exposure, tonal shaping, and localized lighting."""

    def __init__(self):
        pass

    # -------------------------------------------------------------------------
    # 1. Global Exposure and Tonal Processing
    # -------------------------------------------------------------------------

    def apply_global_tonal(
        self,
        rgb: np.ndarray,
        config: GlobalExposureTonalConfig,
    ) -> np.ndarray:
        """Applies deterministic global exposure and tonal transformations.
        Input rgb: float32 in range [0.0, 1.0], shape (H, W, 3).
        """
        out = rgb.copy()

        # 1. Exposure compensation in EV stops (out = rgb * 2^EV)
        if abs(config.exposure_stops) > 1e-4:
            out *= (2.0 ** config.exposure_stops)

        # 2. Brightness offset
        if abs(config.brightness) > 1e-4:
            out += (config.brightness / 100.0)

        # 3. Contrast adjustment around pivot: (out - pivot) * contrast + pivot
        if abs(config.contrast - 1.0) > 1e-4:
            pivot = float(config.contrast_pivot)
            out = (out - pivot) * float(config.contrast) + pivot

        # 4. Color Temperature and Tint
        if abs(config.temperature) > 1e-4 or abs(config.tint) > 1e-4:
            t = config.temperature / 100.0
            tint = config.tint / 100.0
            # Warmth increases Red, decreases Blue
            out[:, :, 0] += t * 0.12
            out[:, :, 2] -= t * 0.12
            # Tint shifts Green vs Magenta
            out[:, :, 1] += tint * 0.10

        # Calculate Rec.709 Luma for tonal split adjustments
        luma = 0.2126 * out[:, :, 0] + 0.7152 * out[:, :, 1] + 0.0722 * out[:, :, 2]
        luma = np.expand_dims(luma, axis=-1)

        # 5. Highlights and Shadows
        if abs(config.highlights) > 1e-4:
            # Highlight weight activates smoothly above 0.5 luma
            h_weight = np.clip((luma - 0.5) * 2.0, 0.0, 1.0) ** 1.5
            out += h_weight * (config.highlights / 100.0) * 0.35

        if abs(config.shadows) > 1e-4:
            # Shadow weight activates smoothly below 0.5 luma
            s_weight = np.clip((0.5 - luma) * 2.0, 0.0, 1.0) ** 1.5
            out += s_weight * (config.shadows / 100.0) * 0.35

        # 6. Whites and Blacks (extreme tonal extremes)
        if abs(config.whites) > 1e-4:
            w_weight = np.clip((luma - 0.75) * 4.0, 0.0, 1.0) ** 2.0
            out += w_weight * (config.whites / 100.0) * 0.40

        if abs(config.blacks) > 1e-4:
            b_weight = np.clip((0.25 - luma) * 4.0, 0.0, 1.0) ** 2.0
            out += b_weight * (config.blacks / 100.0) * 0.40

        # 7. Gamma (Midtone power response)
        if abs(config.gamma - 1.0) > 1e-4:
            gamma_val = max(0.1, config.gamma)
            out = np.clip(out, 0.0, 1.0) ** (1.0 / gamma_val)

        # 8. Black-point and White-point remapping
        if config.black_point > 0.0 or config.white_point < 1.0:
            bp = float(np.clip(config.black_point, 0.0, 0.49))
            wp = float(np.clip(config.white_point, bp + 0.01, 1.0))
            out = np.clip((out - bp) / (wp - bp), 0.0, 1.0)

        return np.clip(out, 0.0, 1.0)

    # -------------------------------------------------------------------------
    # 2. Localized Light Region Mask Generation
    # -------------------------------------------------------------------------

    def generate_region_mask(
        self,
        height: int,
        width: int,
        region: LocalLightRegion,
    ) -> np.ndarray:
        """Generates a 2D float32 attenuation mask [0.0, 1.0] for the given light region."""
        mask = np.zeros((height, width), dtype=np.float32)

        cx = float(np.clip(region.pos_x, 0.0, 1.0) * width)
        cy = float(np.clip(region.pos_y, 0.0, 1.0) * height)
        rx = float(max(1e-4, region.radius_x) * width)
        ry = float(max(1e-4, region.radius_y) * height)

        if region.light_type == LightType.POINT_RADIAL or region.light_type == LightType.SPOTLIGHT:
            # Radial / Elliptical falloff grid
            y_indices, x_indices = np.indices((height, width), dtype=np.float32)
            dx = (x_indices - cx) / rx
            dy = (y_indices - cy) / ry

            # Handle rotation
            if abs(region.angle_deg) > 1e-3:
                rad = math.radians(region.angle_deg)
                cos_a, sin_a = math.cos(rad), math.sin(rad)
                rot_dx = dx * cos_a + dy * sin_a
                rot_dy = -dx * sin_a + dy * cos_a
                dx, dy = rot_dx, rot_dy

            norm_dist = np.sqrt(dx * dx + dy * dy)

            # Feather determines the inner solid vs outer falloff threshold
            feather = float(np.clip(region.feather, 0.01, 1.0))
            inner_thresh = 1.0 - feather
            
            # Smooth bell falloff using cosine or cubic smoothstep
            mask = np.where(
                norm_dist <= inner_thresh,
                1.0,
                np.where(
                    norm_dist >= 1.0,
                    0.0,
                    0.5 * (1.0 + np.cos(math.pi * (norm_dist - inner_thresh) / feather))
                )
            ).astype(np.float32)

            # If Spotlight, attenuate based on direction angle and cone angle
            if region.light_type == LightType.SPOTLIGHT:
                spot_angle = math.radians(region.direction_angle_deg)
                cone_half = math.radians(max(5.0, region.spot_cone_angle_deg) / 2.0)
                pixel_angle = np.arctan2(y_indices - cy, x_indices - cx)
                angle_diff = np.abs(np.arctan2(np.sin(pixel_angle - spot_angle), np.cos(pixel_angle - spot_angle)))
                cone_falloff = np.clip(1.0 - (angle_diff / cone_half), 0.0, 1.0)
                mask *= (cone_falloff ** 1.5)

        elif region.light_type == LightType.DIRECTIONAL:
            # Linear directional gradient across angle
            rad = math.radians(region.direction_angle_deg)
            cos_a, sin_a = math.cos(rad), math.sin(rad)
            y_indices, x_indices = np.indices((height, width), dtype=np.float32)
            
            # Distance along beam axis relative to center
            proj = (x_indices - cx) * cos_a + (y_indices - cy) * sin_a
            beam_span = max(rx, ry) * 2.0
            norm_proj = proj / beam_span + 0.5 # 0.0 to 1.0 across span
            mask = np.clip(1.0 - norm_proj, 0.0, 1.0)

            # Feather smoothing
            feather = float(np.clip(region.feather, 0.05, 1.0))
            mask = np.clip(mask / feather, 0.0, 1.0)
            mask = 0.5 * (1.0 - np.cos(math.pi * mask))

        elif region.light_type == LightType.POLYGON_MASK:
            # Polygon mask rasterization
            if len(region.polygon_points) >= 3:
                pts = np.array(
                    [[p[0] * width, p[1] * height] for p in region.polygon_points],
                    dtype=np.int32
                )
                poly_mask = np.zeros((height, width), dtype=np.uint8)
                cv2.fillPoly(poly_mask, [pts], 255)
                
                # Feathering with Gaussian blur
                feather_px = int(np.clip(region.feather * min(width, height) * 0.1, 1, 101))
                if feather_px % 2 == 0:
                    feather_px += 1
                poly_mask = cv2.GaussianBlur(poly_mask, (feather_px, feather_px), 0)
                mask = poly_mask.astype(np.float32) / 255.0
            else:
                mask.fill(1.0)

        # Inversion support
        if region.invert_mask:
            mask = 1.0 - mask

        return np.clip(mask, 0.0, 1.0)

    # -------------------------------------------------------------------------
    # 3. Local Light Layer Application
    # -------------------------------------------------------------------------

    def apply_local_light_region(
        self,
        base_rgb: np.ndarray,
        region: LocalLightRegion,
    ) -> np.ndarray:
        """Applies a single localized lighting region to base_rgb."""
        if not region.is_enabled or abs(region.intensity) < 1e-4:
            return base_rgb

        h, w = base_rgb.shape[:2]
        mask = self.generate_region_mask(h, w, region) # (H, W) in [0, 1]
        mask_3d = np.expand_dims(mask, axis=-1)

        # Light chromaticity
        cr, cg, cb = region.color_rgb
        # Apply local temperature shift if any
        if abs(region.color_temperature) > 1e-4:
            t_shift = region.color_temperature / 100.0
            cr = float(np.clip(cr + t_shift * 0.15, 0.0, 1.0))
            cb = float(np.clip(cb - t_shift * 0.15, 0.0, 1.0))

        light_color = np.array([cr, cg, cb], dtype=np.float32)

        # Intensity scaling: positive illuminates, negative shades/flags
        intensity = float(region.intensity)
        if intensity >= 0.0:
            # Emitted illumination layer
            light_layer = light_color * mask_3d * intensity
            result = apply_light_blend(base_rgb, light_layer, region.blend_mode, region.opacity)
        else:
            # Negative light / flagging: darken region smoothly
            flag_factor = np.clip(1.0 + (intensity * mask_3d * region.opacity), 0.0, 1.0)
            result = base_rgb * flag_factor

        return np.clip(result, 0.0, 1.0)

    # -------------------------------------------------------------------------
    # 4. Master Frame Processing
    # -------------------------------------------------------------------------

    def process_frame(
        self,
        frame: VideoFrameBuffer,
        doc: LightingEngineDocument,
        tracking_offset: Optional[Tuple[float, float]] = None,
    ) -> Tuple[VideoFrameBuffer, LightingDiagnostics]:
        """Executes full lighting and exposure processing pipeline.
        Returns the processed VideoFrameBuffer and LightingDiagnostics telemetry.
        """
        start_time = time.perf_counter()

        diagnostics = LightingDiagnostics(
            clip_id=doc.clip_id,
            frame_number=getattr(frame, "timeline_frame", 0),
            status="SUCCESS",
        )

        if not doc.is_enabled or frame.data is None:
            diagnostics.processing_time_ms = (time.perf_counter() - start_time) * 1000.0
            return frame, diagnostics

        out = frame.copy()
        raw = out.data

        has_alpha = (raw.shape[2] == 4)
        rgb = raw[:, :, :3].astype(np.float32) / 255.0
        alpha = raw[:, :, 3:] if has_alpha else None

        # Record initial luminance
        diagnostics.mean_luminance_before = float(np.mean(0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]))

        # Handle scene-aware relighting fallback explicitly
        if doc.engine_mode == RelightingEngineMode.SCENE_AWARE:
            if not doc.scene_aware.is_available:
                diagnostics.scene_aware_fallback_triggered = True
                logger.info(
                    f"Scene-aware AI relighting requested for clip '{doc.clip_id}', "
                    f"but model is unavailable ({doc.scene_aware.status_message}). "
                    "Falling back to deterministic 2D lighting."
                )

        # Step 1: Global Exposure & Tonal Corrections
        rgb = self.apply_global_tonal(rgb, doc.global_tone)

        # Step 2: Localized Light Regions (ordered top-to-bottom)
        active_count = 0
        for r in doc.light_regions[:16]: # Enforce maximum 16 regions limit
            if r.is_enabled:
                # Apply tracking offset if attached and provided
                if tracking_offset and r.tracking_session_id:
                    tx, ty = tracking_offset
                    r.pos_x = float(np.clip(r.pos_x + tx, 0.0, 1.0))
                    r.pos_y = float(np.clip(r.pos_y + ty, 0.0, 1.0))
                
                rgb = self.apply_local_light_region(rgb, r)
                active_count += 1

        diagnostics.active_regions_count = active_count

        # Diagnostics metrics
        diagnostics.clipping_underflow_pct = float(np.mean(rgb <= 0.0) * 100.0)
        diagnostics.clipping_overflow_pct = float(np.mean(rgb >= 1.0) * 100.0)
        diagnostics.mean_luminance_after = float(np.mean(0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]))

        # Convert back to uint8 [0, 255] and re-attach untouched alpha channel
        clamped_uint8 = np.clip(rgb * 255.0, 0, 255).astype(np.uint8)
        if has_alpha:
            out.data = np.concatenate([clamped_uint8, alpha], axis=-1)
        else:
            out.data = clamped_uint8

        diagnostics.processing_time_ms = (time.perf_counter() - start_time) * 1000.0
        return out, diagnostics


# Global singleton instance
video_lighting_engine = VideoLightingEngine()
