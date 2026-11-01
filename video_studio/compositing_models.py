"""OMNIA Video Studio — Multilayer Compositing, Blend Modes & Masking Models (Module 11).

Defines:
- BlendMode: NORMAL (Source-Over), MULTIPLY, SCREEN, ADD (Linear Dodge), DARKEN, LIGHTEN, DIFFERENCE, OVERLAY.
- MaskType: GRAYSCALE_LUMA, ALPHA_CHANNEL, INVERTED_LUMA, INVERTED_ALPHA.
- CompositingMask: Mask attachment definition (mask image/asset ID, strength, inversion, transform).
- CompositingGroup: Hierarchical grouping of tracks/layers with group-level opacity, isolation, and blend mode.
- LayerCompositingContext: Encapsulates canvas dimensions, background color/alpha, color space, and frame time.
- CompositorOutput: Mathematical source-over and blend-mode compositing algorithms.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import math
import numpy as np

from video_studio.effects_models import VideoFrameBuffer

# ==============================================================================
# 1. Blend Modes & Mask Types
# ==============================================================================

class BlendMode(str, Enum):
    NORMAL = "NORMAL"          # Standard Source-Over Porter-Duff
    MULTIPLY = "MULTIPLY"      # A * B
    SCREEN = "SCREEN"          # 1 - (1 - A) * (1 - B)
    ADD = "ADD"                # A + B (Linear Dodge)
    DARKEN = "DARKEN"          # min(A, B)
    LIGHTEN = "LIGHTEN"        # max(A, B)
    DIFFERENCE = "DIFFERENCE"  # abs(A - B)
    OVERLAY = "OVERLAY"        # Screen if B > 0.5 else Multiply

class MaskType(str, Enum):
    GRAYSCALE_LUMA = "GRAYSCALE_LUMA"
    ALPHA_CHANNEL = "ALPHA_CHANNEL"
    INVERTED_LUMA = "INVERTED_LUMA"
    INVERTED_ALPHA = "INVERTED_ALPHA"

# ==============================================================================
# 2. Mask & Group Contracts
# ==============================================================================

@dataclass
class CompositingMask:
    """Mask attached to a timeline clip or compositing group."""
    mask_id: str
    mask_type: MaskType = MaskType.GRAYSCALE_LUMA
    asset_id: Optional[str] = None # Reference to media asset for mask image
    mask_data: Optional[np.ndarray] = None # Explicit 2D/3D grayscale mask array
    strength: float = 1.0 # 0.0 to 1.0
    invert: bool = False
    is_enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mask_id": self.mask_id,
            "mask_type": self.mask_type.value,
            "asset_id": self.asset_id,
            "strength": self.strength,
            "invert": self.invert,
            "is_enabled": self.is_enabled,
        }

@dataclass
class CompositingGroup:
    """Isolated compositing group/folder for grouping tracks or clips."""
    group_id: str
    name: str = "Group"
    is_enabled: bool = True
    is_isolated: bool = True # Isolated renders to intermediate buffer before blending
    opacity: float = 1.0 # 0.0 to 1.0
    blend_mode: BlendMode = BlendMode.NORMAL
    mask: Optional[CompositingMask] = None
    child_track_ids: List[str] = field(default_factory=list)
    child_group_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "group_id": self.group_id,
            "name": self.name,
            "is_enabled": self.is_enabled,
            "is_isolated": self.is_isolated,
            "opacity": self.opacity,
            "blend_mode": self.blend_mode.value,
            "mask": self.mask.to_dict() if self.mask else None,
            "child_track_ids": list(self.child_track_ids),
            "child_group_ids": list(self.child_group_ids),
        }

# ==============================================================================
# 3. Mathematical Blend Mode Functions (Normalized Float [0.0, 1.0])
# ==============================================================================

def apply_blend_equation(fg: np.ndarray, bg: np.ndarray, mode: BlendMode) -> np.ndarray:
    """Calculates non-premultiplied RGB blend equation between foreground and background.
    Inputs: fg, bg in float32 [0.0, 1.0].
    """
    if mode == BlendMode.NORMAL:
        return fg
    elif mode == BlendMode.MULTIPLY:
        return fg * bg
    elif mode == BlendMode.SCREEN:
        return 1.0 - (1.0 - fg) * (1.0 - bg)
    elif mode == BlendMode.ADD:
        return np.clip(fg + bg, 0.0, 1.0)
    elif mode == BlendMode.DARKEN:
        return np.minimum(fg, bg)
    elif mode == BlendMode.LIGHTEN:
        return np.maximum(fg, bg)
    elif mode == BlendMode.DIFFERENCE:
        return np.abs(fg - bg)
    elif mode == BlendMode.OVERLAY:
        # 2 * A * B if B < 0.5 else 1 - 2*(1-A)*(1-B)
        mask = bg < 0.5
        res = np.empty_like(fg)
        res[mask] = 2.0 * fg[mask] * bg[mask]
        res[~mask] = 1.0 - 2.0 * (1.0 - fg[~mask]) * (1.0 - bg[~mask])
        return np.clip(res, 0.0, 1.0)
    return fg

def composite_layers_porter_duff(
    fg_buffer: VideoFrameBuffer,
    bg_buffer: VideoFrameBuffer,
    opacity: float = 1.0,
    blend_mode: BlendMode = BlendMode.NORMAL,
    mask: Optional[CompositingMask] = None,
) -> VideoFrameBuffer:
    """Mathematically correct Porter-Duff Source-Over alpha compositing with blend mode.
    
    Formula:
    alpha_fg = fg.alpha * opacity * mask_val
    alpha_out = alpha_fg + bg.alpha * (1 - alpha_fg)
    color_blended = blend_equation(fg.rgb, bg.rgb)
    color_out = (color_blended * alpha_fg + bg.rgb * bg.alpha * (1 - alpha_fg)) / max(alpha_out, 1e-6)
    """
    if fg_buffer.width != bg_buffer.width or fg_buffer.height != bg_buffer.height:
        # Resize foreground to match canvas
        import cv2
        fg_data = cv2.resize(fg_buffer.data, (bg_buffer.width, bg_buffer.height), interpolation=cv2.INTER_LINEAR)
    else:
        fg_data = fg_buffer.data

    bg_data = bg_buffer.data

    fg_rgb = fg_data[:, :, :3].astype(np.float32) / 255.0
    fg_a = (fg_data[:, :, 3].astype(np.float32) / 255.0) if fg_data.shape[2] == 4 else np.ones(fg_rgb.shape[:2], dtype=np.float32)

    bg_rgb = bg_data[:, :, :3].astype(np.float32) / 255.0
    bg_a = (bg_data[:, :, 3].astype(np.float32) / 255.0) if bg_data.shape[2] == 4 else np.ones(bg_rgb.shape[:2], dtype=np.float32)

    # 1. Apply layer opacity
    fg_a = fg_a * float(opacity)

    # 2. Apply Mask if present
    if mask and mask.is_enabled:
        if mask.mask_data is not None:
            # Resize mask array if needed
            m_arr = mask.mask_data
            if m_arr.shape[:2] != fg_a.shape:
                import cv2
                m_arr = cv2.resize(m_arr, (fg_buffer.width, fg_buffer.height), interpolation=cv2.INTER_LINEAR)
            
            if m_arr.ndim == 3 and m_arr.shape[2] >= 3:
                # Rec.709 Luma: 0.2126 R + 0.7152 G + 0.0722 B
                luma_m = 0.2126 * m_arr[:, :, 0] + 0.7152 * m_arr[:, :, 1] + 0.0722 * m_arr[:, :, 2]
            else:
                luma_m = m_arr.astype(np.float32)

            if luma_m.max() > 1.0:
                luma_m = luma_m / 255.0

            if mask.invert or mask.mask_type in (MaskType.INVERTED_LUMA, MaskType.INVERTED_ALPHA):
                luma_m = 1.0 - luma_m

            # Apply mask strength
            final_mask = (1.0 - mask.strength) + mask.strength * luma_m
            fg_a = fg_a * np.clip(final_mask, 0.0, 1.0)

    # 3. Calculate Blend Equation on RGB
    blended_rgb = apply_blend_equation(fg_rgb, bg_rgb, blend_mode)

    # 4. Porter-Duff Source-Over alpha calculation
    fg_a_expanded = np.expand_dims(fg_a, axis=-1)
    bg_a_expanded = np.expand_dims(bg_a, axis=-1)

    out_a = fg_a + bg_a * (1.0 - fg_a)
    out_a_expanded = np.expand_dims(out_a, axis=-1)

    safe_out_a = np.maximum(out_a_expanded, 1e-6)
    out_rgb = (blended_rgb * fg_a_expanded + bg_rgb * bg_a_expanded * (1.0 - fg_a_expanded)) / safe_out_a

    # 5. Pack into output buffer uint8
    clamped_rgb = np.clip(out_rgb * 255.0, 0, 255).astype(np.uint8)
    clamped_a = np.clip(out_a * 255.0, 0, 255).astype(np.uint8)
    clamped_a = np.expand_dims(clamped_a, axis=-1)

    out_data = np.concatenate([clamped_rgb, clamped_a], axis=-1)

    return VideoFrameBuffer(
        width=bg_buffer.width,
        height=bg_buffer.height,
        pixel_format="RGBA",
        color_space=bg_buffer.color_space,
        data=out_data,
        pts_seconds=bg_buffer.pts_seconds,
        timeline_frame=bg_buffer.timeline_frame,
    )
