"""OMNIA Video Studio — Module 40: Review & Collaboration Service.

Service orchestrator managing review session lifecycles, user authorization,
threaded discussions, decision submissions, and audit logging.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from video_studio.collaboration_engine import CollaborationEngine
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
from video_studio.registry import VideoStudioCapabilityRegistry
from video_studio.registry_models import (
    ImplementationState,
    VideoStudioCategory,
    VideoStudioCapabilityDescriptor,
)
from video_studio.timeline_models import TimelineMarker, VideoSequence

logger = logging.getLogger("omnia.video_studio.collaboration")


class CollaborationService:
    """Enterprise Review, Annotation, and Approval Service for OMNIA Video Studio."""

    def __init__(
        self,
        capability_registry: Optional[VideoStudioCapabilityRegistry] = None,
        audit_log_path: str = "omnia_audit.jsonl",
    ) -> None:
        self.registry = capability_registry
        self.audit_log_path = audit_log_path
        self._sessions: Dict[str, ReviewSession] = {}
        self.engine = CollaborationEngine()

        if self.registry:
            self._register_capabilities()

    def _register_capabilities(self) -> None:
        """Registers Module 40 Collaboration capabilities into the registry."""
        capabilities = [
            VideoStudioCapabilityDescriptor(
                id="video.collaboration.review_sessions",
                name="Project & Sequence Review Sessions",
                description="Version-aware multi-user review sessions with role-based access control.",
                category=VideoStudioCategory.COLLABORATION,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["collaboration", "review", "rbac"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.collaboration.timestamped_annotations",
                name="Timestamped & Spatial Video Annotations",
                description="Point, range, and normalized rectangular bounding-box visual annotations.",
                category=VideoStudioCategory.COLLABORATION,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["collaboration", "annotations", "spatial"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.collaboration.version_aware_review",
                name="Version-Aware Review & Stale Comment Detection",
                description="Automatic drift tracking between comments and subsequent timeline edits.",
                category=VideoStudioCategory.COLLABORATION,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["collaboration", "revisions", "stale_detection"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.collaboration.decision_audit",
                name="Formal Review Decisions & Audit Trail",
                description="Non-destructive approval workflows with immutable decision audit logging.",
                category=VideoStudioCategory.COLLABORATION,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["collaboration", "decisions", "approvals", "audit"],
            ),
        ]
        for cap in capabilities:
            if not self.registry.get(cap.id):
                self.registry.register(cap, auth_token="core")

    def _log_audit_event(self, event_type: str, details: Dict[str, Any]) -> None:
        """Appends an immutable event to the audit trail log."""
        payload = {
            "event_type": event_type,
            "timestamp": time.time(),
            "details": details,
        }
        try:
            with open(self.audit_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload) + "\n")
        except Exception as e:
            logger.warning(f"Failed to append to audit log {self.audit_log_path}: {e}")

    # --- Session Management ---

    def create_review_session(
        self,
        project_id: str,
        sequence_id: str,
        title: str,
        created_by: str,
        target_revision: int = 1,
        description: str = "",
        participants: Optional[Dict[str, ParticipantRole]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ReviewSession:
        """Creates a new version-pinned review session."""
        if not project_id or not sequence_id or not title or not created_by:
            raise ValueError("project_id, sequence_id, title, and created_by are required.")

        parts = dict(participants or {})
        # Creator is always OWNER unless specified
        if created_by not in parts:
            parts[created_by] = ParticipantRole.OWNER

        session = ReviewSession(
            project_id=project_id,
            sequence_id=sequence_id,
            title=title,
            description=description,
            target_revision=target_revision,
            created_by=created_by,
            participants=parts,
            metadata=dict(metadata or {}),
        )
        self._sessions[session.session_id] = session

        self._log_audit_event("REVIEW_SESSION_CREATED", {
            "session_id": session.session_id,
            "project_id": project_id,
            "sequence_id": sequence_id,
            "target_revision": target_revision,
            "created_by": created_by,
        })
        return session

    def get_session(self, session_id: str) -> Optional[ReviewSession]:
        return self._sessions.get(session_id)

    def list_sessions(
        self,
        project_id: Optional[str] = None,
        sequence_id: Optional[str] = None,
        status: Optional[ReviewSessionStatus] = None,
    ) -> List[ReviewSession]:
        """Lists sessions filtered by project, sequence, or status."""
        results = list(self._sessions.values())
        if project_id:
            results = [s for s in results if s.project_id == project_id]
        if sequence_id:
            results = [s for s in results if s.sequence_id == sequence_id]
        if status:
            results = [s for s in results if s.status == status]
        return results

    def close_session(self, session_id: str, user_id: str) -> ReviewSession:
        """Closes a review session. Only OWNER or EDITOR can close."""
        session = self.get_session(session_id)
        if not session:
            raise KeyError(f"Review session {session_id} not found.")

        if not session.is_authorized(user_id, [ParticipantRole.OWNER, ParticipantRole.EDITOR]):
            raise PermissionError(f"User {user_id} lacks permission to close session {session_id}.")

        session.status = ReviewSessionStatus.CLOSED
        session.closed_by = user_id
        session.closed_at = time.time()
        session.updated_at = time.time()

        self._log_audit_event("REVIEW_SESSION_CLOSED", {
            "session_id": session_id,
            "closed_by": user_id,
        })
        return session

    def add_participant(
        self,
        session_id: str,
        admin_user_id: str,
        new_user_id: str,
        role: ParticipantRole,
    ) -> None:
        """Adds or updates a participant's role. Requires OWNER role."""
        session = self.get_session(session_id)
        if not session:
            raise KeyError(f"Review session {session_id} not found.")

        if not session.is_authorized(admin_user_id, [ParticipantRole.OWNER]):
            raise PermissionError(f"User {admin_user_id} must be OWNER to manage participants.")

        session.participants[new_user_id] = role
        session.updated_at = time.time()

    # --- Comments & Annotations ---

    def add_comment(
        self,
        session_id: str,
        author_id: str,
        content: str,
        timestamp_seconds: float,
        end_timestamp_seconds: Optional[float] = None,
        region: Optional[NormalizedRegion] = None,
        parent_comment_id: Optional[str] = None,
        target_revision: Optional[int] = None,
        sequence: Optional[VideoSequence] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ReviewComment:
        """Adds a new timestamped/spatial comment or threaded reply."""
        session = self.get_session(session_id)
        if not session:
            raise KeyError(f"Review session {session_id} not found.")

        if session.status == ReviewSessionStatus.CLOSED:
            raise ValueError(f"Cannot add comments to closed session {session_id}.")

        allowed = [ParticipantRole.OWNER, ParticipantRole.EDITOR, ParticipantRole.REVIEWER]
        if not session.is_authorized(author_id, allowed):
            raise PermissionError(f"User {author_id} lacks comment permission in session {session_id}.")

        if parent_comment_id is not None:
            parent = next((c for c in session.comments if c.comment_id == parent_comment_id), None)
            if not parent:
                raise KeyError(f"Parent comment {parent_comment_id} not found.")

        # Spatial and temporal validations
        self.engine.validate_spatial_region(region)
        self.engine.validate_temporal_bounds(timestamp_seconds, end_timestamp_seconds, sequence)

        rev = target_revision if target_revision is not None else session.target_revision

        comment = ReviewComment(
            session_id=session_id,
            author_id=author_id,
            target_revision=rev,
            content=content,
            timestamp_seconds=timestamp_seconds,
            end_timestamp_seconds=end_timestamp_seconds,
            region=region,
            parent_comment_id=parent_comment_id,
            metadata=dict(metadata or {}),
        )
        session.comments.append(comment)
        session.updated_at = time.time()

        # Recalculate status if OPEN
        if session.status == ReviewSessionStatus.OPEN:
            session.status = ReviewSessionStatus.IN_REVIEW

        self._log_audit_event("REVIEW_COMMENT_ADDED", {
            "session_id": session_id,
            "comment_id": comment.comment_id,
            "author_id": author_id,
            "target_revision": rev,
            "has_region": region is not None,
        })
        return comment

    def resolve_comment(
        self,
        session_id: str,
        comment_id: str,
        user_id: str,
        state: CommentResolutionState = CommentResolutionState.RESOLVED,
    ) -> ReviewComment:
        """Resolves or reopens a comment."""
        session = self.get_session(session_id)
        if not session:
            raise KeyError(f"Review session {session_id} not found.")

        comment = next((c for c in session.comments if c.comment_id == comment_id), None)
        if not comment:
            raise KeyError(f"Comment {comment_id} not found in session {session_id}.")

        role = session.get_participant_role(user_id)
        if not role:
            raise PermissionError(f"User {user_id} is not a participant.")

        # Owners and Editors can resolve any comment; Reviewers can resolve their own
        if role not in [ParticipantRole.OWNER, ParticipantRole.EDITOR]:
            if comment.author_id != user_id:
                raise PermissionError("Reviewers can only resolve their own comments.")

        comment.resolution_state = state
        comment.resolved_by = user_id if state in [CommentResolutionState.RESOLVED, CommentResolutionState.WONT_FIX] else None
        comment.resolved_at = time.time() if state in [CommentResolutionState.RESOLVED, CommentResolutionState.WONT_FIX] else None
        comment.updated_at = time.time()
        session.updated_at = time.time()

        self._log_audit_event("REVIEW_COMMENT_RESOLVED", {
            "session_id": session_id,
            "comment_id": comment_id,
            "resolved_by": user_id,
            "resolution_state": state.value,
        })
        return comment

    # --- Decisions & Approvals ---

    def submit_decision(
        self,
        session_id: str,
        reviewer_id: str,
        decision_type: ReviewDecisionType,
        rationale: str = "",
        target_revision: Optional[int] = None,
    ) -> ReviewDecision:
        """Submits an immutable formal review decision (APPROVED, CHANGES_REQUESTED, ABSTAIN)."""
        session = self.get_session(session_id)
        if not session:
            raise KeyError(f"Review session {session_id} not found.")

        if session.status == ReviewSessionStatus.CLOSED:
            raise ValueError(f"Cannot submit decision on closed session {session_id}.")

        allowed = [ParticipantRole.OWNER, ParticipantRole.REVIEWER]
        if not session.is_authorized(reviewer_id, allowed):
            raise PermissionError(f"User {reviewer_id} lacks approval/decision authority.")

        rev = target_revision if target_revision is not None else session.target_revision

        decision = ReviewDecision(
            session_id=session_id,
            reviewer_id=reviewer_id,
            target_revision=rev,
            decision_type=decision_type,
            rationale=rationale,
        )
        session.decisions.append(decision)
        session.status = self.engine.aggregate_session_status(session)
        session.updated_at = time.time()

        self._log_audit_event("REVIEW_DECISION_SUBMITTED", {
            "session_id": session_id,
            "decision_id": decision.decision_id,
            "reviewer_id": reviewer_id,
            "target_revision": rev,
            "decision_type": decision_type.value,
            "new_session_status": session.status.value,
        })
        return decision

    # --- Drift & Markers ---

    def get_stale_comments(
        self,
        session_id: str,
        current_sequence_revision: int,
    ) -> List[Tuple[ReviewComment, int]]:
        """Identifies comments authored on earlier revisions than current sequence state."""
        session = self.get_session(session_id)
        if not session:
            raise KeyError(f"Review session {session_id} not found.")
        return self.engine.detect_stale_comments(session, current_sequence_revision)

    def export_timeline_markers(
        self,
        session_id: str,
        include_resolved: bool = False,
    ) -> List[TimelineMarker]:
        """Exports comments as viewer-compatible non-destructive TimelineMarkers."""
        session = self.get_session(session_id)
        if not session:
            raise KeyError(f"Review session {session_id} not found.")
        return self.engine.project_comments_to_timeline_markers(session, include_resolved)
