"""OMNIA Video Studio — Module 40: Review & Collaboration Engine.

Core algorithmic logic for timestamp/region validation, revision drift detection,
timeline marker synchronization, and review status aggregation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from video_studio.collaboration_models import (
    CommentResolutionState,
    NormalizedRegion,
    ParticipantRole,
    ReviewComment,
    ReviewDecision,
    ReviewDecisionType,
    ReviewSession,
    ReviewSessionStatus,
)
from video_studio.timeline_models import TimelineMarker, VideoSequence


class CollaborationEngine:
    """Core domain logic for Video Studio review cycles, annotations, and marker projection."""

    @staticmethod
    def validate_spatial_region(region: Optional[NormalizedRegion]) -> None:
        """Validates that a normalized bounding box lies strictly within [0.0, 1.0]."""
        if region is None:
            return
        if not (0.0 <= region.x <= 1.0):
            raise ValueError(f"Region X coordinate {region.x} must be between 0.0 and 1.0.")
        if not (0.0 <= region.y <= 1.0):
            raise ValueError(f"Region Y coordinate {region.y} must be between 0.0 and 1.0.")
        if not (0.0 <= region.width <= 1.0):
            raise ValueError(f"Region width {region.width} must be between 0.0 and 1.0.")
        if not (0.0 <= region.height <= 1.0):
            raise ValueError(f"Region height {region.height} must be between 0.0 and 1.0.")
        if region.x + region.width > 1.0001:
            raise ValueError(f"Region extends past right boundary: x + w = {region.x + region.width}")
        if region.y + region.height > 1.0001:
            raise ValueError(f"Region extends past bottom boundary: y + h = {region.y + region.height}")

    @staticmethod
    def validate_temporal_bounds(
        timestamp_seconds: float,
        end_timestamp_seconds: Optional[float],
        sequence: Optional[VideoSequence] = None,
    ) -> None:
        """Ensures comment timestamps are non-negative and within sequence duration if sequence is provided."""
        if timestamp_seconds < 0.0:
            raise ValueError(f"Comment timestamp cannot be negative: {timestamp_seconds}")

        if end_timestamp_seconds is not None:
            if end_timestamp_seconds < timestamp_seconds:
                raise ValueError(
                    f"End timestamp ({end_timestamp_seconds}) cannot be less than start timestamp ({timestamp_seconds})."
                )

        if sequence is not None:
            fps = sequence.settings.frame_rate if sequence.settings and sequence.settings.frame_rate > 0 else 24.0
            seq_dur_sec = sequence.duration_frames / fps
            if seq_dur_sec > 0:
                if timestamp_seconds > seq_dur_sec:
                    raise ValueError(
                        f"Timestamp ({timestamp_seconds}s) exceeds sequence duration ({seq_dur_sec}s)."
                    )
                if end_timestamp_seconds is not None and end_timestamp_seconds > seq_dur_sec:
                    raise ValueError(
                        f"End timestamp ({end_timestamp_seconds}s) exceeds sequence duration ({seq_dur_sec}s)."
                    )

    @staticmethod
    def detect_stale_comments(
        session: ReviewSession,
        current_sequence_revision: int,
    ) -> List[Tuple[ReviewComment, int]]:
        """Identifies comments authored on earlier revisions than the sequence's current state.

        Returns:
            List of tuples: (comment, revision_drift_delta)
        """
        stale_entries: List[Tuple[ReviewComment, int]] = []
        for comment in session.comments:
            if comment.target_revision < current_sequence_revision:
                drift = current_sequence_revision - comment.target_revision
                stale_entries.append((comment, drift))
        return stale_entries

    @staticmethod
    def aggregate_session_status(session: ReviewSession) -> ReviewSessionStatus:
        """Computes current session state based on decisions and comments.

        Rules:
        - If explicitly closed, stays CLOSED.
        - If any CHANGES_REQUESTED decision exists on current target revision, CHANGES_REQUESTED.
        - If all non-abstaining decisions on target revision are APPROVED and at least one exists, APPROVED.
        - If decisions exist or comments exist, IN_REVIEW.
        - Otherwise, OPEN.
        """
        if session.status == ReviewSessionStatus.CLOSED:
            return ReviewSessionStatus.CLOSED

        target_decisions = [
            d for d in session.decisions
            if d.target_revision == session.target_revision
        ]

        has_changes_requested = any(
            d.decision_type == ReviewDecisionType.CHANGES_REQUESTED
            for d in target_decisions
        )
        if has_changes_requested:
            return ReviewSessionStatus.CHANGES_REQUESTED

        approvals = [
            d for d in target_decisions
            if d.decision_type == ReviewDecisionType.APPROVED
        ]
        if approvals and len(approvals) == len([d for d in target_decisions if d.decision_type != ReviewDecisionType.ABSTAIN]):
            return ReviewSessionStatus.APPROVED

        if target_decisions or session.comments:
            return ReviewSessionStatus.IN_REVIEW

        return ReviewSessionStatus.OPEN

    @staticmethod
    def project_comments_to_timeline_markers(
        session: ReviewSession,
        include_resolved: bool = False,
    ) -> List[TimelineMarker]:
        """Projects non-destructive ReviewComments into TimelineMarker representations for viewer overlays."""
        from video_studio.timeline_models import MarkerCategory
        markers: List[TimelineMarker] = []
        for comment in session.comments:
            if not include_resolved and comment.resolution_state == CommentResolutionState.RESOLVED:
                continue

            color = "#FFA500"  # Orange for active
            if comment.resolution_state == CommentResolutionState.RESOLVED:
                color = "#28A745"  # Green
            elif comment.resolution_state == CommentResolutionState.WONT_FIX:
                color = "#6C757D"  # Gray

            frame = int(round(comment.timestamp_seconds * 24.0))
            dur_frames = 0
            if comment.end_timestamp_seconds and comment.end_timestamp_seconds > comment.timestamp_seconds:
                dur_frames = int(round((comment.end_timestamp_seconds - comment.timestamp_seconds) * 24.0))

            marker = TimelineMarker(
                marker_id=f"marker-{comment.comment_id[:8]}",
                sequence_id=session.sequence_id,
                frame=frame,
                duration_frames=dur_frames,
                name=f"Review [{comment.author_id}]",
                comment=comment.content,
                category=MarkerCategory.NOTE,
                color_hex=color,
                creator=comment.author_id,
            )
            markers.append(marker)
        return markers
