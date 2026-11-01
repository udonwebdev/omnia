"""OMNIA Video Studio — Module 42: Media Asset Provenance, Dependency Graph & Relinking Models.

Defines authoritative domain models for:
- AssetProvenanceRecord: Immutable history record of asset origins, imports, copies, and moves.
- RelinkMatchCandidate: Candidate file identified during relinking with match confidence and score breakdown.
- RelinkMatchConfidence: VERIFIED_EXACT, HIGH_PROBABILITY, PARTIAL_MATCH, UNVERIFIED.
- DependencyNode & DependencyEdge: Representation of project entities and directional relationships.
- ProjectDependencyGraph: Directed acyclic graph (DAG) of project resources (projects, sequences, clips, assets, LUTs).
- RelinkTransactionResult: Outcome of atomic relinking transactions with audit and rollback capabilities.
- AssetUsageReport: Detailed audit of which sequences, revisions, and branches utilize an asset.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


PROVENANCE_SCHEMA_VERSION = "video-studio.provenance.v1"


class DependencyNodeType(str, Enum):
    """Categorization of entities within a project's dependency graph."""
    PROJECT = "PROJECT"
    SEQUENCE = "SEQUENCE"
    TRACK = "TRACK"
    CLIP = "CLIP"
    MEDIA_ASSET = "MEDIA_ASSET"
    EXTERNAL_RESOURCE = "EXTERNAL_RESOURCE" # LUTs, fonts, subtitles, audio presets
    REVISION_SNAPSHOT = "REVISION_SNAPSHOT"


class DependencyEdgeType(str, Enum):
    """Relationship between two dependent nodes."""
    CONTAINS = "CONTAINS"              # Project -> Sequence, Track -> Clip
    REFERENCES = "REFERENCES"          # Clip -> MediaAsset
    REQUIRES_RESOURCE = "REQUIRES"     # Clip/Effect -> LUT / Font / Preset
    SNAPSHOT_PINS = "SNAPSHOT_PINS"    # RevisionSnapshot -> MediaAsset


class RelinkMatchConfidence(str, Enum):
    """Confidence grade assigned to a candidate file during intelligent relinking."""
    VERIFIED_EXACT = "VERIFIED_EXACT"       # SHA-256 fingerprint exact match (100% confidence)
    HIGH_PROBABILITY = "HIGH_PROBABILITY"   # Same size, duration, stream characteristics & filename (85-99%)
    PARTIAL_MATCH = "PARTIAL_MATCH"         # Filename and extension match, but size/duration unverified (50-84%)
    UNVERIFIED = "UNVERIFIED"               # Name similarity or fuzzy match (< 50%)


@dataclass
class AssetProvenanceRecord:
    """Historical audit trail entry for an asset's provenance."""
    record_id: str = field(default_factory=lambda: f"prov_{uuid.uuid4().hex[:10]}")
    asset_id: str = ""
    event_type: str = "INGEST"              # INGEST, RELINK, MOVE, RENAME, CHECKSUM_UPDATE
    actor_id: str = "system"
    previous_location: Optional[str] = None
    new_location: str = ""
    previous_checksum: Optional[str] = None
    new_checksum: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    rationale: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "asset_id": self.asset_id,
            "event_type": self.event_type,
            "actor_id": self.actor_id,
            "previous_location": self.previous_location,
            "new_location": self.new_location,
            "previous_checksum": self.previous_checksum,
            "new_checksum": self.new_checksum,
            "timestamp": self.timestamp,
            "rationale": self.rationale,
            "details": dict(self.details),
        }


@dataclass
class RelinkMatchCandidate:
    """Potential replacement file discovered during an intelligent relink search."""
    candidate_id: str = field(default_factory=lambda: f"cand_{uuid.uuid4().hex[:8]}")
    file_path: str = ""
    filename: str = ""
    size_bytes: int = 0
    content_fingerprint_sha256: Optional[str] = None
    confidence: RelinkMatchConfidence = RelinkMatchConfidence.UNVERIFIED
    score: float = 0.0                      # Normalized matching score [0.0 - 1.0]
    match_reasons: List[str] = field(default_factory=list)
    is_verified: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "file_path": self.file_path,
            "filename": self.filename,
            "size_bytes": self.size_bytes,
            "content_fingerprint_sha256": self.content_fingerprint_sha256,
            "confidence": self.confidence.value,
            "score": round(self.score, 3),
            "match_reasons": list(self.match_reasons),
            "is_verified": self.is_verified,
        }


@dataclass
class DependencyNode:
    """A discrete node in the project resource dependency graph."""
    node_id: str
    node_type: DependencyNodeType
    label: str
    is_missing: bool = False
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "label": self.label,
            "is_missing": self.is_missing,
            "details": dict(self.details),
        }


@dataclass
class DependencyEdge:
    """A directed edge expressing a relationship between two dependency nodes."""
    source_id: str
    target_id: str
    edge_type: DependencyEdgeType
    is_required: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type.value,
            "is_required": self.is_required,
            "metadata": dict(self.metadata),
        }


@dataclass
class ProjectDependencyGraph:
    """Directed dependency graph of all assets and structural entities within a project."""
    project_id: str
    nodes: Dict[str, DependencyNode] = field(default_factory=dict)
    edges: List[DependencyEdge] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def add_node(self, node: DependencyNode) -> None:
        self.nodes[node.node_id] = node

    def add_edge(self, edge: DependencyEdge) -> None:
        self.edges.append(edge)

    def get_dependents(self, node_id: str) -> List[str]:
        """Finds all node IDs that depend on (point to) this node."""
        return [e.source_id for e in self.edges if e.target_id == node_id]

    def get_dependencies(self, node_id: str) -> List[str]:
        """Finds all node IDs that this node depends on (points to)."""
        return [e.target_id for e in self.edges if e.source_id == node_id]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "created_at": self.created_at,
        }


@dataclass
class RelinkTransactionResult:
    """Report detailing the result of an asset relink operation."""
    success: bool = True
    project_id: str = ""
    relinked_assets_count: int = 0
    updated_clips_count: int = 0
    relinked_pairs: List[Dict[str, Any]] = field(default_factory=list)
    missing_after_relink: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    is_dry_run: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "project_id": self.project_id,
            "relinked_assets_count": self.relinked_assets_count,
            "updated_clips_count": self.updated_clips_count,
            "relinked_pairs": list(self.relinked_pairs),
            "missing_after_relink": list(self.missing_after_relink),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "is_dry_run": self.is_dry_run,
        }


@dataclass
class AssetUsageReport:
    """Usage analysis for an asset across active sequences, revisions, and branches."""
    asset_id: str
    is_used_in_active_project: bool = False
    active_sequence_ids: List[str] = field(default_factory=list)
    active_clip_ids: List[str] = field(default_factory=list)
    referenced_in_revisions: List[str] = field(default_factory=list)
    referenced_in_branches: List[str] = field(default_factory=list)
    total_reference_count: int = 0
    is_safe_to_delete: bool = False
    safety_blockers: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "is_used_in_active_project": self.is_used_in_active_project,
            "active_sequence_ids": list(self.active_sequence_ids),
            "active_clip_ids": list(self.active_clip_ids),
            "referenced_in_revisions": list(self.referenced_in_revisions),
            "referenced_in_branches": list(self.referenced_in_branches),
            "total_reference_count": self.total_reference_count,
            "is_safe_to_delete": self.is_safe_to_delete,
            "safety_blockers": list(self.safety_blockers),
        }
