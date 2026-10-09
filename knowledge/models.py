"""
Omnia Module 30: Knowledge Graph & Entity Resolution Engine Models
Authoritative data representations for persistent entities, typed relationships,
identity mappings, and resolution candidates.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional
import time
import uuid

# Reuse existing classification and boundaries where appropriate
from retrieval.models import DataClassification, TrustBoundary


class EntityType(str, Enum):
    PERSON = "PERSON"
    ORGANIZATION = "ORGANIZATION"
    SYSTEM = "SYSTEM"
    SERVICE = "SERVICE"
    LOCATION = "LOCATION"
    CONCEPT = "CONCEPT"
    RESOURCE = "RESOURCE"
    EVENT = "EVENT"
    CUSTOM = "CUSTOM"


class EntityStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    MERGED = "MERGED"
    TENTATIVE = "TENTATIVE"


class RelationshipStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INVALIDATED = "INVALIDATED"
    DISPUTED = "DISPUTED"


class IdentifierType(str, Enum):
    NAME = "NAME"
    ALIAS = "ALIAS"
    EMAIL = "EMAIL"
    URI = "URI"
    UUID = "UUID"
    EXTERNAL_KEY = "EXTERNAL_KEY"
    CUSTOM = "CUSTOM"


class ResolutionStatus(str, Enum):
    PENDING = "PENDING"
    RESOLVED_SAME = "RESOLVED_SAME"
    RESOLVED_DISTINCT = "RESOLVED_DISTINCT"
    SPLIT = "SPLIT"


@dataclass
class GraphEntity:
    entity_id: str
    canonical_name: str
    entity_type: EntityType
    aliases: List[str] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)
    classification: DataClassification = DataClassification.INTERNAL
    trust_boundary: TrustBoundary = TrustBoundary.TRUSTED_INTERNAL
    confidence: float = 1.0
    provenance_ids: List[str] = field(default_factory=list)
    status: EntityStatus = EntityStatus.ACTIVE
    merged_into_id: Optional[str] = None
    owner_node: str = "local"
    version: int = 1
    valid_from: float = field(default_factory=time.time)
    valid_until: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "canonical_name": self.canonical_name,
            "entity_type": self.entity_type.value if isinstance(self.entity_type, EntityType) else str(self.entity_type),
            "aliases": self.aliases,
            "attributes": self.attributes,
            "classification": self.classification.value if isinstance(self.classification, DataClassification) else str(self.classification),
            "trust_boundary": self.trust_boundary.value if isinstance(self.trust_boundary, TrustBoundary) else str(self.trust_boundary),
            "confidence": self.confidence,
            "provenance_ids": self.provenance_ids,
            "status": self.status.value if isinstance(self.status, EntityStatus) else str(self.status),
            "merged_into_id": self.merged_into_id,
            "owner_node": self.owner_node,
            "version": self.version,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class GraphRelationship:
    relationship_id: str
    source_id: str
    predicate: str  # e.g., DEPENDS_ON, OWNS, COMMUNICATES_WITH, LOCATED_AT, PART_OF, AUTHORED_BY, ASSOCIATED_WITH
    target_id: str
    properties: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    weight: float = 1.0
    directed: bool = True
    provenance_ids: List[str] = field(default_factory=list)
    status: RelationshipStatus = RelationshipStatus.ACTIVE
    valid_from: float = field(default_factory=time.time)
    valid_until: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "relationship_id": self.relationship_id,
            "source_id": self.source_id,
            "predicate": self.predicate,
            "target_id": self.target_id,
            "properties": self.properties,
            "confidence": self.confidence,
            "weight": self.weight,
            "directed": self.directed,
            "provenance_ids": self.provenance_ids,
            "status": self.status.value if isinstance(self.status, RelationshipStatus) else str(self.status),
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class EntityIdentity:
    identity_id: str
    entity_id: str
    identifier_type: IdentifierType
    identifier_value: str
    confidence: float = 1.0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "identity_id": self.identity_id,
            "entity_id": self.entity_id,
            "identifier_type": self.identifier_type.value if isinstance(self.identifier_type, IdentifierType) else str(self.identifier_type),
            "identifier_value": self.identifier_value,
            "confidence": self.confidence,
            "created_at": self.created_at,
        }


@dataclass
class ResolutionCandidate:
    candidate_id: str
    source_entity_id: str
    target_entity_id: str
    similarity_score: float
    match_reasons: List[str] = field(default_factory=list)
    status: ResolutionStatus = ResolutionStatus.PENDING
    evaluated_at: float = field(default_factory=time.time)
    resolution_notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "source_entity_id": self.source_entity_id,
            "target_entity_id": self.target_entity_id,
            "similarity_score": self.similarity_score,
            "match_reasons": self.match_reasons,
            "status": self.status.value if isinstance(self.status, ResolutionStatus) else str(self.status),
            "evaluated_at": self.evaluated_at,
            "resolution_notes": self.resolution_notes,
        }


@dataclass
class GraphTraversalPath:
    start_entity_id: str
    target_entity_id: str
    entities: List[GraphEntity] = field(default_factory=list)
    relationships: List[GraphRelationship] = field(default_factory=list)
    total_depth: int = 0
    path_weight: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_entity_id": self.start_entity_id,
            "target_entity_id": self.target_entity_id,
            "entities": [e.to_dict() for e in self.entities],
            "relationships": [r.to_dict() for r in self.relationships],
            "total_depth": self.total_depth,
            "path_weight": self.path_weight,
        }


@dataclass
class Subgraph:
    center_entity_id: str
    depth: int
    entities: List[GraphEntity] = field(default_factory=list)
    relationships: List[GraphRelationship] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "center_entity_id": self.center_entity_id,
            "depth": self.depth,
            "entities": [e.to_dict() for e in self.entities],
            "relationships": [r.to_dict() for r in self.relationships],
        }
