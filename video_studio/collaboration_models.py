"""OMNIA Video Studio — Module 40: Professional Collaboration, Review & Annotation Engine.

Data models for version-aware project & sequence review sessions, threaded annotations,
spatial/temporal markers, participant permissions, and review decisions.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ParticipantRole(str, Enum):
    """Permissions hierarchy for review session participants."""
    OWNER = "OWNER"          # Session owner: can close/reopen, manage participants, decide, comment
    EDITOR = "EDITOR"        # Editor: can comment, reply, resolve comments, edit sequence
    REVIEWER = "REVIEWER"    # Reviewer: can comment, reply, resolve own comments, submit decisions
    VIEWER = "VIEWER"        # Viewer: read-only access to session, comments, and decisions


class ReviewSessionStatus(str, Enum):
    """Lifecycle state of a review session."""
    OPEN = "OPEN"
    IN_REVIEW = "IN_REVIEW"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    APPROVED = "APPROVED"
    CLOSED = "CLOSED"


class ReviewDecisionType(str, Enum):
    """Formal decision rendered by an authorized reviewer or owner."""
    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    ABSTAIN = "ABSTAIN"


class CommentResolutionState(str, Enum):
    """Resolution lifecycle for an annotation comment."""
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    REOPENED = "REOPENED"
    WONT_FIX = "WONT_FIX"


@dataclass(frozen=True)
class NormalizedRegion:
    """Normalized spatial bounding box [0.0, 1.0] for frame annotations."""
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        if not (0.0 <= self.x <= 1.0):
            raise ValueError(f"NormalizedRegion x ({self.x}) must be between 0.0 and 1.0.")
        if not (0.0 <= self.y <= 1.0):
            raise ValueError(f"NormalizedRegion y ({self.y}) must be between 0.0 and 1.0.")
        if not (0.0 <= self.width <= 1.0):
            raise ValueError(f"NormalizedRegion width ({self.width}) must be between 0.0 and 1.0.")
        if not (0.0 <= self.height <= 1.0):
            raise ValueError(f"NormalizedRegion height ({self.height}) must be between 0.0 and 1.0.")
        if self.x + self.width > 1.0001:
            raise ValueError(f"NormalizedRegion x + width ({self.x + self.width}) exceeds 1.0.")
        if self.y + self.height > 1.0001:
            raise ValueError(f"NormalizedRegion y + height ({self.y + self.height}) exceeds 1.0.")

    def to_dict(self) -> Dict[str, float]:
        return {
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "width": round(self.width, 4),
            "height": round(self.height, 4),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> NormalizedRegion:
        return cls(
            x=float(data["x"]),
            y=float(data["y"]),
            width=float(data["width"]),
            height=float(data["height"]),
        )


@dataclass
class ReviewComment:
    """Timestamped and optionally spatially bounded annotation comment."""
    comment_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    author_id: str = ""
    target_revision: int = 1
    content: str = ""
    timestamp_seconds: float = 0.0
    end_timestamp_seconds: Optional[float] = None
    region: Optional[NormalizedRegion] = None
    parent_comment_id: Optional[str] = None
    resolution_state: CommentResolutionState = CommentResolutionState.OPEN
    resolved_by: Optional[str] = None
    resolved_at: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_stale(self, current_sequence_revision: int) -> bool:
        """Determines if the comment was authored against an older revision."""
        return self.target_revision < current_sequence_revision

    def is_range(self) -> bool:
        """Returns True if this annotation spans a time range."""
        return self.end_timestamp_seconds is not None and self.end_timestamp_seconds > self.timestamp_seconds

    def to_dict(self) -> Dict[str, Any]:
        return {
            "comment_id": self.comment_id,
            "session_id": self.session_id,
            "author_id": self.author_id,
            "target_revision": self.target_revision,
            "content": self.content,
            "timestamp_seconds": round(self.timestamp_seconds, 3),
            "end_timestamp_seconds": round(self.end_timestamp_seconds, 3) if self.end_timestamp_seconds is not None else None,
            "region": self.region.to_dict() if self.region else None,
            "parent_comment_id": self.parent_comment_id,
            "resolution_state": self.resolution_state.value,
            "resolved_by": self.resolved_by,
            "resolved_at": self.resolved_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ReviewDecision:
    """Immutable audit record of a formal review decision."""
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    reviewer_id: str = ""
    target_revision: int = 1
    decision_type: ReviewDecisionType = ReviewDecisionType.APPROVED
    rationale: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "session_id": self.session_id,
            "reviewer_id": self.reviewer_id,
            "target_revision": self.target_revision,
            "decision_type": self.decision_type.value,
            "rationale": self.rationale,
            "created_at": self.created_at,
        }


@dataclass
class ReviewSession:
    """Master container for a review and annotation cycle over a sequence revision."""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    sequence_id: str = ""
    title: str = ""
    description: str = ""
    target_revision: int = 1
    status: ReviewSessionStatus = ReviewSessionStatus.OPEN
    created_by: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    closed_at: Optional[float] = None
    closed_by: Optional[str] = None
    participants: Dict[str, ParticipantRole] = field(default_factory=dict)
    comments: List[ReviewComment] = field(default_factory=list)
    decisions: List[ReviewDecision] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_participant_role(self, user_id: str) -> Optional[ParticipantRole]:
        return self.participants.get(user_id)

    def is_authorized(self, user_id: str, allowed_roles: List[ParticipantRole]) -> bool:
        role = self.get_participant_role(user_id)
        if not role:
            return False
        return role in allowed_roles

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "project_id": self.project_id,
            "sequence_id": self.sequence_id,
            "title": self.title,
            "description": self.description,
            "target_revision": self.target_revision,
            "status": self.status.value,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "closed_at": self.closed_at,
            "closed_by": self.closed_by,
            "participants": {uid: role.value for uid, role in self.participants.items()},
            "comment_count": len(self.comments),
            "decision_count": len(self.decisions),
            "metadata": dict(self.metadata),
        }
