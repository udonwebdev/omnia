import difflib
import logging
from typing import List, Optional
from vision.models import (
    VisionObservation,
    GroundingCandidate,
    ElementType
)

logger = logging.getLogger("Omnia.Vision.Grounding")

class VisualGroundingEngine:
    """Ranks and grounds natural language element targets onto observed visual elements."""

    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        """Computes normalized string similarity."""
        s1 = a.lower().strip()
        s2 = b.lower().strip()
        if not s1 or not s2:
            return 0.0
        if s1 == s2:
            return 1.0
        if s1 in s2 or s2 in s1:
            return 0.85 + (0.15 * (min(len(s1), len(s2)) / max(len(s1), len(s2))))
        return difflib.SequenceMatcher(None, s1, s2).ratio()

    def find_candidates(self, query: str, observation: VisionObservation, min_confidence: float = 0.3) -> List[GroundingCandidate]:
        """Grounds a target query (e.g. 'continue button') against visible elements."""
        q_lower = query.lower().strip()
        # Check target type hinting
        wants_button = "button" in q_lower or "btn" in q_lower
        wants_input = "input" in q_lower or "field" in q_lower or "box" in q_lower
        wants_link = "link" in q_lower

        cleaned_query = q_lower.replace("button", "").replace("btn", "").replace("input", "").replace("field", "").replace("link", "").strip()
        if not cleaned_query:
            cleaned_query = q_lower

        candidates = []

        for el in observation.elements:
            sim = self._text_similarity(cleaned_query, el.text)
            
            # Confidence bonus based on element type compatibility
            type_bonus = 0.0
            if wants_button and el.element_type == ElementType.BUTTON:
                type_bonus = 0.15
            elif wants_input and el.element_type == ElementType.INPUT:
                type_bonus = 0.15
            elif wants_link and el.element_type == ElementType.LINK:
                type_bonus = 0.15

            # Combine OCR confidence with text similarity and type match
            final_score = (sim * 0.7) + (el.confidence * 0.2) + type_bonus
            final_score = min(1.0, final_score)

            if final_score >= min_confidence and sim > 0.35:
                reason = f"Matched text '{el.text}' (sim: {sim:.2f}, type: {el.element_type.value}, ocr_conf: {el.confidence:.2f})"
                candidates.append((final_score, el, reason))

        # Sort descending by score
        candidates.sort(key=lambda c: c[0], reverse=True)

        ranked = []
        for rank, (score, element, reason) in enumerate(candidates, 1):
            ranked.append(GroundingCandidate(
                element=element,
                rank=rank,
                score=score,
                reason=reason
            ))

        return ranked

    def ground_best(self, query: str, observation: VisionObservation) -> Optional[GroundingCandidate]:
        """Returns the highest-scoring candidate if any exists."""
        ranked = self.find_candidates(query, observation)
        return ranked[0] if ranked else None

grounding_engine = VisualGroundingEngine()
