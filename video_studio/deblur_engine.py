"""OMNIA Video Studio — Video Deblurring & Motion Blur Processing Engine (Module 28).

Coordinates:
- Deblur Restoration:
  1. Regularized Wiener frequency-domain deconvolution:
     F_est = (H* / (|H|^2 + K)) * G
     Where H is the Point Spread Function (PSF), G is the blurry frame, and K prevents division by zero / noise explosion.
  2. Ringing & Gibbs artifact attenuation:
     Edge-tapering and overshoot clamping to prevent oscillatory fringes along high-contrast borders.
- Motion Blur Generation:
  1. Cinema shutter-angle synthetic motion blur from directional parameters or tracking vectors.
  2. Sub-frame temporal trajectory sampling across the shutter interval.
- Alpha channel preservation:
  - Alpha is filtered consistently or preserved intact.
"""

import time
import math
import logging
from typing import Dict, Any, List, Optional, Tuple

import cv2
import numpy as np

from video_studio.effects_models import VideoFrameBuffer
from video_studio.deblur_models import (
    BlurOperationType,
    BlurKernelType,
    ShutterAngleMode,
    DeblurMethod,
    DeblurConfig,
    DeblurDiagnostics,
)

logger = logging.getLogger("omnia.video_studio.deblur_engine")


