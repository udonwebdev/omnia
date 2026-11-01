"""OMNIA Video Studio — Module 41: Version Control, Revision Snapshots, Timeline Branching & Recovery Models.

Domain models for:
- RevisionSnapshot: Immutable project revision snapshot with checksums and schema versioning.
- ProjectBranch: Named pointer to a head revision snapshot with parent tracking.
- RevisionDiff: Structural difference report comparing two revisions (tracks, clips, settings, duration).
- RestoreResult: Outcome of non-destructive restore and recovery operations.
- VersionControlPolicy: Retention rules, protection flags, and safety limits.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


VERSION_CONTROL_SCHEMA_VERSION = "video-studio.versioning.v1"


class RevisionType(str, Enum):
    """Categorization of how or why a revision snapshot was captured."""
    MANUAL = "MANUAL"               # User explicitly created a milestone snapshot
    AUTO = "AUTO"                   # Periodic background snapshot
    PRE_RESTORE = "PRE_RESTORE"     # Safety snapshot created before restoring an earlier state
    BRANCH_CHECKPOINT = "BRANCH_CHECKPOINT"  # Snapshot created when branching
    COLLABORATION_REVIEW = "COLLABORATION_REVIEW" # Snapshot pinned to a review session


class RestoreSafetyLevel(str, Enum):
    """Safety strategy for executing a project state restoration."""
    ATOMIC_REPLACE = "ATOMIC_REPLACE"   # Atomic swap with pre-restore safety snapshot
    DRY_RUN = "DRY_RUN"                 # Validation and preview only, leaves project untouched
    NEW_PROJECT = "NEW_PROJECT"         # Restores revision into a new project instance


@dataclass
class StructuralDiffItem:
    """Individual structural change detected between two snapshots."""
    entity_type: str                  # track, clip, marker, setting, effect
    entity_id: str
    change_type: str                  # ADDED, REMOVED, MODIFIED, MOVED
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "change_type": self.change_type,
            "summary": self.summary,
            "details": dict(self.details),
        }


@dataclass
class RevisionDiff:
    """Comprehensive comparison between two revision snapshots."""
    source_revision_id: str
    target_revision_id: str
    source_revision_number: int
    target_revision_number: int
    is_identical: bool = False
    tracks_added: List[str] = field(default_factory=list)
    tracks_removed: List[str] = field(default_factory=list)
    clips_added: List[str] = field(default_factory=list)
    clips_removed: List[str] = field(default_factory=list)
    clips_modified: List[str] = field(default_factory=list)
    settings_changed: Dict[str, Any] = field(default_factory=dict)
    duration_delta_frames: int = 0
    structural_changes: List[StructuralDiffItem] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_revision_id": self.source_revision_id,
            "target_revision_id": self.target_revision_id,
            "source_revision_number": self.source_revision_number,
            "target_revision_number": self.target_revision_number,
            "is_identical": self.is_identical,
            "tracks_added": list(self.tracks_added),
            "tracks_removed": list(self.tracks_removed),
            "clips_added": list(self.clips_added),
            "clips_removed": list(self.clips_removed),
            "clips_modified": list(self.clips_modified),
            "settings_changed": dict(self.settings_changed),
            "duration_delta_frames": self.duration_delta_frames,
            "structural_changes_count": len(self.structural_changes),
            "structural_changes": [c.to_dict() for c in self.structural_changes],
        }


@dataclass
class RevisionSnapshot:
    """Immutable, content-addressed snapshot of a project's timeline state."""
    revision_id: str = field(default_factory=lambda: f"rev_{uuid.uuid4().hex[:12]}")
    project_id: str = ""
    sequence_id: str = ""
    revision_number: int = 1
    branch_name: str = "main"
    parent_revision_id: Optional[str] = None
    name: str = "Milestone"
    message: str = ""
    author_id: str = "editor"
    revision_type: RevisionType = RevisionType.MANUAL
    schema_version: str = VERSION_CONTROL_SCHEMA_VERSION
    created_at: float = field(default_factory=time.time)

    # Serialized sequence state payload
    sequence_data: Dict[str, Any] = field(default_factory=dict)
    referenced_asset_ids: List[str] = field(default_factory=list)
    
    # Integrity and content hashing
    content_fingerprint_sha256: str = ""
    is_protected: bool = False       # Protected snapshots cannot be deleted by retention pruning
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self, include_sequence_data: bool = False) -> Dict[str, Any]:
        res: Dict[str, Any] = {
            "revision_id": self.revision_id,
            "project_id": self.project_id,
            "sequence_id": self.sequence_id,
            "revision_number": self.revision_number,
            "branch_name": self.branch_name,
            "parent_revision_id": self.parent_revision_id,
            "name": self.name,
            "message": self.message,
            "author_id": self.author_id,
            "revision_type": self.revision_type.value,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "referenced_asset_count": len(self.referenced_asset_ids),
            "referenced_asset_ids": list(self.referenced_asset_ids),
            "content_fingerprint_sha256": self.content_fingerprint_sha256,
            "is_protected": self.is_protected,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }
        if include_sequence_data:
            res["sequence_data"] = copy_dict(self.sequence_data)
        return res


def copy_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    import copy
    return copy.deepcopy(d)


@dataclass
class ProjectBranch:
    """Named timeline branch pointing to a head revision."""
    branch_id: str = field(default_factory=lambda: f"br_{uuid.uuid4().hex[:8]}")
    project_id: str = ""
    name: str = "main"
    head_revision_id: str = ""
    parent_branch_name: Optional[str] = None
    fork_revision_id: Optional[str] = None
    created_by: str = "editor"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    description: str = ""
    is_default: bool = False
    is_locked: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "project_id": self.project_id,
            "name": self.name,
            "head_revision_id": self.head_revision_id,
            "parent_branch_name": self.parent_branch_name,
            "fork_revision_id": self.fork_revision_id,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "description": self.description,
            "is_default": self.is_default,
            "is_locked": self.is_locked,
        }


@dataclass
class RestoreResult:
    """Outcome of attempting to restore a project sequence to an earlier revision."""
    success: bool = True
    revision_id: str = ""
    project_id: str = ""
    sequence_id: str = ""
    restored_revision_number: int = 1
    safety_snapshot_id: Optional[str] = None
    missing_assets: List[str] = field(default_factory=list)
    available_assets: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    restored_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "revision_id": self.revision_id,
            "project_id": self.project_id,
            "sequence_id": self.sequence_id,
            "restored_revision_number": self.restored_revision_number,
            "safety_snapshot_id": self.safety_snapshot_id,
            "missing_asset_count": len(self.missing_assets),
            "missing_assets": list(self.missing_assets),
            "available_assets": list(self.available_assets),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "restored_at": self.restored_at,
        }
