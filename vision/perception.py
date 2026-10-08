import time
import re
import logging
from typing import List
from vision.models import (
    VisionFrame,
    VisionElement,
    VisionObservation,
    ElementType
)
from vision.ocr import ocr_engine

logger = logging.getLogger("Omnia.Vision.Perception")

class VisualPerceptionEngine:
    """Perception abstraction identifying visually meaningful UI elements with confidence scores."""

    BUTTON_KEYWORDS = re.compile(
        r"\b(submit|continue|next|ok|cancel|save|confirm|done|login|sign in|register|download|accept|allow|close|search|buy|checkout)\b",
        re.IGNORECASE
    )
    INPUT_KEYWORDS = re.compile(
        r"\b(enter|type|search|username|password|email|phone|card|address|name)\b",
        re.IGNORECASE
    )
    LINK_KEYWORDS = re.compile(
        r"\b(learn more|click here|read more|details|terms|privacy|forgot)\b",
        re.IGNORECASE
    )

    def _infer_element_type(self, text: str, width_norm: float, height_norm: float) -> ElementType:
        """Heuristic element type classifier. If uncertain, classifies as UNKNOWN."""
        t_lower = text.lower().strip()
        
        # Check explicit button matches
        if self.BUTTON_KEYWORDS.search(t_lower):
            # Buttons typically have moderate aspect ratios and compact heights
            if height_norm < 0.15 and width_norm < 0.6:
                return ElementType.BUTTON

        if self.INPUT_KEYWORDS.search(t_lower) and "search" in t_lower:
            return ElementType.INPUT

        if self.LINK_KEYWORDS.search(t_lower):
            return ElementType.LINK

        # Long text paragraphs
        if len(text.split()) > 6 or width_norm > 0.5:
            return ElementType.TEXT

        if len(text) > 0:
            return ElementType.TEXT

        return ElementType.UNKNOWN

    def analyze_frame(self, frame: VisionFrame) -> VisionObservation:
        """Analyzes a VisionFrame and extracts detected elements and transcriptions."""
        t0 = time.perf_counter()
        raw_regions = ocr_engine.extract_text_regions(frame)

        elements: List[VisionElement] = []
        full_text_parts = []

        for reg in raw_regions:
            text = reg["text"]
            conf = reg["confidence"]
            bbox = reg["bounding_box"]

            full_text_parts.append(text)
            el_type = self._infer_element_type(text, bbox.width, bbox.height)

            elements.append(VisionElement(
                element_type=el_type,
                label=text,
                text=text,
                confidence=conf,
                bounding_box=bbox,
                clickable=(el_type in [ElementType.BUTTON, ElementType.LINK, ElementType.INPUT]),
                visible=True,
                enabled=True
            ))

        analysis_ms = (time.perf_counter() - t0) * 1000
        aggregated_text = "\n".join(full_text_parts)

        return VisionObservation(
            frame=frame,
            elements=elements,
            raw_text=aggregated_text,
            analysis_duration_ms=analysis_ms
        )

perception_engine = VisualPerceptionEngine()