class VideoDeblurEngine:
    """Core computer vision engine for deblurring, motion blur generation, and restoration."""

    # -------------------------------------------------------------------------
    # 1. Point Spread Function (PSF) Generation
    # -------------------------------------------------------------------------

    def create_motion_psf(
        self,
        length: float,
        angle_deg: float,
        kernel_size: Optional[int] = None,
    ) -> np.ndarray:
        """
        Creates a normalized linear motion Point Spread Function (PSF) kernel.
        """
        k_len = max(3, int(round(length)))
        if k_len % 2 == 0:
            k_len += 1
        size = kernel_size if kernel_size else max(k_len, 5)
        if size % 2 == 0:
            size += 1

        kernel = np.zeros((size, size), dtype=np.float32)
        center = size // 2

        # Draw line along angle
        theta = math.radians(angle_deg)
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)

        half_l = length / 2.0
        x1 = int(round(center - half_l * cos_t))
        y1 = int(round(center - half_l * sin_t))
        x2 = int(round(center + half_l * cos_t))
        y2 = int(round(center + half_l * sin_t))

        cv2.line(kernel, (x1, y1), (x2, y2), 1.0, thickness=1, lineType=cv2.LINE_AA)
        k_sum = np.sum(kernel)
        if k_sum > 1e-6:
            kernel /= k_sum
        else:
            kernel[center, center] = 1.0
        return kernel

    # -------------------------------------------------------------------------
    # 2. Deblurring / Deconvolution Implementations
    # -------------------------------------------------------------------------

    def wiener_deconvolution(
        self,
        channel: np.ndarray,
        psf: np.ndarray,
        k: float = 0.005,
        suppress_ringing: bool = True,
    ) -> np.ndarray:
        """
        Applies regularized Wiener deconvolution in the 2D Fourier domain.
        channel: 2D float32 image array [0.0, 1.0].
        """
        h, w = channel.shape
        kh, kw = psf.shape

        # Zero-pad PSF to match image dimensions
        psf_padded = np.zeros((h, w), dtype=np.float32)
        psf_padded[:kh, :kw] = psf

        # Circular shift PSF center to (0,0) for FFT alignment
        psf_padded = np.roll(psf_padded, -kh // 2, axis=0)
        psf_padded = np.roll(psf_padded, -kw // 2, axis=1)

        # Edge tapering to reduce boundary discontinuity Gibbs ringing
        if suppress_ringing:
            border = min(8, h // 8, w // 8)
            if border > 0:
                taper_y = np.ones(h, dtype=np.float32)
                taper_y[:border] = 0.5 * (1.0 - np.cos(np.linspace(0, np.pi, border)))
                taper_y[-border:] = taper_y[:border][::-1]

                taper_x = np.ones(w, dtype=np.float32)
                taper_x[:border] = 0.5 * (1.0 - np.cos(np.linspace(0, np.pi, border)))
                taper_x[-border:] = taper_x[:border][::-1]

                taper_mask = np.outer(taper_y, taper_x)
                mean_val = float(np.mean(channel))
                proc_channel = mean_val + (channel - mean_val) * taper_mask
            else:
                proc_channel = channel
        else:
            proc_channel = channel

        H = np.fft.fft2(psf_padded)
        G = np.fft.fft2(proc_channel)
        H_conj = np.conj(H)

        # Wiener transfer function
        F_est = (H_conj / (np.abs(H) ** 2 + k)) * G
        deblurred = np.real(np.fft.ifft2(F_est))

        if suppress_ringing:
            # Clamp overshoot against original channel bounds
            min_c = np.min(channel)
            max_c = np.max(channel)
            margin = 0.1 * (max_c - min_c + 1e-4)
            deblurred = np.clip(deblurred, min_c - margin, max_c + margin)

        return np.clip(deblurred, 0.0, 1.0)

    # -------------------------------------------------------------------------
    # 3. Motion Blur Generation
    # -------------------------------------------------------------------------

    def generate_motion_blur(
        self,
        rgb_img: np.ndarray,
        config: DeblurConfig,
        motion_vector: Optional[Tuple[float, float]] = None,
    ) -> np.ndarray:
        """
        Synthesizes cinema motion blur using shutter angle and directional trajectory or motion vector.
        """
        # Determine effective length and angle from shutter angle and motion
        shutter_factor = config.effective_shutter_angle / 180.0
        if motion_vector is not None:
            vx, vy = motion_vector
            length = math.sqrt(vx * vx + vy * vy) * config.motion_scale * shutter_factor
            angle_deg = math.degrees(math.atan2(vy, vx))
        else:
            length = config.blur_length * shutter_factor
            angle_deg = config.blur_angle_deg

        if length < 1.0:
            return rgb_img

        psf = self.create_motion_psf(length, angle_deg)
        blurred = cv2.filter2D(rgb_img, -1, psf, borderType=cv2.BORDER_REFLECT)
        return blurred

    # -------------------------------------------------------------------------
    # 4. Master Frame Processing Pipeline
    # -------------------------------------------------------------------------

    def process_frame(
        self,
        frame: VideoFrameBuffer,
        config: DeblurConfig,
        motion_vector: Optional[Tuple[float, float]] = None,
    ) -> Tuple[VideoFrameBuffer, DeblurDiagnostics]:
        """
        Executes deblurring, motion blur generation, or motion blur reduction.
        Preserves alpha channel untouched.
        """
        t0 = time.time()
        src_data = frame.data
        h, w = src_data.shape[:2]

        if not config.is_enabled:
            diag = DeblurDiagnostics(
                operation_performed="BYPASSED",
                kernel_size=(1, 1),
                processing_time_ms=0.0,
                psf_length=0.0,
                psf_angle_deg=0.0,
                ringing_suppressed=False,
            )
            return frame.copy(), diag

        rgb = src_data[:, :, :3]
        has_alpha = (src_data.shape[2] == 4)
        alpha = src_data[:, :, 3:] if has_alpha else None

        psf_len = config.blur_length
        psf_ang = config.blur_angle_deg

        if config.operation == BlurOperationType.MOTION_BLUR_GENERATION:
            shutter_factor = config.effective_shutter_angle / 180.0
            if motion_vector is not None:
                vx, vy = motion_vector
                psf_len = math.sqrt(vx * vx + vy * vy) * config.motion_scale * shutter_factor
                psf_ang = math.degrees(math.atan2(vy, vx))
            else:
                psf_len = config.blur_length * shutter_factor

            out_rgb = self.generate_motion_blur(rgb, config, motion_vector)
            psf = self.create_motion_psf(psf_len, psf_ang)
            k_size = psf.shape

        else: # DEBLUR_RESTORATION or MOTION_BLUR_REDUCTION
            # Determine PSF
            if motion_vector is not None and config.kernel_type == BlurKernelType.MOTION_VECTOR:
                vx, vy = motion_vector
                psf_len = max(2.0, math.sqrt(vx * vx + vy * vy))
                psf_ang = math.degrees(math.atan2(vy, vx))

            psf = self.create_motion_psf(psf_len, psf_ang)
            k_size = psf.shape

            # Process each RGB channel through Wiener deconvolution
            rgb_f = rgb.astype(np.float32) / 255.0
            deblurred_channels = []
            for c in range(3):
                deb_c = self.wiener_deconvolution(
                    rgb_f[:, :, c],
                    psf,
                    k=config.regularization_k,
                    suppress_ringing=config.ringing_suppression,
                )
                deblurred_channels.append(deb_c)

            out_rgb = np.clip(np.stack(deblurred_channels, axis=-1) * 255.0, 0, 255).astype(np.uint8)

        # Recombine with alpha
        if has_alpha and alpha is not None:
            out_data = np.concatenate([out_rgb, alpha], axis=-1)
        else:
            out_data = out_rgb

        t1 = time.time()
        elapsed_ms = (t1 - t0) * 1000.0

        diag = DeblurDiagnostics(
            operation_performed=config.operation.value,
            kernel_size=k_size,
            processing_time_ms=elapsed_ms,
            psf_length=psf_len,
            psf_angle_deg=psf_ang,
            ringing_suppressed=config.ringing_suppression,
        )

        out_buffer = VideoFrameBuffer(
            width=w,
            height=h,
            pixel_format="RGBA" if has_alpha else "RGB",
            color_space=frame.color_space,
            data=out_data,
            pts_seconds=frame.pts_seconds,
            timeline_frame=frame.timeline_frame,
        )
        return out_buffer, diag


# Global singleton
video_deblur_engine = VideoDeblurEngine()
