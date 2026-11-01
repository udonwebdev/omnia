"""OMNIA Video Studio — AI-Assisted Editing, Automated Rough Cut & Edit Decision Models (Module 36).

Defines authoritative domain models for:
- EditingBrief: Comprehensive specification for the rough cut:
  * Target duration & tolerance range
  * Pacing profile (FAST_PACED, MODERATE, SLOW_CINEMATIC)
  * Preferred narrative structure (CHRONOLOGICAL, HIGHLIGHTS_FIRST, THEMATIC)
  * Mandatory scenes/moments (must-include tags, keywords, or asset IDs)
  * Excluded scenes/moments (must-exclude tags or intervals)
  * Aspect ratio & target resolution
  * Music & caption placement preferences
- CandidateMoment: Selected footage slice with rationale, technical score, and timestamps
- EditDecision: Single proposed timeline edit operation (clip in/out, timeline position, track, rationale)
- EditDecisionList (EDL): Versioned container holding proposed decisions with approval workflow (PROPOSED, APPROVED, REJECTED)
- RoughCutGenerationStatus: READY, PROCESSING, COMPLETED, FAILED, CANCELLED
- RoughCutResult: Summary of rough cut construction, created sequence ID, added item count, and timeline duration
"""

import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple


class PacingProfile(str, Enum):
    """Pacing rhythm and average cut duration."""
    FAST_PACED = "FAST_PACED"         # Rapid cuts (1.5 - 3.0 seconds per shot, e.g., trailers/socials)
    MODERATE = "MODERATE"             # Standard documentary / vlog pacing (3.0 - 6.0 seconds per shot)
    SLOW_CINEMATIC = "SLOW_CINEMATIC" # Lingering contemplative framing (6.0 - 15.0 seconds per shot)


class NarrativeStructure(str, Enum):
    """Sequencing strategy for candidate moments."""
    CHRONOLOGICAL = "CHRONOLOGICAL"   # Preserves original source capture sequence
    HIGHLIGHTS_FIRST = "HIGHLIGHTS_FIRST" # High-energy hook in opening 5 seconds, followed by body
    THEMATIC = "THEMATIC"             # Groups clips by visual/semantic tags


class EDLApprovalStatus(str, Enum):
    """Approval lifecycle of an edit proposal."""
    PROPOSED = "PROPOSED"             # AI/algorithmic proposal pending review
    MODIFIED = "MODIFIED"             # Edited by user before commit
    APPROVED = "APPROVED"             # Approved by user for timeline commit
    REJECTED = "REJECTED"             # Rejected / discarded


@dataclass
class EditingBrief:
    """User-defined creative brief and technical constraints for rough cut generation."""
    brief_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = "default_project"
    source_asset_ids: List[str] = field(default_factory=list)
    title: str = "Rough Cut First Assembly"
    objective: str = "Create an engaging highlights assembly"
    target_duration_seconds: float = 60.0
    duration_tolerance_seconds: float = 5.0
    pacing: PacingProfile = PacingProfile.MODERATE
    narrative_structure: NarrativeStructure = NarrativeStructure.CHRONOLOGICAL
    required_keywords: List[str] = field(default_factory=list)  # Must include shots matching these
    excluded_keywords: List[str] = field(default_factory=list)  # Strictly exclude shots matching these
    min_shot_duration: float = 1.5
    max_shot_duration: float = 8.0
    include_captions: bool = True
    include_source_audio: bool = True
    aspect_ratio: str = "16:9"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "brief_id": self.brief_id,
            "project_id": self.project_id,
            "source_asset_ids": list(self.source_asset_ids),
            "title": self.title,
            "objective": self.objective,
            "target_duration_seconds": round(float(self.target_duration_seconds), 2),
            "duration_tolerance_seconds": round(float(self.duration_tolerance_seconds), 2),
            "pacing": self.pacing.value,
            "narrative_structure": self.narrative_structure.value,
            "required_keywords": list(self.required_keywords),
            "excluded_keywords": list(self.excluded_keywords),
            "min_shot_duration": round(float(self.min_shot_duration), 2),
            "max_shot_duration": round(float(self.max_shot_duration), 2),
            "include_captions": self.include_captions,
            "include_source_audio": self.include_source_audio,
            "aspect_ratio": self.aspect_ratio,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EditingBrief":
        return cls(
            brief_id=data.get("brief_id", str(uuid.uuid4())),
            project_id=data.get("project_id", "default_project"),
            source_asset_ids=list(data.get("source_asset_ids", [])),
            title=data.get("title", "Rough Cut First Assembly"),
            objective=data.get("objective", "Create an engaging highlights assembly"),
            target_duration_seconds=float(data.get("target_duration_seconds", 60.0)),
            duration_tolerance_seconds=float(data.get("duration_tolerance_seconds", 5.0)),
            pacing=PacingProfile(data.get("pacing", PacingProfile.MODERATE.value)),
            narrative_structure=NarrativeStructure(data.get("narrative_structure", NarrativeStructure.CHRONOLOGICAL.value)),
            required_keywords=list(data.get("required_keywords", [])),
            excluded_keywords=list(data.get("excluded_keywords", [])),
            min_shot_duration=float(data.get("min_shot_duration", 1.5)),
            max_shot_duration=float(data.get("max_shot_duration", 8.0)),
            include_captions=bool(data.get("include_captions", True)),
            include_source_audio=bool(data.get("include_source_audio", True)),
            aspect_ratio=data.get("aspect_ratio", "16:9"),
        )


