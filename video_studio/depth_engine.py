"""OMNIA Video Studio — Video Depth Processing & 2.5D Engine (Module 32).

Implements deterministic algorithms for:
- Robust depth map normalization, NaN/Inf filtering, and value clamping
- Depth slicing & range matte generation with smooth cosine falloff
- Optical Depth-of-Field (DoF) defocus blur simulation
- 2.5D Camera Parallax displacement via inverse coordinate warping (cv2.remap)
- Depth-aware occlusion matte generation for virtual foreground/background layering
- Zero alpha channel corruption and strict boundary protection
"""

import math
import time
import numpy as np
import cv2
from typing import Tuple, Optional, Dict, Any

from video_studio.depth_models import (
    DepthMap,
    DepthEffectConfig,
    DepthDiagnostics,
    DepthEdgeMode,
    DepthRepresentationType,
)


def normalize_depth_map(
    raw_depth: np.ndarray,
    is_inverted: bool = False,
    scale: float = 1.0,
    offset: float = 0.0,
    clamp_min: float = 0.0,
    clamp_max: float = 1.0,
    diagnostics: Optional[DepthDiagnostics] = None,
) -> np.ndarray:
    """Sanitize and normalize any 2D depth array to strictly valid [0.0, 1.0] float32.
    
    Handles:
    - NaN and Inf detection and replacement with neutral 0.5 (or boundary depth).
    - Dynamic range normalization if raw values exceed [0, 1].
    - Scale and offset transforms.
    - Directional inversion (near becomes far, far becomes near).
    - Strict boundary clamping.
    """
    if raw_depth is None or raw_depth.size == 0:
        return np.zeros((1, 1), dtype=np.float32)

    # Convert to 2D float32
    depth = raw_depth.astype(np.float32)
    if depth.ndim == 3:
        if depth.shape[2] == 1:
            depth = depth[:, :, 0]
        else:
            # Grayscale extraction from 3-channel
            depth = cv2.cvtColor(depth, cv2.COLOR_BGR2GRAY if depth.shape[2] == 3 else cv2.COLOR_BGRA2GRAY)

    # Detect NaNs / Infs
    invalid_mask = ~np.isfinite(depth)
    invalid_count = int(np.count_nonzero(invalid_mask))
    if invalid_count > 0:
        depth = np.nan_to_num(depth, nan=0.5, posinf=1.0, neginf=0.0)

    # Telemetry before transform
    min_val = float(np.min(depth))
    max_val = float(np.max(depth))

    # If raw depth is outside [0.0, 1.0], auto-normalize range first
    if min_val < 0.0 or max_val > 1.0:
        span = max_val - min_val
        if span > 1e-6:
            depth = (depth - min_val) / span
        else:
            depth = np.full_like(depth, 0.5)

    # Apply user scale and offset
    if scale != 1.0 or offset != 0.0:
        depth = (depth * scale) + offset

    # Apply inversion if requested
    if is_inverted:
        depth = 1.0 - depth

    # Clamping
    pre_clamp_min = np.min(depth)
    pre_clamp_max = np.max(depth)
    clamped_count = int(np.count_nonzero((depth < clamp_min) | (depth > clamp_max)))
    depth = np.clip(depth, clamp_min, clamp_max)

    if diagnostics is not None:
        diagnostics.invalid_nan_inf_count += invalid_count
        diagnostics.clamped_pixel_count += clamped_count
        diagnostics.min_depth_encountered = min(diagnostics.min_depth_encountered, float(np.min(depth)))
        diagnostics.max_depth_encountered = max(diagnostics.max_depth_encountered, float(np.max(depth)))
        diagnostics.average_depth = float(np.mean(depth))
        if invalid_count > 0:
            diagnostics.warning_messages.append(f"Sanitized {invalid_count} invalid NaN/Inf pixels in depth map.")

    return depth


