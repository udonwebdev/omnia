"""OMNIA Video Studio — Color Grading Pipeline & Pixel Processor (Module 16).

Strictly ordered non-destructive color processing pipeline:
1. Input Normalization (uint8 -> float32 [0.0, 1.0]).
2. Working Color Space conversion.
3. Primary Correction:
   - Exposure (2^EV multiplier).
   - White Balance (Temperature and Tint chromatic adjustments).
   - Contrast & Pivot.
   - Highlights & Shadows shaping.
   - Saturation & Vibrance.
4. Three-Way Color Wheels (Lift, Gamma, Gain, Offset).
5. Tone Curves (Master RGB, Red, Green, Blue).
6. HSL Secondary Qualifier (targeted selection with feathering).
7. Creative 3D/1D LUT Application.
8. Output Clamping & Alpha Channel Reintegration.
9. Real-Time Scopes Measurement Generation (Histogram, Waveform, Vectorscope, Parade).
"""

from typing import Dict, Any, List, Optional, Tuple
import math
import numpy as np
import logging

from video_studio.color_models import (
    ColorGradeDocument,
    PrimaryGrade,
    LiftGammaGain,
    WheelBalance,
    ColorCurves,
    CurvePoint,
    HSLQualifier,
    ColorScopeData,
    ColorSpace,
)
from video_studio.color_lut import lut_processor, LUTProcessor
from video_studio.compositing_models import VideoFrameBuffer

logger = logging.getLogger("omnia.video_studio.color_pipeline")

