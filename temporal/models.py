"""
Omnia Module 31: Temporal Knowledge & Causal State Engine Models
Authoritative bi-temporal state representations, causal relationships,
evidence bindings, and state transitions.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional
import time
import uuid


class CausalRelationType(str, Enum):
    TRIGGERED = "TRIGGERED"
    CAUSED_BY = "CAUSED_BY"
    ENABLED = "ENABLED"
    PREVENTED = "PREVENTED"
    RESULTED_IN = "RESULTED_IN"
    INFLUENCED = "INFLUENCED"
    CORRELATED_WITH = "CORRELATED_WITH"


class CausalStatus(str, Enum):
    HYPOTHESIZED = "HYPOTHESIZED"
    CONFIRMED = "CONFIRMED"
    DISPUTED = "DISPUTED"
    REFUTED = "REFUTED"


class EvidenceSupportType(str, Enum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass
class TemporalStateRecord:
    state_id: str
    entity_id: str
    valid_from: float
    valid_until: Optional[float] = None  # None indicates currently active
    transaction_time: float = field(default_factory=time.time)
    recorded_by: str = "system"
    state_payload: Dict[str, Any] = field(default_factory=dict)
    is_deleted: bool = False
    evidence_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    @property
    def record_id(self) -> str:
        return self.state_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state_id": self.state_id,
            "record_id": self.state_id,
            "entity_id": self.entity_id,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "transaction_time": self.transaction_time,
            "recorded_by": self.recorded_by,
            "state_payload": self.state_payload,
            "is_deleted": self.is_deleted,
            "evidence_id": self.evidence_id,
            "created_at": self.created_at,
        }


@dataclass
class CausalLink:
    causal_link_id: str
    cause_entity_id: str
    effect_entity_id: str
    relation_type: CausalRelationType
    confidence: float = 1.0
    evidence_ids: List[str] = field(default_factory=list)
    mechanism_description: Optional[str] = None
    observed_lag_sec: float = 0.0
    status: CausalStatus = CausalStatus.HYPOTHESIZED
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "causal_link_id": self.causal_link_id,
            "cause_entity_id": self.cause_entity_id,
            "effect_entity_id": self.effect_entity_id,
            "relation_type": self.relation_type.value if isinstance(self.relation_type, CausalRelationType) else str(self.relation_type),
            "confidence": self.confidence,
            "evidence_ids": self.evidence_ids,
            "mechanism_description": self.mechanism_description,
            "observed_lag_sec": self.observed_lag_sec,
            "status": self.status.value if isinstance(self.status, CausalStatus) else str(self.status),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class CausalEvidenceBinding:
    binding_id: str
    causal_link_id: str
    evidence_id: str
    support_type: EvidenceSupportType = EvidenceSupportType.SUPPORTS
    strength: float = 1.0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "binding_id": self.binding_id,
            "causal_link_id": self.causal_link_id,
            "evidence_id": self.evidence_id,
            "support_type": self.support_type.value if isinstance(self.support_type, EvidenceSupportType) else str(self.support_type),
            "strength": self.strength,
            "created_at": self.created_at,
        }


@dataclass
class StateTransitionDiff:
    entity_id: str
    from_state_id: Optional[str]
    to_state_id: str
    transition_time: float
    changed_keys: List[str] = field(default_factory=list)
    previous_values: Dict[str, Any] = field(default_factory=dict)
    new_values: Dict[str, Any] = field(default_factory=dict)

    @property
    def from_state(self) -> Dict[str, Any]:
        return self.previous_values

    @property
    def to_state(self) -> Dict[str, Any]:
        return self.new_values

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "from_state_id": self.from_state_id,
            "to_state_id": self.to_state_id,
            "transition_time": self.transition_time,
            "changed_keys": self.changed_keys,
            "previous_values": self.previous_values,
            "new_values": self.new_values,
        }


@dataclass
class CausalChainNode:
    entity_id: str
    step_depth: int
    relation_to_next: Optional[str] = None
    step_confidence: float = 1.0
    cumulative_confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "step_depth": self.step_depth,
            "relation_to_next": self.relation_to_next,
            "step_confidence": self.step_confidence,
            "cumulative_confidence": self.cumulative_confidence,
        }


@dataclass
class CausalChain:
    root_cause_id: str
    target_effect_id: str
    nodes: List[CausalChainNode] = field(default_factory=list)
    overall_confidence: float = 1.0
    has_cycles: bool = False
    direction: str = "ROOT_CAUSE"

    @property
    def root_entity_id(self) -> str:
        return self.target_effect_id if self.direction == "ROOT_CAUSE" else self.root_cause_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root_cause_id": self.root_cause_id,
            "target_effect_id": self.target_effect_id,
            "root_entity_id": self.root_entity_id,
            "direction": self.direction,
            "nodes": [n.to_dict() for n in self.nodes],
            "overall_confidence": self.overall_confidence,
            "has_cycles": self.has_cycles,
        }