def generate_depth_range_mask(
    normalized_depth: np.ndarray,
    slice_near: float = 0.2,
    slice_far: float = 0.6,
    feather: float = 0.05,
) -> np.ndarray:
    """Generate a smooth float32 [0.0, 1.0] matte isolating objects in [slice_near, slice_far].
    
    Uses smooth cosine feathering at transitions to eliminate edge artifacts.
    """
    if normalized_depth is None or normalized_depth.size == 0:
        return np.ones((1, 1), dtype=np.float32)

    near = min(slice_near, slice_far)
    far = max(slice_near, slice_far)
    f = max(1e-5, feather)

    # Mask calculation
    # Between near and far: 1.0
    # Outside [near - f, far + f]: 0.0
    # Transitions smoothly with cosine ramp
    mask = np.zeros_like(normalized_depth, dtype=np.float32)

    # Core region
    core_idx = (normalized_depth >= near) & (normalized_depth <= far)
    mask[core_idx] = 1.0

    # Near feather ramp: from near-f to near
    if f > 0:
        near_ramp_idx = (normalized_depth >= (near - f)) & (normalized_depth < near)
        if np.any(near_ramp_idx):
            t_near = (normalized_depth[near_ramp_idx] - (near - f)) / f
            # 0.5 * (1 - cos(pi * t))
            mask[near_ramp_idx] = 0.5 * (1.0 - np.cos(np.pi * t_near))

        # Far feather ramp: from far to far+f
        far_ramp_idx = (normalized_depth > far) & (normalized_depth <= (far + f))
        if np.any(far_ramp_idx):
            t_far = ((far + f) - normalized_depth[far_ramp_idx]) / f
            mask[far_ramp_idx] = 0.5 * (1.0 - np.cos(np.pi * t_far))

    return np.clip(mask, 0.0, 1.0)


def apply_depth_of_field(
    frame_rgba: np.ndarray,
    normalized_depth: np.ndarray,
    focus_distance: float = 0.4,
    focal_range: float = 0.1,
    max_blur: float = 15.0,
    feather: float = 0.1,
) -> np.ndarray:
    """Apply depth-dependent optical defocus blur.
    
    Pixels within `focus_distance +/- focal_range/2` remain sharp.
    Blur magnitude scales with distance from the focal plane up to `max_blur`.
    Alpha channel is strictly preserved.
    """
    if frame_rgba is None or frame_rgba.size == 0:
        return frame_rgba

    h, w = frame_rgba.shape[:2]
    # Resize depth map if dimensions differ
    if normalized_depth.shape[:2] != (h, w):
        depth = cv2.resize(normalized_depth, (w, h), interpolation=cv2.INTER_LINEAR)
    else:
        depth = normalized_depth

    # Separate RGB and Alpha
    rgb = frame_rgba[:, :, :3]
    alpha = frame_rgba[:, :, 3:4] if frame_rgba.shape[2] == 4 else None

    # Calculate defocus factor [0.0, 1.0]
    half_range = max(1e-4, focal_range * 0.5)
    f = max(1e-4, feather)

    dist_from_focus = np.abs(depth - focus_distance)
    # Beyond focal range, ramp up defocus factor
    defocus = np.zeros_like(depth, dtype=np.float32)
    ramp_idx = dist_from_focus > half_range
    if np.any(ramp_idx):
        excess = dist_from_focus[ramp_idx] - half_range
        # Smooth ramp using tanh or linear clamp
        defocus[ramp_idx] = np.clip(excess / f, 0.0, 1.0)

    # Multi-tier pyramid blur approximation for speed and optical realism
    # Tier 1: Small blur
    # Tier 2: Medium blur
    # Tier 3: Strong blur
    k1 = max(3, int(round(max_blur * 0.3)) | 1)
    k2 = max(5, int(round(max_blur * 0.65)) | 1)
    k3 = max(7, int(round(max_blur)) | 1)

    blur1 = cv2.GaussianBlur(rgb, (k1, k1), 0)
    blur2 = cv2.GaussianBlur(rgb, (k2, k2), 0)
    blur3 = cv2.GaussianBlur(rgb, (k3, k3), 0)

    # Defocus map blending
    # 0.0 - 0.33 -> rgb to blur1
    # 0.33 - 0.66 -> blur1 to blur2
    # 0.66 - 1.0 -> blur2 to blur3
    defocus_3ch = np.repeat(defocus[:, :, np.newaxis], 3, axis=2)

    rgb_float = rgb.astype(np.float32)
    b1_float = blur1.astype(np.float32)
    b2_float = blur2.astype(np.float32)
    b3_float = blur3.astype(np.float32)

    # Piecewise continuous blend
    out_rgb = np.empty_like(rgb_float)

    mask1 = defocus_3ch <= 0.3333
    w1 = defocus_3ch / 0.3333
    out_rgb = np.where(mask1, (1.0 - w1) * rgb_float + w1 * b1_float, out_rgb)

    mask2 = (defocus_3ch > 0.3333) & (defocus_3ch <= 0.6666)
    w2 = (defocus_3ch - 0.3333) / 0.3333
    out_rgb = np.where(mask2, (1.0 - w2) * b1_float + w2 * b2_float, out_rgb)

    mask3 = defocus_3ch > 0.6666
    w3 = np.clip((defocus_3ch - 0.6666) / 0.3334, 0.0, 1.0)
    out_rgb = np.where(mask3, (1.0 - w3) * b2_float + w3 * b3_float, out_rgb)

    result_rgb = np.clip(out_rgb, 0, 255).astype(np.uint8)

    if alpha is not None:
        return np.concatenate([result_rgb, alpha], axis=2)
    return result_rgb


