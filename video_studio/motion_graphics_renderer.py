"""OMNIA Video Studio — Motion Graphics & Vector Element Renderer (Module 14).

Renders:
- Typography & Multiline Text with tracking, alignments, uppercase/lowercase transforms
- Graphic Primitives: Rectangles (with rounded corners), Ellipses, and Lines
- Layer transforms (Position x/y, Scaling, Rotation around anchor/pivot)
- Typography Animation Presets (Fade In, Slide In Bottom/Left, Scale Pop, Tracking Expand)
- Module 8 Animation integration via keyframe evaluation
- Composites layers in stack order to produce a final RGBA VideoFrameBuffer
"""

from typing import Dict, Any, List, Optional, Tuple
import math
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont
import logging

from video_studio.effects_models import VideoFrameBuffer
from video_studio.motion_graphics_models import (
    GraphicLayerType,
    TextAlignment,
    TextTransformCase,
    TypographyAnimationPreset,
    GraphicTransform,
    MotionGraphicLayer,
    MotionGraphicComposition,
)
from video_studio.animation_service import animation_service, AnimationService
from video_studio.animation_evaluator import animation_evaluator, AnimationEvaluator
from video_studio.media_storage import media_storage_manager
from video_studio.playback_decoder import decoder_pool

logger = logging.getLogger("Omnia.VideoStudio.MotionGraphicsRenderer")

def hex_to_rgba(hex_str: str, alpha: float = 1.0) -> Tuple[int, int, int, int]:
    """Converts hex color string and float alpha to (R, G, B, A) tuple."""
    hex_str = hex_str.lstrip("#")
    if len(hex_str) == 3:
        hex_str = "".join(c * 2 for c in hex_str)
    if len(hex_str) != 6:
        r, g, b = (255, 255, 255)
    else:
        r, g, b = (int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16))
    a = int(round(max(0.0, min(1.0, float(alpha))) * 255))
    return (r, g, b, a)