class ColorPipelineProcessor:
    """Core image processing backend for real-time video color grading."""

    def process_frame(
        self,
        frame: VideoFrameBuffer,
        grade: ColorGradeDocument,
    ) -> VideoFrameBuffer:
        """Applies complete color grade pipeline to a VideoFrameBuffer."""
        if not grade.is_enabled or frame.data is None:
            return frame

        out = frame.copy()
        raw_data = out.data

        # Separate RGB and Alpha
        has_alpha = (raw_data.shape[2] == 4)
        rgb = raw_data[:, :, :3].astype(np.float32) / 255.0
        alpha = raw_data[:, :, 3:] if has_alpha else None

        # 1. Primary Adjustments
        rgb = self._apply_primary(rgb, grade.primary)

        # 2. Lift / Gamma / Gain Wheels
        rgb = self._apply_wheels(rgb, grade.wheels)

        # 3. Tone Curves
        rgb = self._apply_curves(rgb, grade.curves)

        # 4. HSL Secondary Qualification
        if grade.hsl_qualifier and grade.hsl_qualifier.is_enabled:
            rgb = self._apply_hsl_qualifier(rgb, grade.hsl_qualifier)

        # 5. LUT application
        if grade.lut and grade.lut.is_enabled:
            rgb = lut_processor.apply_lut(rgb, grade.lut)

        # 6. Clamp to valid [0, 1] range and convert back to uint8
        clamped_rgb = np.clip(rgb * 255.0, 0, 255).astype(np.uint8)

        if has_alpha:
            out.data = np.concatenate([clamped_rgb, alpha], axis=-1)
        else:
            out.data = clamped_rgb

        return out

    # ==========================================================================
    # 1. Primary Processing Engine
    # ==========================================================================

    def _apply_primary(self, rgb: np.ndarray, p: PrimaryGrade) -> np.ndarray:
        # Exposure: 2^EV
        if abs(p.exposure) > 1e-4:
            rgb *= (2.0 ** p.exposure)

        # Temperature & Tint
        if abs(p.temperature) > 1e-4 or abs(p.tint) > 1e-4:
            t = p.temperature / 100.0
            tint = p.tint / 100.0
            rgb[:, :, 0] += t * 0.1      # Warm (Red)
            rgb[:, :, 2] -= t * 0.1      # Cool (Blue)
            rgb[:, :, 1] += tint * 0.1   # Green vs Magenta

        # Contrast around Pivot + Brightness Offset
        if abs(p.contrast - 1.0) > 1e-4 or abs(p.brightness) > 1e-4:
            b_offset = p.brightness / 255.0
            rgb = (rgb - p.pivot) * p.contrast + p.pivot + b_offset

        # Highlights and Shadows shaping
        if abs(p.highlights) > 1e-4 or abs(p.shadows) > 1e-4:
            luma = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
            luma = np.expand_dims(luma, axis=-1)
            # Highlights weight: smooth ramp towards 1.0
            h_weight = np.clip((luma - 0.5) * 2.0, 0.0, 1.0)
            s_weight = np.clip((0.5 - luma) * 2.0, 0.0, 1.0)
            if abs(p.highlights) > 1e-4:
                rgb += h_weight * (p.highlights / 100.0) * 0.2
            if abs(p.shadows) > 1e-4:
                rgb += s_weight * (p.shadows / 100.0) * 0.2

        # Saturation in Rec.709 Luma space
        if abs(p.saturation - 1.0) > 1e-4:
            luma = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
            luma = np.expand_dims(luma, axis=-1)
            rgb = luma + p.saturation * (rgb - luma)

        # Vibrance (boosts lower saturated pixels more than highly saturated ones)
        if abs(p.vibrance) > 1e-4:
            vib = p.vibrance / 100.0
            max_c = np.max(rgb, axis=-1, keepdims=True)
            min_c = np.min(rgb, axis=-1, keepdims=True)
            sat = np.where(max_c > 1e-5, (max_c - min_c) / np.maximum(max_c, 1e-5), 0.0)
            boost = (1.0 - sat) * vib
            luma = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
            luma = np.expand_dims(luma, axis=-1)
            rgb = luma + (1.0 + boost) * (rgb - luma)

        return rgb

    # ==========================================================================
    # 2. Lift / Gamma / Gain Processing
    # ==========================================================================

    def _apply_wheels(self, rgb: np.ndarray, wheels: LiftGammaGain) -> np.ndarray:
        # Check identity
        w_lift = wheels.lift
        w_gamma = wheels.gamma
        w_gain = wheels.gain
        w_offset = wheels.offset

        # 1. Lift (Shadows): affects black point
        # Formula: out = rgb * (1 - lift) + lift
        lr = w_lift.r + w_lift.master
        lg = w_lift.g + w_lift.master
        lb = w_lift.b + w_lift.master
        if abs(lr) > 1e-4 or abs(lg) > 1e-4 or abs(lb) > 1e-4:
            lift_vec = np.array([lr, lg, lb], dtype=np.float32)
            rgb = rgb * (1.0 - lift_vec) + lift_vec

        # 2. Gain (Highlights): multiplies signal
        gr = 1.0 + w_gain.r + w_gain.master
        gg = 1.0 + w_gain.g + w_gain.master
        gb = 1.0 + w_gain.b + w_gain.master
        if abs(gr - 1.0) > 1e-4 or abs(gg - 1.0) > 1e-4 or abs(gb - 1.0) > 1e-4:
            gain_vec = np.array([gr, gg, gb], dtype=np.float32)
            rgb *= gain_vec

        # 3. Gamma (Midtones): power curve
        # midtone power = 1.0 / (1.0 + gamma)
        gam_r = 1.0 / max(0.1, 1.0 + w_gamma.r + w_gamma.master)
        gam_g = 1.0 / max(0.1, 1.0 + w_gamma.g + w_gamma.master)
        gam_b = 1.0 / max(0.1, 1.0 + w_gamma.b + w_gamma.master)
        if abs(gam_r - 1.0) > 1e-4 or abs(gam_g - 1.0) > 1e-4 or abs(gam_b - 1.0) > 1e-4:
            pos_rgb = np.maximum(0.0, rgb)
            rgb[:, :, 0] = pos_rgb[:, :, 0] ** gam_r
            rgb[:, :, 1] = pos_rgb[:, :, 1] ** gam_g
            rgb[:, :, 2] = pos_rgb[:, :, 2] ** gam_b

        # 4. Offset: uniform pedestal shift
        off_r = w_offset.r + w_offset.master
        off_g = w_offset.g + w_offset.master
        off_b = w_offset.b + w_offset.master
        if abs(off_r) > 1e-4 or abs(off_g) > 1e-4 or abs(off_b) > 1e-4:
            rgb += np.array([off_r, off_g, off_b], dtype=np.float32)

        return rgb

    # ==========================================================================
    # 3. Tone Curves
    # ==========================================================================

    def _apply_curves(self, rgb: np.ndarray, curves: ColorCurves) -> np.ndarray:
        # Apply master curve first
        if not self._is_identity_curve(curves.master):
            lut_m = self._generate_curve_lut(curves.master)
            rgb = np.interp(rgb, np.linspace(0.0, 1.0, 256), lut_m).astype(np.float32)

        # Apply per-channel curves
        if not self._is_identity_curve(curves.red):
            lut_r = self._generate_curve_lut(curves.red)
            rgb[:, :, 0] = np.interp(rgb[:, :, 0], np.linspace(0.0, 1.0, 256), lut_r).astype(np.float32)

        if not self._is_identity_curve(curves.green):
            lut_g = self._generate_curve_lut(curves.green)
            rgb[:, :, 1] = np.interp(rgb[:, :, 1], np.linspace(0.0, 1.0, 256), lut_g).astype(np.float32)

        if not self._is_identity_curve(curves.blue):
            lut_b = self._generate_curve_lut(curves.blue)
            rgb[:, :, 2] = np.interp(rgb[:, :, 2], np.linspace(0.0, 1.0, 256), lut_b).astype(np.float32)

        return rgb

    def _is_identity_curve(self, points: List[CurvePoint]) -> bool:
        if len(points) == 2 and abs(points[0].x) < 1e-4 and abs(points[0].y) < 1e-4 and abs(points[1].x - 1.0) < 1e-4 and abs(points[1].y - 1.0) < 1e-4:
            return True
        return False

    def _generate_curve_lut(self, points: List[CurvePoint]) -> np.ndarray:
        pts = sorted(points, key=lambda p: p.x)
        xs = [p.x for p in pts]
        ys = [p.y for p in pts]
        samples = np.linspace(0.0, 1.0, 256)
        return np.interp(samples, xs, ys).astype(np.float32)

    # ==========================================================================
    # 4. HSL Secondary Qualifier
    # ==========================================================================

    def _apply_hsl_qualifier(self, rgb: np.ndarray, q: HSLQualifier) -> np.ndarray:
        # Convert RGB to HSL
        r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
        max_c = np.maximum(np.maximum(r, g), b)
        min_c = np.minimum(np.minimum(r, g), b)
        delta = max_c - min_c

        luma = (max_c + min_c) * 0.5

        # Saturation
        sat = np.zeros_like(luma)
        mask_nonzero = delta > 1e-5
        sat[mask_nonzero] = np.where(
            luma[mask_nonzero] <= 0.5,
            delta[mask_nonzero] / (max_c[mask_nonzero] + min_c[mask_nonzero]),
            delta[mask_nonzero] / (2.0 - max_c[mask_nonzero] - min_c[mask_nonzero]),
        )

        # Hue in degrees [0, 360]
        hue = np.zeros_like(luma)
        r_eq = (max_c == r) & mask_nonzero
        g_eq = (max_c == g) & mask_nonzero & (~r_eq)
        b_eq = (max_c == b) & mask_nonzero & (~r_eq) & (~g_eq)

        hue[r_eq] = 60.0 * (((g[r_eq] - b[r_eq]) / delta[r_eq]) % 6)
        hue[g_eq] = 60.0 * (((b[g_eq] - r[g_eq]) / delta[g_eq]) + 2)
        hue[b_eq] = 60.0 * (((r[b_eq] - g[b_eq]) / delta[b_eq]) + 4)

        # Qualification Mask
        # 1. Hue window with wraparound
        half_w = q.hue_width * 0.5
        hue_diff = np.abs(hue - q.hue_center)
        hue_diff = np.minimum(hue_diff, 360.0 - hue_diff) # Circular distance
        hue_mask = np.clip(1.0 - (np.maximum(0.0, hue_diff - half_w) / max(1.0, q.hue_softness)), 0.0, 1.0)

        # 2. Saturation mask
        sat_mask = ((sat >= q.sat_min) & (sat <= q.sat_max)).astype(np.float32)

        # 3. Luma mask
        luma_mask = ((luma >= q.luma_min) & (luma <= q.luma_max)).astype(np.float32)

        total_mask = hue_mask * sat_mask * luma_mask
        mask_3d = np.expand_dims(total_mask, axis=-1)

        # Modify qualified pixels: Hue shift, Sat scale, Luma offset
        adjusted_rgb = rgb.copy()
        if abs(q.target_sat_scale - 1.0) > 1e-4:
            lum_3d = np.expand_dims(luma, axis=-1)
            adjusted_rgb = lum_3d + q.target_sat_scale * (adjusted_rgb - lum_3d)

        if abs(q.target_luma_offset) > 1e-4:
            adjusted_rgb += q.target_luma_offset

        # Blend targeted correction according to mask
        return rgb * (1.0 - mask_3d) + adjusted_rgb * mask_3d

    # ==========================================================================
    # 5. Scopes Measurement Generation
    # ==========================================================================

    def calculate_scopes(self, frame: VideoFrameBuffer) -> ColorScopeData:
        """Calculates real histogram, waveform, vectorscope, and parade measurements."""
        raw = frame.data[:, :, :3]
        h, w, _ = raw.shape

        # 1. Histogram (256 bins per channel)
        hist_r, _ = np.histogram(raw[:, :, 0], bins=256, range=(0, 256))
        hist_g, _ = np.histogram(raw[:, :, 1], bins=256, range=(0, 256))
        hist_b, _ = np.histogram(raw[:, :, 2], bins=256, range=(0, 256))

        luma = (0.2126 * raw[:, :, 0] + 0.7152 * raw[:, :, 1] + 0.0722 * raw[:, :, 2]).astype(np.uint8)
        hist_luma, _ = np.histogram(luma, bins=256, range=(0, 256))

        # 2. Waveform (column luma profile subsampled to 64 columns)
        step_x = max(1, w // 64)
        waveform_vals = []
        for col in range(0, w, step_x):
            waveform_vals.append(float(np.mean(luma[:, col])))

        # 3. Vectorscope (subsampled YCbCr chrominance points)
        # Cb = -0.1687 R - 0.3313 G + 0.5000 B
        # Cr =  0.5000 R - 0.4187 G - 0.0813 B
        step_xy = max(1, int(math.sqrt((h * w) / 512)))
        sample_r = raw[::step_xy, ::step_xy, 0].flatten().astype(np.float32)
        sample_g = raw[::step_xy, ::step_xy, 1].flatten().astype(np.float32)
        sample_b = raw[::step_xy, ::step_xy, 2].flatten().astype(np.float32)

        cb = (-0.1687 * sample_r - 0.3313 * sample_g + 0.5000 * sample_b) / 128.0
        cr = ( 0.5000 * sample_r - 0.4187 * sample_g - 0.0813 * sample_b) / 128.0
        vectorscope_pts = list(zip([float(x) for x in cb], [float(y) for y in cr]))

        # 4. RGB Parade
        parade_r = [float(np.mean(raw[:, col, 0])) for col in range(0, w, step_x)]
        parade_g = [float(np.mean(raw[:, col, 1])) for col in range(0, w, step_x)]
        parade_b = [float(np.mean(raw[:, col, 2])) for col in range(0, w, step_x)]

        return ColorScopeData(
            frame_timestamp=0.0,
            histogram_r=[int(x) for x in hist_r],
            histogram_g=[int(x) for x in hist_g],
            histogram_b=[int(x) for x in hist_b],
            histogram_luma=[int(x) for x in hist_luma],
            waveform_samples=waveform_vals,
            vectorscope_uv=vectorscope_pts,
            rgb_parade={"r": parade_r, "g": parade_g, "b": parade_b},
        )

# Global singleton
color_pipeline_processor = ColorPipelineProcessor()