@dataclass
class CandidateMoment:
    """An analyzed clip moment considered for rough-cut inclusion."""
    moment_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    asset_id: str = "default_asset"
    source_in: float = 0.0
    source_out: float = 3.0
    shot_id: Optional[str] = None
    score: float = 1.0
    selection_rationale: str = ""
    tags: List[str] = field(default_factory=list)
    has_speech: bool = False
    is_mandatory: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "moment_id": self.moment_id,
            "asset_id": self.asset_id,
            "source_in": round(float(self.source_in), 3),
            "source_out": round(float(self.source_out), 3),
            "duration": round(float(self.source_out - self.source_in), 3),
            "shot_id": self.shot_id,
            "score": round(float(self.score), 3),
            "selection_rationale": self.selection_rationale,
            "tags": list(self.tags),
            "has_speech": self.has_speech,
            "is_mandatory": self.is_mandatory,
        }


@dataclass
class EditDecision:
    """Individual cut decision in an edit decision list."""
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    asset_id: str = "default_asset"
    source_in: float = 0.0
    source_out: float = 3.0
    timeline_start: float = 0.0
    track_id: str = "track_v1"
    audio_track_id: Optional[str] = "track_a1"
    rationale: str = "Chronological cut"
    shot_type: str = "MEDIUM_SHOT"
    tags: List[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max(0.0, self.source_out - self.source_in)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "asset_id": self.asset_id,
            "source_in": round(float(self.source_in), 3),
            "source_out": round(float(self.source_out), 3),
            "duration": round(float(self.duration), 3),
            "timeline_start": round(float(self.timeline_start), 3),
            "track_id": self.track_id,
            "audio_track_id": self.audio_track_id,
            "rationale": self.rationale,
            "shot_type": self.shot_type,
            "tags": list(self.tags),
        }


@dataclass
class EditDecisionList:
    """Master structured edit proposal with review and approval workflow."""
    edl_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    brief_id: str = ""
    project_id: str = "default_project"
    revision: int = 1
    status: EDLApprovalStatus = EDLApprovalStatus.PROPOSED
    decisions: List[EditDecision] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def total_duration(self) -> float:
        if not self.decisions:
            return 0.0
        return sum(d.duration for d in self.decisions)

    def recalculate_timeline_positions(self) -> None:
        """Sequential ripple re-alignment of timeline start positions."""
        curr = 0.0
        for d in self.decisions:
            d.timeline_start = curr
            curr += d.duration

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edl_id": self.edl_id,
            "brief_id": self.brief_id,
            "project_id": self.project_id,
            "revision": self.revision,
            "status": self.status.value,
            "decision_count": len(self.decisions),
            "total_duration": round(float(self.total_duration), 3),
            "decisions": [d.to_dict() for d in self.decisions],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class RoughCutResult:
    """Final result of converting approved EDL into timeline tracks and clips."""
    success: bool = True
    sequence_id: str = ""
    edl_id: str = ""
    items_created: int = 0
    total_timeline_duration: float = 0.0
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "sequence_id": self.sequence_id,
            "edl_id": self.edl_id,
            "items_created": self.items_created,
            "total_timeline_duration": round(float(self.total_timeline_duration), 3),
            "warnings": list(self.warnings),
            "error": self.error,
        }
