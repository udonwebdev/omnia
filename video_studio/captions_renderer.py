"""OMNIA Video Studio — Subtitle & Caption Text Renderer (Module 13).

Provides pixel-accurate, multi-language subtitle rendering:
- Renders subtitle cues onto RGBA video frame buffers
- Multi-line text wrapping with custom margins and safe-area constraints
- Background bounding boxes with customizable alpha transparency
- Outlines and drop-shadows for high-contrast legibility against bright/dark backgrounds
- Text alignment (LEFT, CENTER, RIGHT) and vertical placement (BOTTOM, TOP, CENTER)
- Unicode text support (Latin, Cyrillic, CJK, Arabic, etc.) via Pillow/PIL
- Integrates with Module 11 compositing and Module 7 playback viewer
"""

from typing import List, Optional, Tuple, Dict, Any
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import logging

from video_studio.effects_models import VideoFrameBuffer
from video_studio.captions_models import (
    SubtitleCue,
    SubtitleStyling,
    SubtitleAlignment,
    SubtitleVerticalPosition,
)

logger = logging.getLogger("Omnia.VideoStudio.CaptionsRenderer")

def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
    """Converts hex color code to (R, G, B) tuple."""
    hex_str = hex_str.lstrip("#")
    if len(hex_str) == 3:
        hex_str = "".join(c * 2 for c in hex_str)
    if len(hex_str) != 6:
        return (255, 255, 255)
    return (int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16))

class CaptionsRenderer:
    """Renders active subtitle cues into an RGBA layer buffer."""

    def __init__(self):
        self._font_cache: Dict[Tuple[str, int], Any] = {}

    def _get_font(self, font_family: str, size: int) -> Any:
        key = (font_family, size)
        if key in self._font_cache:
            return self._font_cache[key]

        font = None
        # Try system fonts or fallback to PIL default
        try:
            # On Windows, try loading standard system fonts
            for candidate in [f"{font_family}.ttf", f"arial.ttf", f"segoeui.ttf", "calibri.ttf"]:
                try:
                    font = ImageFont.truetype(candidate, size)
                    break
                except IOError:
                    continue
        except Exception:
            pass

        if font is None:
            font = ImageFont.load_default()

        self._font_cache[key] = font
        return font

    def render_subtitles_to_frame(
        self,
        cues: List[SubtitleCue],
        canvas_width: int,
        canvas_height: int,
        default_styling: Optional[SubtitleStyling] = None,
    ) -> VideoFrameBuffer:
        """Renders active subtitle cues onto a transparent RGBA VideoFrameBuffer."""
        if not cues:
            return VideoFrameBuffer.blank(canvas_width, canvas_height, color=(0, 0, 0, 0))

        # Create transparent PIL Image (RGBA)
        pil_img = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(pil_img)

        fallback_styling = default_styling or SubtitleStyling()

        for cue in cues:
            styling = cue.styling_override or fallback_styling
            text = cue.text
            if not text.strip():
                continue

            font = self._get_font(styling.font_family, styling.font_size)

            # Split into lines and compute line wrapping if line exceeds max_line_width
            raw_lines = text.split("\n")
            wrapped_lines: List[str] = []
            for rline in raw_lines:
                words = rline.split()
                if not words:
                    continue
                current_line = words[0]
                for w in words[1:]:
                    test_line = current_line + " " + w
                    bbox = draw.textbbox((0, 0), test_line, font=font)
                    w_px = bbox[2] - bbox[0]
                    if w_px <= styling.max_line_width:
                        current_line = test_line
                    else:
                        wrapped_lines.append(current_line)
                        current_line = w
                wrapped_lines.append(current_line)

            if not wrapped_lines:
                continue

            # Calculate total text block bounding box
            line_heights = []
            line_widths = []
            for l in wrapped_lines:
                bbox = draw.textbbox((0, 0), l, font=font)
                line_widths.append(bbox[2] - bbox[0])
                line_heights.append(bbox[3] - bbox[1])

            max_w = max(line_widths)
            total_h = sum(line_heights) + styling.line_spacing * (len(wrapped_lines) - 1)

            # Determine block position
            padding_x = 16
            padding_y = 10
            box_w = max_w + padding_x * 2
            box_h = total_h + padding_y * 2

            # Horizontal placement
            if styling.alignment == SubtitleAlignment.LEFT:
                pos_x = styling.margin_horizontal
            elif styling.alignment == SubtitleAlignment.RIGHT:
                pos_x = canvas_width - box_w - styling.margin_horizontal
            else:  # CENTER
                pos_x = (canvas_width - box_w) // 2

            # Vertical placement
            if styling.vertical_position == SubtitleVerticalPosition.TOP:
                pos_y = styling.margin_vertical
            elif styling.vertical_position == SubtitleVerticalPosition.CENTER:
                pos_y = (canvas_height - box_h) // 2
            else:  # BOTTOM (Standard)
                pos_y = canvas_height - box_h - styling.margin_vertical

            # Ensure safe bounds
            pos_x = max(10, min(canvas_width - box_w - 10, pos_x))
            pos_y = max(10, min(canvas_height - box_h - 10, pos_y))

            # Draw background bounding box if background_alpha > 0
            if styling.background_alpha > 0.0:
                bg_rgb = hex_to_rgb(styling.background_color)
                bg_a = int(round(styling.background_alpha * 255))
                box_shape = [
                    (pos_x, pos_y),
                    (pos_x + box_w, pos_y + box_h),
                ]
                draw.rounded_rectangle(box_shape, radius=8, fill=(bg_rgb[0], bg_rgb[1], bg_rgb[2], bg_a))

            # Draw each text line
            cur_y = pos_y + padding_y
            text_rgb = hex_to_rgb(styling.text_color)
            text_a = int(round(styling.text_alpha * 255))
            text_fill = (text_rgb[0], text_rgb[1], text_rgb[2], text_a)

            outline_rgb = hex_to_rgb(styling.outline_color)
            outline_fill = (outline_rgb[0], outline_rgb[1], outline_rgb[2], text_a)

            for idx, line in enumerate(wrapped_lines):
                lw = line_widths[idx]
                if styling.alignment == SubtitleAlignment.LEFT:
                    line_x = pos_x + padding_x
                elif styling.alignment == SubtitleAlignment.RIGHT:
                    line_x = pos_x + box_w - padding_x - lw
                else:  # CENTER
                    line_x = pos_x + (box_w - lw) // 2

                # Optional Outline
                if styling.outline_width > 0:
                    draw.text(
                        (line_x, cur_y),
                        line,
                        font=font,
                        fill=text_fill,
                        stroke_width=styling.outline_width,
                        stroke_fill=outline_fill,
                    )
                else:
                    draw.text((line_x, cur_y), line, font=font, fill=text_fill)

                cur_y += line_heights[idx] + styling.line_spacing

        # Convert PIL RGBA image to numpy array and VideoFrameBuffer
        arr = np.array(pil_img, dtype=np.uint8)
        return VideoFrameBuffer(canvas_width, canvas_height, data=arr)


# Global singleton
captions_renderer = CaptionsRenderer()