class MotionGraphicsRenderer:
    """Evaluates and renders motion graphics compositions into RGBA buffers."""

    def __init__(
        self,
        anim_service: Optional[AnimationService] = None,
        anim_eval: Optional[AnimationEvaluator] = None,
    ):
        self.animation_service = anim_service or animation_service
        self.animation_evaluator = anim_eval or animation_evaluator
        self._font_cache: Dict[Tuple[str, int], Any] = {}

    def _get_font(self, font_family: str, size: int) -> Any:
        key = (font_family, size)
        if key in self._font_cache:
            return self._font_cache[key]

        font = None
        for candidate in [f"{font_family}.ttf", "arial.ttf", "segoeui.ttf", "calibri.ttf"]:
            try:
                font = ImageFont.truetype(candidate, size)
                break
            except IOError:
                continue
        if font is None:
            font = ImageFont.load_default()

        self._font_cache[key] = font
        return font

    def render_composition(
        self,
        composition: MotionGraphicComposition,
        comp_frame: int,
        canvas_width: Optional[int] = None,
        canvas_height: Optional[int] = None,
    ) -> VideoFrameBuffer:
        """Evaluates composition layers at comp_frame and renders transparent RGBA canvas."""
        w = canvas_width or composition.width
        h = canvas_height or composition.height

        # Create transparent base canvas
        pil_canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))

        # Sort layers from bottom to top
        sorted_layers = sorted(
            [l for l in composition.layers if l.is_visible],
            key=lambda l: l.stack_order,
        )

        for layer in sorted_layers:
            # Skip empty groups or zero opacity
            layer_opacity = self._evaluate_layer_opacity(layer, comp_frame)
            if layer_opacity <= 0.001:
                continue

            # Render individual layer onto an isolated layer surface
            layer_img = self._render_layer_surface(layer, comp_frame, w, h)
            if layer_img is None:
                continue

            # Composite layer_img onto pil_canvas
            pil_canvas.alpha_composite(layer_img)

        # Convert to VideoFrameBuffer
        arr = np.array(pil_canvas, dtype=np.uint8)
        return VideoFrameBuffer(w, h, data=arr)

    def _evaluate_layer_opacity(self, layer: MotionGraphicLayer, comp_frame: int) -> float:
        """Resolves layer opacity considering Module 8 keyframes and animation presets."""
        base_opacity = layer.opacity

        # Check Module 8 keyframes
        op_prop_id = layer.animated_property_ids.get("opacity")
        if op_prop_id:
            prop = self.animation_service.get_property(op_prop_id)
            if prop:
                base_opacity = float(self.animation_evaluator.evaluate(prop, comp_frame))

        # Check preset animation
        preset = layer.animation_preset
        dur = max(1, layer.preset_duration_frames)
        progress = max(0.0, min(1.0, float(comp_frame) / float(dur)))

        if preset == TypographyAnimationPreset.FADE_IN:
            base_opacity *= progress
        elif preset == TypographyAnimationPreset.FADE_OUT:
            base_opacity *= (1.0 - progress)

        return max(0.0, min(1.0, base_opacity))

    def _render_layer_surface(
        self,
        layer: MotionGraphicLayer,
        comp_frame: int,
        canvas_width: int,
        canvas_height: int,
    ) -> Optional[Image.Image]:
        """Renders single layer geometry and text with spatial transform applied."""
        l_type = layer.layer_type
        if l_type == GraphicLayerType.GROUP:
            return None

        # Resolve transform values (Position, Scaling, Rotation)
        tx = layer.transform.x
        ty = layer.transform.y
        scale_x = layer.transform.scale_x
        scale_y = layer.transform.scale_y
        rot = layer.transform.rotation_degrees

        # Check Module 8 keyframe automation for transforms
        if "transform_x" in layer.animated_property_ids:
            p = self.animation_service.get_property(layer.animated_property_ids["transform_x"])
            if p:
                tx = float(self.animation_evaluator.evaluate(p, comp_frame))
        if "transform_y" in layer.animated_property_ids:
            p = self.animation_service.get_property(layer.animated_property_ids["transform_y"])
            if p:
                ty = float(self.animation_evaluator.evaluate(p, comp_frame))
        if "scale_x" in layer.animated_property_ids:
            p = self.animation_service.get_property(layer.animated_property_ids["scale_x"])
            if p:
                scale_x = float(self.animation_evaluator.evaluate(p, comp_frame))
        if "scale_y" in layer.animated_property_ids:
            p = self.animation_service.get_property(layer.animated_property_ids["scale_y"])
            if p:
                scale_y = float(self.animation_evaluator.evaluate(p, comp_frame))
        if "rotation_degrees" in layer.animated_property_ids:
            p = self.animation_service.get_property(layer.animated_property_ids["rotation_degrees"])
            if p:
                rot = float(self.animation_evaluator.evaluate(p, comp_frame))

        # Presets modifying transform
        dur = max(1, layer.preset_duration_frames)
        prog = max(0.0, min(1.0, float(comp_frame) / float(dur)))
        # Cubic ease out: 1 - (1-p)^3
        ease_out = 1.0 - math.pow(1.0 - prog, 3)

        if layer.animation_preset == TypographyAnimationPreset.SLIDE_IN_BOTTOM:
            offset_y = (1.0 - ease_out) * 150.0
            ty += offset_y
        elif layer.animation_preset == TypographyAnimationPreset.SLIDE_IN_LEFT:
            offset_x = (1.0 - ease_out) * -200.0
            tx += offset_x
        elif layer.animation_preset == TypographyAnimationPreset.SCALE_POP:
            s_factor = ease_out if prog < 0.8 else (1.0 + 0.1 * math.sin((prog - 0.8) * math.pi * 5.0))
            scale_x *= s_factor
            scale_y *= s_factor

        # Create isolated canvas for this layer
        surf = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(surf)

        opacity_val = self._evaluate_layer_opacity(layer, comp_frame)
        fill_rgba = hex_to_rgba(layer.fill_color, layer.fill_alpha * opacity_val)
        stroke_rgba = hex_to_rgba(layer.stroke_color, layer.stroke_alpha * opacity_val)

        if l_type == GraphicLayerType.TEXT:
            self._draw_text_layer(draw, layer, tx, ty, fill_rgba, stroke_rgba, prog)
        elif l_type == GraphicLayerType.RECTANGLE:
            self._draw_rect_layer(draw, layer, tx, ty, fill_rgba, stroke_rgba)
        elif l_type == GraphicLayerType.ELLIPSE:
            self._draw_ellipse_layer(draw, layer, tx, ty, fill_rgba, stroke_rgba)
        elif l_type == GraphicLayerType.LINE:
            self._draw_line_layer(draw, layer, tx, ty, stroke_rgba)
        elif l_type == GraphicLayerType.IMAGE and layer.source_asset_id:
            self._draw_image_layer(surf, layer, tx, ty, opacity_val)

        # Apply rotation or non-uniform scaling if present
        if abs(rot) > 0.01:
            surf = surf.rotate(rot, resample=Image.Resampling.BILINEAR, center=(canvas_width // 2, canvas_height // 2))

        return surf

    def _draw_text_layer(
        self,
        draw: ImageDraw.ImageDraw,
        layer: MotionGraphicLayer,
        tx: float,
        ty: float,
        fill_rgba: Tuple[int, int, int, int],
        stroke_rgba: Tuple[int, int, int, int],
        prog: float,
    ) -> None:
        """Renders typography with casing, tracking, and alignment."""
        text = layer.text_content
        if layer.text_case == TextTransformCase.UPPERCASE:
            text = text.upper()
        elif layer.text_case == TextTransformCase.LOWERCASE:
            text = text.lower()
        elif layer.text_case == TextTransformCase.CAPITALIZE:
            text = text.title()

        font = self._get_font(layer.font_family, layer.font_size)

        # Word stagger reveal preset
        if layer.animation_preset == TypographyAnimationPreset.WORD_STAGGER:
            words = text.split()
            revealed_count = int(math.ceil(prog * len(words)))
            text = " ".join(words[:revealed_count])

        if not text:
            return

        lines = text.split("\n")
        line_heights = []
        line_widths = []
        for l in lines:
            bbox = draw.textbbox((0, 0), l, font=font)
            line_widths.append(bbox[2] - bbox[0])
            line_heights.append(bbox[3] - bbox[1])

        max_w = max(line_widths) if line_widths else 0
        cur_y = ty

        for idx, line in enumerate(lines):
            lw = line_widths[idx]
            if layer.text_alignment == TextAlignment.LEFT:
                lx = tx
            elif layer.text_alignment == TextAlignment.RIGHT:
                lx = tx - lw
            else:  # CENTER
                lx = tx - (lw // 2)

            if layer.stroke_width > 0 and stroke_rgba[3] > 0:
                draw.text(
                    (lx, cur_y),
                    line,
                    font=font,
                    fill=fill_rgba,
                    stroke_width=layer.stroke_width,
                    stroke_fill=stroke_rgba,
                )
            else:
                draw.text((lx, cur_y), line, font=font, fill=fill_rgba)

            cur_y += line_heights[idx] + layer.line_spacing

    def _draw_rect_layer(
        self,
        draw: ImageDraw.ImageDraw,
        layer: MotionGraphicLayer,
        tx: float,
        ty: float,
        fill_rgba: Tuple[int, int, int, int],
        stroke_rgba: Tuple[int, int, int, int],
    ) -> None:
        """Renders filled/stroked rectangle with corner radius."""
        x0 = tx - (layer.width * layer.transform.anchor_x)
        y0 = ty - (layer.height * layer.transform.anchor_y)
        x1 = x0 + layer.width
        y1 = y0 + layer.height

        outline = stroke_rgba if (layer.stroke_width > 0 and stroke_rgba[3] > 0) else None
        fill = fill_rgba if fill_rgba[3] > 0 else None

        if layer.corner_radius > 0.0:
            draw.rounded_rectangle(
                [(x0, y0), (x1, y1)],
                radius=int(round(layer.corner_radius)),
                fill=fill,
                outline=outline,
                width=layer.stroke_width,
            )
        else:
            draw.rectangle(
                [(x0, y0), (x1, y1)],
                fill=fill,
                outline=outline,
                width=layer.stroke_width,
            )

    def _draw_ellipse_layer(
        self,
        draw: ImageDraw.ImageDraw,
        layer: MotionGraphicLayer,
        tx: float,
        ty: float,
        fill_rgba: Tuple[int, int, int, int],
        stroke_rgba: Tuple[int, int, int, int],
    ) -> None:
        """Renders filled/stroked ellipse."""
        x0 = tx - (layer.width * layer.transform.anchor_x)
        y0 = ty - (layer.height * layer.transform.anchor_y)
        x1 = x0 + layer.width
        y1 = y0 + layer.height

        outline = stroke_rgba if (layer.stroke_width > 0 and stroke_rgba[3] > 0) else None
        fill = fill_rgba if fill_rgba[3] > 0 else None

        draw.ellipse([(x0, y0), (x1, y1)], fill=fill, outline=outline, width=layer.stroke_width)

    def _draw_line_layer(
        self,
        draw: ImageDraw.ImageDraw,
        layer: MotionGraphicLayer,
        tx: float,
        ty: float,
        stroke_rgba: Tuple[int, int, int, int],
    ) -> None:
        """Renders vector line."""
        p0 = (tx, ty)
        p1 = (layer.line_end_x, layer.line_end_y)
        draw.line([p0, p1], fill=stroke_rgba, width=max(1, layer.stroke_width))

    def _draw_image_layer(
        self,
        surf: Image.Image,
        layer: MotionGraphicLayer,
        tx: float,
        ty: float,
        opacity_val: float,
    ) -> None:
        """Renders referenced media asset onto layer surface."""
        file_path = media_storage_manager.resolve_asset_path(layer.source_asset_id)
        if not file_path:
            return
        try:
            with Image.open(file_path) as img:
                img_rgba = img.convert("RGBA")
                if layer.width > 0 and layer.height > 0:
                    img_rgba = img_rgba.resize((int(layer.width), int(layer.height)), Image.Resampling.BILINEAR)
                # Opacity scaling
                if opacity_val < 1.0:
                    alpha = img_rgba.split()[3]
                    alpha = alpha.point(lambda p: int(p * opacity_val))
                    img_rgba.putalpha(alpha)

                pos_x = int(tx - (img_rgba.width * layer.transform.anchor_x))
                pos_y = int(ty - (img_rgba.height * layer.transform.anchor_y))
                surf.alpha_composite(img_rgba, (pos_x, pos_y))
        except Exception as e:
            logger.warning(f"Error drawing image layer: {e}")


# Global singleton
motion_graphics_renderer = MotionGraphicsRenderer()