def apply_parallax_25d(
    frame_rgba: np.ndarray,
    normalized_depth: np.ndarray,
    shift_x: float = 0.0,
    shift_y: float = 0.0,
    focal_plane: float = 0.5,
    edge_mode: DepthEdgeMode = DepthEdgeMode.REPLICATE,
    diagnostics: Optional[DepthDiagnostics] = None,
) -> np.ndarray:
    """Simulate 2.5D camera displacement using inverse coordinate warping.
    
    Closer objects (lower depth) move more; background objects move less.
    At `focal_plane`, displacement is zero.
    
    Displacement law:
        dx(x, y) = shift_x * (depth(x, y) - focal_plane)
        dy(x, y) = shift_y * (depth(x, y) - focal_plane)
    Inverse map for cv2.remap:
        src_x = x - dx
        src_y = y - dy
    """
    if frame_rgba is None or frame_rgba.size == 0:
        return frame_rgba

    h, w = frame_rgba.shape[:2]
    if shift_x == 0.0 and shift_y == 0.0:
        return frame_rgba.copy()

    # Resize depth map if necessary
    if normalized_depth.shape[:2] != (h, w):
        depth = cv2.resize(normalized_depth, (w, h), interpolation=cv2.INTER_LINEAR)
    else:
        depth = normalized_depth

    # Base grid
    grid_y, grid_x = np.indices((h, w), dtype=np.float32)

    # Parallax differential: (focal_plane - depth)
    # Closer points (depth < focal_plane) shift in direction of movement
    diff = (focal_plane - depth)
    offset_x = shift_x * diff
    offset_y = shift_y * diff

    # Source coordinate mapping
    map_x = grid_x + offset_x
    map_y = grid_y + offset_y

    max_mag = float(np.max(np.sqrt(offset_x**2 + offset_y**2)))
    if diagnostics is not None:
        diagnostics.displacement_magnitude_max = max(diagnostics.displacement_magnitude_max, max_mag)

    # Border mode handling
    if edge_mode == DepthEdgeMode.REPLICATE or edge_mode == DepthEdgeMode.CLAMP:
        cv_border = cv2.BORDER_REPLICATE
        warped = cv2.remap(
            frame_rgba,
            map_x,
            map_y,
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv_border,
        )
        return warped
    elif edge_mode == DepthEdgeMode.TRANSPARENT:
        # Warp with transparent borders (borderValue=(0,0,0,0))
        warped = cv2.remap(
            frame_rgba,
            map_x,
            map_y,
            interpolation=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0, 0),
        )
        return warped

    return frame_rgba


