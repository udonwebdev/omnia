"""OMNIA Video Studio — Film Grain, Video Texture & Analog Emulation Engine (Module 31).

Implements:
1. Deterministic procedural grain generation using seeded numpy.random.Generator.
2. Fine vs. coarse spatial scaling (Gaussian micro-grain vs. downsampled/bilinear upscaled grain clusters).
3. Rec.709 Luma and Chroma split weighting.
4. Tonal response curve: differential weighting for shadows, midtones, and highlights.
5. Deterministic temporal grain modes: FIXED, FRAME_VARYING, and TEMPORALLY_COHERENT.
6. Optional analog texture operations:
   - Gate weave / jitter (subpixel affine translation)
   - Halation highlight glow (thresholded Gaussian bloom with red-orange tint)
   - Procedural dust specks and hairline vertical scratches
7. Byte-for-byte alpha preservation and numerical stability.
"""

from typing import Dict, Any, List, Optional, Tuple
import time
import logging
import math
import numpy as np
import cv2

from video_studio.effects_models import VideoFrameBuffer
from video_studio.grain_models import (
    FilmGrainConfig,
    GrainType,
    TemporalGrainMode,
    HalationMode,
    AnalogTextureConfig,
    GrainDiagnostics,
)

logger = logging.getLogger("omnia.video_studio.grain_engine")


