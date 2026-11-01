"""OMNIA Video Studio — Video Deblurring & Motion Blur Processing Models (Module 28).

Defines authoritative domain models for:
- BlurOperationType: DEBLUR_RESTORATION, MOTION_BLUR_GENERATION, MOTION_BLUR_REDUCTION.
- BlurKernelType: LINEAR_DIRECTIONAL, GAUSSIAN_DEFOCUS, ESTIMATED_MOTION_VECTOR.
- ShutterAngleMode: SHUTTER_180 (Standard Cinema), SHUTTER_90 (Crisp Action), SHUTTER_360 (Max Dreamy), CUSTOM.
- DeblurMethod: WIENER_DECONVOLUTION, REGULARIZED_INVERSE, LUCY_RICHARDSON.
- DeblurConfig: Complete configuration for deblurring, motion blur generation, and artifact mitigation.
- DeblurDiagnostics: Telemetry on kernel size, regularizer K, processing time, and metric gain.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import math


class BlurOperationType(str, Enum):
    DEBLUR_RESTORATION = "DEBLUR_RESTORATION"           # Wiener / Lucy-Richardson deconvolution to recover soft edges
    MOTION_BLUR_GENERATION = "MOTION_BLUR_GENERATION"   # Cinema shutter-angle synthetic motion blur from motion/direction
    MOTION_BLUR_REDUCTION = "MOTION_BLUR_REDUCTION"     # Conservative directional deconvolution based on motion velocity


class BlurKernelType(str, Enum):
    LINEAR_DIRECTIONAL = "LINEAR_DIRECTIONAL" # Linear motion PSF (length + angle)
    GAUSSIAN_DEFOCUS = "GAUSSIAN_DEFOCUS"     # Isotropic defocus blur PSF (radius)
    MOTION_VECTOR = "MOTION_VECTOR"           # Derived from Module 21 / 22 motion tracking vectors


class ShutterAngleMode(str, Enum):
    SHUTTER_90 = "SHUTTER_90"   # 90 degrees: fast shutter, tight trails, sharp combat/action
    SHUTTER_180 = "SHUTTER_180" # 180 degrees: natural cinematic motion blur cadence
    SHUTTER_270 = "SHUTTER_270" # 270 degrees: extended low-light exposure
    SHUTTER_360 = "SHUTTER_360" # 360 degrees: full frame duration smear
    CUSTOM = "CUSTOM"           # Arbitrary angle [1 to 360 degrees]


class DeblurMethod(str, Enum):
    WIENER_DECONVOLUTION = "WIENER_DECONVOLUTION" # Frequency-domain regularized Wiener filter
    LUCY_RICHARDSON = "LUCY_RICHARDSON"           # Iterative Bayesian deconvolution
    REGULARIZED_INVERSE = "REGULARIZED_INVERSE"   # Damped inverse spectral filter


@dataclass
class DeblurConfig:
    """Configuration for deblurring, motion blur generation, and reduction."""
    operation: BlurOperationType = BlurOperationType.MOTION_BLUR_GENERATION
    deblur_method: DeblurMethod = DeblurMethod.WIENER_DECONVOLUTION
    kernel_type: BlurKernelType = BlurKernelType.LINEAR_DIRECTIONAL

    # Deblurring & Deconvolution Parameters
    blur_length: float = 7.0              # Estimated blur path length in pixels [1.0 to 45.0]
    blur_angle_deg: float = 0.0           # Angle of blur trajectory [-180.0 to 180.0]
    regularization_k: float = 0.005       # Noise-to-signal ratio regularizer to prevent noise explosion [0.0001 to 0.1]
    iteration_count: int = 10             # Iteration count for iterative deconvolution

    # Motion Blur Generation Parameters
    shutter_mode: ShutterAngleMode = ShutterAngleMode.SHUTTER_180
    custom_shutter_deg: float = 180.0     # Shutter angle in degrees [1.0 to 360.0]
    blur_samples: int = 7                 # Number of temporal sub-samples across shutter opening [3 to 15]
    motion_scale: float = 1.0             # Scale factor on motion vectors / blur trail length [0.1 to 3.0]

    # Artifact & Halo Safeguards
    ringing_suppression: bool = True      # Suppress Gibbs ringing along high-contrast boundaries
    noise_coring_threshold: float = 3.0   # Protect flat/shadow noise from high-frequency amplification

    is_enabled: bool = True

    @property
    def effective_shutter_angle(self) -> float:
        if self.shutter_mode == ShutterAngleMode.SHUTTER_90:
            return 90.0
        elif self.shutter_mode == ShutterAngleMode.SHUTTER_180:
            return 180.0
        elif self.shutter_mode == ShutterAngleMode.SHUTTER_270:
            return 270.0
        elif self.shutter_mode == ShutterAngleMode.SHUTTER_360:
            return 360.0
        return float(self.custom_shutter_deg)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation": self.operation.value,
            "deblur_method": self.deblur_method.value,
            "kernel_type": self.kernel_type.value,
            "blur_length": round(self.blur_length, 2),
            "blur_angle_deg": round(self.blur_angle_deg, 2),
            "regularization_k": round(self.regularization_k, 5),
            "iteration_count": self.iteration_count,
            "shutter_mode": self.shutter_mode.value,
            "custom_shutter_deg": round(self.custom_shutter_deg, 2),
            "effective_shutter_angle": round(self.effective_shutter_angle, 2),
            "blur_samples": self.blur_samples,
            "motion_scale": round(self.motion_scale, 2),
            "ringing_suppression": self.ringing_suppression,
            "noise_coring_threshold": round(self.noise_coring_threshold, 2),
            "is_enabled": self.is_enabled,
        }


@dataclass
class DeblurDiagnostics:
    """Operational telemetry on deblurring or motion blur generation."""
    operation_performed: str
    kernel_size: Tuple[int, int]
    processing_time_ms: float
    psf_length: float
    psf_angle_deg: float
    ringing_suppressed: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation_performed": self.operation_performed,
            "kernel_size": list(self.kernel_size),
            "processing_time_ms": round(self.processing_time_ms, 2),
            "psf_length": round(self.psf_length, 2),
            "psf_angle_deg": round(self.psf_angle_deg, 2),
            "ringing_suppressed": self.ringing_suppressed,
        }