def apply_depth_occlusion(
    foreground_rgba: np.ndarray,
    foreground_depth: np.ndarray,
    occlusion_plane: float = 0.5,
    softness: float = 0.02,
) -> np.ndarray:
    """Generate occlusion matte and modulate foreground alpha when occluded by virtual geometry.
    
    If foreground pixel depth > occlusion_plane, it is behind the plane and gets masked out.
    """
    if foreground_rgba is None or foreground_rgba.size == 0:
        return foreground_rgba

    h, w = foreground_rgba.shape[:2]
    if foreground_depth.shape[:2] != (h, w):
        depth = cv2.resize(foreground_depth, (w, h), interpolation=cv2.INTER_LINEAR)
    else:
        depth = foreground_depth

    s = max(1e-4, softness)
    # Visibility factor: 1.0 when depth < occlusion_plane (in front)
    # 0.0 when depth > occlusion_plane (behind)
    diff = depth - occlusion_plane
    visibility = 0.5 * (1.0 - np.clip(diff / s, -1.0, 1.0))

    out = foreground_rgba.copy()
    if out.shape[2] == 4:
        orig_alpha = out[:, :, 3].astype(np.float32)
        new_alpha = np.clip(orig_alpha * visibility, 0, 255).astype(np.uint8)
        out[:, :, 3] = new_alpha
    else:
        # Add alpha
        alpha = np.clip(visibility * 255.0, 0, 255).astype(np.uint8)
        out = np.concatenate([out, alpha[:, :, np.newaxis]], axis=2)

    return out


class VideoDepthEngine:
    """High-level engine orchestrating depth operations for a video frame."""

    def __init__(self):
        self.diagnostics = DepthDiagnostics()

    def process_frame(
        self,
        frame_rgba: np.ndarray,
        depth_map: Optional[DepthMap],
        config: DepthEffectConfig,
    ) -> Tuple[np.ndarray, DepthDiagnostics]:
        """Execute full depth-processing stack on an RGBA frame."""
        t_start = time.perf_counter()
        self.diagnostics.processed_frames += 1

        if not config.enabled or frame_rgba is None or frame_rgba.size == 0:
            self.diagnostics.last_process_duration_ms = (time.perf_counter() - t_start) * 1000.0
            return frame_rgba, self.diagnostics

        h, w = frame_rgba.shape[:2]

        # Check if depth map data exists
        if depth_map is None or depth_map.data is None:
            # Fallback: neutral uniform depth map
            self.diagnostics.fallback_used = True
            norm_depth = np.full((h, w), 0.5, dtype=np.float32)
        else:
            norm_depth = normalize_depth_map(
                depth_map.data,
                is_inverted=config.invert_depth or depth_map.is_inverted,
                scale=config.depth_scale,
                offset=config.depth_offset,
                clamp_min=config.clamp_min,
                clamp_max=config.clamp_max,
                diagnostics=self.diagnostics,
            )
            if norm_depth.shape[:2] != (h, w):
                norm_depth = cv2.resize(norm_depth, (w, h), interpolation=cv2.INTER_LINEAR)

        result = frame_rgba.copy()

        # 1. 2.5D Parallax Camera Displacement
        if config.enable_parallax and (config.parallax_shift_x != 0.0 or config.parallax_shift_y != 0.0):
            result = apply_parallax_25d(
                result,
                norm_depth,
                shift_x=config.parallax_shift_x,
                shift_y=config.parallax_shift_y,
                focal_plane=config.parallax_focal_plane,
                edge_mode=config.parallax_edge_mode,
                diagnostics=self.diagnostics,
            )

        # 2. Depth Slicing / Matte Isolation
        if config.enable_depth_slice:
            slice_mask = generate_depth_range_mask(
                norm_depth,
                slice_near=config.slice_near,
                slice_far=config.slice_far,
                feather=config.slice_feather,
            )
            # Modulate alpha
            if result.shape[2] == 4:
                alpha = result[:, :, 3].astype(np.float32) * slice_mask
                result[:, :, 3] = np.clip(alpha, 0, 255).astype(np.uint8)

        # 3. Depth of Field (DoF) Optical Blur
        if config.enable_dof and config.dof_max_blur > 0.0:
            result = apply_depth_of_field(
                result,
                norm_depth,
                focus_distance=config.dof_focus_distance,
                focal_range=config.dof_focal_range,
                max_blur=config.dof_max_blur,
                feather=config.dof_feather,
            )

        # 4. Depth-aware Occlusion
        if config.enable_occlusion:
            result = apply_depth_occlusion(
                result,
                norm_depth,
                occlusion_plane=config.occlusion_layer_depth,
                softness=config.occlusion_softness,
            )

        self.diagnostics.last_process_duration_ms = (time.perf_counter() - t_start) * 1000.0
        return result, self.diagnostics