class VideoGrainEngine:
    """Production-grade procedural film grain and analog texture generation engine."""

    def __init__(self):
        # Previous frame grain cache for TEMPORALLY_COHERENT mode: (clip_id, seed) -> noise_array
        self._coherent_noise_cache: Dict[str, np.ndarray] = {}

    def clear_cache(self) -> None:
        self._coherent_noise_cache.clear()

    # -------------------------------------------------------------------------
    # 1. Deterministic Noise Field Synthesis
    # -------------------------------------------------------------------------

    def generate_noise_field(
        self,
        height: int,
        width: int,
        channels: int,
        effective_seed: int,
        scale: float,
        grain_type: GrainType,
    ) -> np.ndarray:
        """Generates zero-mean normal/uniform noise field scaled to target spatial dimensions."""
        rng = np.random.default_rng(effective_seed)

        # Base scale clamped safely
        s = float(np.clip(scale, 0.5, 4.0))

        if abs(s - 1.0) < 1e-3:
            # 1:1 pixel grain
            if grain_type == GrainType.FINE:
                # Sharper, high-frequency distribution
                noise = rng.normal(0.0, 0.8, size=(height, width, channels)).astype(np.float32)
            else:
                noise = rng.normal(0.0, 1.0, size=(height, width, channels)).astype(np.float32)
        else:
            # Downsampled generation + bilinear interpolation for coarse grain clusters
            low_h = max(2, int(height / s))
            low_w = max(2, int(width / s))
            low_noise = rng.normal(0.0, 1.0, size=(low_h, low_w, channels)).astype(np.float32)
            noise = cv2.resize(low_noise, (width, height), interpolation=cv2.INTER_LINEAR)
            if channels == 1 and noise.ndim == 2:
                noise = np.expand_dims(noise, axis=-1)

        return noise

    # -------------------------------------------------------------------------
    # 2. Tonal Response Mask
    # -------------------------------------------------------------------------

    def compute_tonal_response_mask(
        self,
        luma: np.ndarray,
        config: FilmGrainConfig,
    ) -> np.ndarray:
        """Computes a float32 grain visibility mask [0.0, 1.0] across Shadows, Midtones, and Highlights.
        Luma is shape (H, W, 1) in range [0.0, 1.0].
        """
        # Shadow weight: high below 0.33
        shadow_ramp = np.clip((0.4 - luma) / 0.4, 0.0, 1.0) ** 1.5
        # Highlight weight: high above 0.66
        highlight_ramp = np.clip((luma - 0.6) / 0.4, 0.0, 1.0) ** 1.5
        # Midtone weight: smooth bell centered at 0.5
        midtone_ramp = np.clip(1.0 - 2.0 * np.abs(luma - 0.5), 0.0, 1.0) ** 1.5

        tonal_mask = (
            config.shadow_weight * shadow_ramp +
            config.midtone_weight * midtone_ramp +
            config.highlight_weight * highlight_ramp
        )
        return np.clip(tonal_mask, 0.0, 1.0)

    # -------------------------------------------------------------------------
    # 3. Analog Emulation Artifacts
    # -------------------------------------------------------------------------

    def apply_gate_weave(
        self,
        rgb: np.ndarray,
        alpha: Optional[np.ndarray],
        frame_idx: int,
        seed: int,
        tex: AnalogTextureConfig,
    ) -> Tuple[np.ndarray, Optional[np.ndarray]]:
        """Applies subtle subpixel affine vertical and horizontal frame jitter."""
        if not tex.enable_gate_weave or (abs(tex.weave_amplitude_x) < 1e-4 and abs(tex.weave_amplitude_y) < 1e-4):
            return rgb, alpha

        # Deterministic pseudo-random offset using trigonometric harmonics + seed
        t = frame_idx * tex.weave_frequency
        s_offset = (seed % 1000) * 0.1
        dx = math.sin(t * 0.45 + s_offset) * tex.weave_amplitude_x
        dy = math.cos(t * 0.72 + s_offset) * tex.weave_amplitude_y

        h, w = rgb.shape[:2]
        mat = np.array([[1.0, 0.0, dx], [0.0, 1.0, dy]], dtype=np.float32)

        warped_rgb = cv2.warpAffine(rgb, mat, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        warped_alpha = None
        if alpha is not None:
            warped_alpha = cv2.warpAffine(alpha, mat, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            if warped_alpha.ndim == 2:
                warped_alpha = np.expand_dims(warped_alpha, axis=-1)

        return warped_rgb, warped_alpha

    def apply_halation(
        self,
        rgb: np.ndarray,
        tex: AnalogTextureConfig,
    ) -> np.ndarray:
        """Applies photochemical halation bloom (red-orange glow on high-contrast edges)."""
        if tex.halation_mode == HalationMode.OFF or tex.halation_intensity < 1e-4:
            return rgb

        # Calculate luminance
        luma = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
        thresh = float(np.clip(tex.halation_threshold, 0.4, 0.99))
        
        # Isolate extreme specular highlights
        specular = np.clip((luma - thresh) / (1.0 - thresh + 1e-5), 0.0, 1.0)

        # Gaussian blur for soft halation halo
        k_radius = max(3, int(tex.halation_radius))
        if k_radius % 2 == 0:
            k_radius += 1
        specular_blurred = cv2.GaussianBlur(specular, (k_radius, k_radius), 0)
        specular_3d = np.expand_dims(specular_blurred, axis=-1)

        # Halation color tint
        if tex.halation_mode == HalationMode.RED_ORANGE:
            # Emulsion back-scatter color: predominantly Red with touch of Green, zero Blue
            glow_color = np.array([1.0, 0.22, 0.02], dtype=np.float32)
        else: # DIFFUSE_WHITE
            glow_color = np.array([1.0, 1.0, 1.0], dtype=np.float32)

        # Screen-blend halation glow onto RGB base
        glow_layer = specular_3d * glow_color * float(np.clip(tex.halation_intensity, 0.0, 1.0))
        result = 1.0 - (1.0 - rgb) * (1.0 - glow_layer)
        return np.clip(result, 0.0, 1.0)

    def apply_film_wear(
        self,
        rgb: np.ndarray,
        frame_idx: int,
        seed: int,
        tex: AnalogTextureConfig,
    ) -> np.ndarray:
        """Applies procedural dust particles and vertical emulsion scratches."""
        if not tex.enable_film_wear:
            return rgb

        h, w = rgb.shape[:2]
        out = rgb.copy()
        rng = np.random.default_rng(seed ^ (frame_idx * 7919))

        # 1. Procedural Dust specks (white/black specks)
        if tex.dust_density > 0.0:
            num_specks = int(w * h * min(0.005, tex.dust_density))
            if num_specks > 0:
                speck_x = rng.integers(0, w, size=num_specks)
                speck_y = rng.integers(0, h, size=num_specks)
                # Alternate between bright dust (1.0) and dark specks (0.0)
                colors = rng.choice([0.0, 0.95], size=num_specks)
                for i in range(num_specks):
                    px, py, col = speck_x[i], speck_y[i], colors[i]
                    out[py, px, :] = col
                    if py + 1 < h and px + 1 < w and rng.random() > 0.6:
                        out[py + 1, px, :] = col

        # 2. Vertical Hairline Scratches
        if tex.scratch_count > 0 and tex.scratch_intensity > 0.0:
            for s_idx in range(min(5, tex.scratch_count)):
                # Scratch position slowly wanders horizontally
                scratch_x = int((rng.integers(0, w) + (frame_idx % 30)) % w)
                intensity = float(np.clip(tex.scratch_intensity, 0.0, 1.0))
                # Slight wobble along vertical line
                for y in range(h):
                    wobble = int(math.sin(y * 0.05 + s_idx) * 0.7)
                    cx = np.clip(scratch_x + wobble, 0, w - 1)
                    # Semi-transparent translucent scratch
                    out[y, cx, :] = (1.0 - intensity * 0.6) * out[y, cx, :] + (intensity * 0.6) * 0.9

        return np.clip(out, 0.0, 1.0)

    # -------------------------------------------------------------------------
    # 4. Master Frame Processing
    # -------------------------------------------------------------------------

    def process_frame(
        self,
        frame: VideoFrameBuffer,
        config: FilmGrainConfig,
    ) -> Tuple[VideoFrameBuffer, GrainDiagnostics]:
        """Synthesizes film grain and analog textures onto input VideoFrameBuffer."""
        start_time = time.perf_counter()
        frame_idx = getattr(frame, "timeline_frame", 0)

        diagnostics = GrainDiagnostics(
            clip_id=config.clip_id,
            frame_number=frame_idx,
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

        # Determine effective temporal seed
        if config.temporal_mode == TemporalGrainMode.FIXED:
            effective_seed = int(config.base_seed)
        else: # FRAME_VARYING or TEMPORALLY_COHERENT
            effective_seed = int(config.base_seed) ^ (frame_idx * 31337)
        diagnostics.effective_seed = effective_seed

        # Step 1: Optional Gate Weave (subpixel jitter)
        if config.texture.enable_gate_weave:
            rgb, alpha = self.apply_gate_weave(rgb, alpha, frame_idx, config.base_seed, config.texture)
            diagnostics.gate_weave_applied = True

        # Step 2: Film Grain Synthesis
        if config.intensity > 1e-4:
            diagnostics.grain_applied = True

            # Calculate Rec.709 Luma for tonal split weighting: (H, W, 1)
            luma = np.expand_dims(
                0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2],
                axis=-1
            )
            tonal_mask = self.compute_tonal_response_mask(luma, config) # (H, W, 1)

            # Generate Luma noise field (monochromatic silver grain)
            luma_noise = self.generate_noise_field(
                height=h,
                width=w,
                channels=1,
                effective_seed=effective_seed,
                scale=config.scale,
                grain_type=config.grain_type,
            )

            # If TEMPORALLY_COHERENT, blend with previous cached noise field
            cache_key = f"{config.clip_id}_{config.base_seed}"
            if config.temporal_mode == TemporalGrainMode.TEMPORALLY_COHERENT and cache_key in self._coherent_noise_cache:
                prev_noise = self._coherent_noise_cache[cache_key]
                if prev_noise.shape == luma_noise.shape:
                    factor = float(np.clip(config.coherence_factor, 0.0, 0.9))
                    luma_noise = factor * prev_noise + (1.0 - factor) * luma_noise
            self._coherent_noise_cache[cache_key] = luma_noise

            # Overall grain delta: luma contribution
            grain_delta = luma_noise * config.luma_weight

            # Optional Chroma noise (color grain / dye cloud variation)
            if config.chroma_weight > 1e-4:
                chroma_seed = (effective_seed ^ 0x55AA55AA) & 0x7FFFFFFF
                chroma_noise = self.generate_noise_field(
                    height=h,
                    width=w,
                    channels=3,
                    effective_seed=chroma_seed,
                    scale=config.scale * 1.25, # Chroma dye clouds are slightly softer
                    grain_type=config.grain_type,
                )
                grain_delta = grain_delta + chroma_noise * config.chroma_weight

            # Scale grain delta by intensity and tonal response mask
            # Linear additive composite: rgb + grain_delta * intensity * tonal_mask
            scaled_delta = grain_delta * (config.intensity * 0.35) * tonal_mask
            rgb = np.clip(rgb + scaled_delta, 0.0, 1.0)

        # Step 3: Optional Emulsion Halation Glow
        if config.texture.halation_mode != HalationMode.OFF:
            rgb = self.apply_halation(rgb, config.texture)
            diagnostics.halation_applied = True

        # Step 4: Optional Procedural Dust & Scratches
        if config.texture.enable_film_wear:
            rgb = self.apply_film_wear(rgb, frame_idx, config.base_seed, config.texture)
            diagnostics.film_wear_applied = True

        # Convert back to uint8 and re-attach untouched alpha channel
        clamped_uint8 = np.clip(rgb * 255.0, 0, 255).astype(np.uint8)
        if has_alpha and alpha is not None:
            if alpha.ndim == 2:
                alpha = np.expand_dims(alpha, axis=-1)
            out.data = np.concatenate([clamped_uint8, alpha], axis=-1)
        else:
            out.data = clamped_uint8

        diagnostics.processing_time_ms = (time.perf_counter() - start_time) * 1000.0
        return out, diagnostics


# Global singleton instance
video_grain_engine = VideoGrainEngine()
