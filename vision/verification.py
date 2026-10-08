import logging
from typing import Optional
from vision.models import (
    VisionFrame,
    VisionVerification,
    VerificationStatus,
    BoundingBox
)
from vision.perception import perception_engine
from vision.comparison import diff_engine

logger = logging.getLogger("Omnia.Vision.Verification")

class VisualVerificationEngine:
    """Verifies that an executed visual action produced the expected UI transition."""

    def verify_text_appearance(
        self,
        before: VisionFrame,
        after: VisionFrame,
        expected_text: str,
        should_appear: bool = True
    ) -> VisionVerification:
        """Checks whether expected text appeared or disappeared after action."""
        obs_after = perception_engine.analyze_frame(after)
        found = any(expected_text.lower() in el.text.lower() for el in obs_after.elements)

        if should_appear and found:
            status = VerificationStatus.VERIFIED
            reason = f"Expected text '{expected_text}' successfully observed on screen."
        elif not should_appear and not found:
            status = VerificationStatus.VERIFIED
            reason = f"Expected text '{expected_text}' successfully disappeared from screen."
        elif should_appear and not found:
            status = VerificationStatus.FAILED
            reason = f"Expected text '{expected_text}' was NOT found on screen."
        else:
            status = VerificationStatus.FAILED
            reason = f"Expected text '{expected_text}' was still present on screen."

        diff = diff_engine.compare_frames(before, after)
        return VisionVerification(
            status=status,
            strategy="text_appearance",
            diff=diff,
            expected=f"{'Appear' if should_appear else 'Disappear'}: '{expected_text}'",
            observed=f"Found: {found}",
            reason=reason,
            pre_frame_id=before.frame_id,
            post_frame_id=after.frame_id
        )

    def verify_visual_transition(
        self,
        before: VisionFrame,
        after: VisionFrame,
        min_change_ratio: float = 0.015,
        target_region: Optional[BoundingBox] = None
    ) -> VisionVerification:
        """Verifies that a visual change took place following an interaction."""
        diff = diff_engine.compare_frames(before, after, target_region=target_region)

        if diff.confidence < 0.3:
            status = VerificationStatus.UNCERTAIN
            reason = f"Verification uncertain: Frame comparison had low confidence ({diff.confidence:.2f})."
        elif diff.changed_pixels_ratio >= min_change_ratio:
            status = VerificationStatus.VERIFIED
            reason = f"Visual transition verified: {diff.description}"
        elif diff.changed_pixels_ratio < 0.002: # Virtually no change
            status = VerificationStatus.FAILED
            reason = f"No visual transition detected: {diff.description}"
        else:
            status = VerificationStatus.UNCERTAIN
            reason = f"Subtle change ({diff.changed_pixels_ratio * 100:.2f}%) below confidence threshold."

        return VisionVerification(
            status=status,
            strategy="visual_transition",
            diff=diff,
            expected=f"Visual change >= {min_change_ratio * 100:.1f}%",
            observed=f"Measured change: {diff.changed_pixels_ratio * 100:.2f}%",
            reason=reason,
            pre_frame_id=before.frame_id,
            post_frame_id=after.frame_id
        )

    def detect_unexpected_state(self, after: VisionFrame, error_keywords: Optional[list] = None) -> Optional[str]:
        """Detects error dialogs or crash popups in the post-action frame."""
        if error_keywords is None:
            error_keywords = ["error", "fatal", "failed", "exception", "crash", "access denied", "not responding"]

        obs = perception_engine.analyze_frame(after)
        for el in obs.elements:
            for kw in error_keywords:
                if kw in el.text.lower():
                    return f"UNEXPECTED_UI_STATE: Detected error indicator '{el.text}'"
        return None

verification_engine = VisualVerificationEngine()
