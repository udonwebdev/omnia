"""
Domain models for Omnia Module 29: Evidence & Decision Engine.

Core Principles:
- RAW DATA != NORMALIZED DATA != DERIVED DATA != KNOWLEDGE != MEMORY != TRUTH
- A conclusion is not an LLM hallucination: it is a reproducible, evidence-backed state.
- Uncertainty, conflict, and abstention are first-class citizens.
- Decisions can expire, degrade, or be invalidated by new evidence.
"""

import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


class ClaimStatus(str, Enum):
    PENDING = "PENDING"
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    REFUTED = "REFUTED"


class EvidenceStance(str, Enum):
    SUPPORTING = "SUPPORTING"
    CONTRADICTING = "CONTRADICTING"
    NEUTRAL = "NEUTRAL"


class DecisionState(str, Enum):
    EVALUATING = "EVALUATING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    DISPUTED = "DISPUTED"
    ABSTAINED = "ABSTAINED"
    EXPIRED = "EXPIRED"


class ConflictSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class EvidenceLink:
    """Explicit weighted link connecting an evidence item to a claim."""
    link_id: str
    decision_id: str
    claim_id: str
    evidence_id: str
    stance: EvidenceStance
    weight: float = 1.0
    provenance_hash: str = "prov_link_0"
    linked_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "link_id": self.link_id,
            "decision_id": self.decision_id,
            "claim_id": self.claim_id,
            "evidence_id": self.evidence_id,
            "stance": self.stance.value,
            "weight": self.weight,
            "provenance_hash": self.provenance_hash,
            "linked_at": self.linked_at
        }


@dataclass
class Claim:
    """Atomic evaluatable proposition backed by evidence."""
    claim_id: str
    decision_id: str
    statement: str
    status: ClaimStatus = ClaimStatus.PENDING
    confidence_score: float = 0.0  # [0.0, 1.0]
    supporting_evidence_count: int = 0
    contradicting_evidence_count: int = 0
    evaluated_at: float = field(default_factory=time.time)
    rationale: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "decision_id": self.decision_id,
            "statement": self.statement,
            "status": self.status.value,
            "confidence_score": round(self.confidence_score, 4),
            "supporting_evidence_count": self.supporting_evidence_count,
            "contradicting_evidence_count": self.contradicting_evidence_count,
            "evaluated_at": self.evaluated_at,
            "rationale": self.rationale,
            "metadata": self.metadata
        }


@dataclass
class DecisionConflict:
    """Detected contradiction between evidence or claims."""
    conflict_id: str
    decision_id: str
    claim_id: str
    conflict_type: str
    severity: ConflictSeverity = ConflictSeverity.MEDIUM
    resolution_state: str = "UNRESOLVED"
    resolved_by: Optional[str] = None
    resolution_rationale: Optional[str] = None
    detected_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "decision_id": self.decision_id,
            "claim_id": self.claim_id,
            "conflict_type": self.conflict_type,
            "severity": self.severity.value,
            "resolution_state": self.resolution_state,
            "resolved_by": self.resolved_by,
            "resolution_rationale": self.resolution_rationale,
            "detected_at": self.detected_at,
            "resolved_at": self.resolved_at,
            "metadata": self.metadata
        }


@dataclass
class DecisionPolicy:
    """Thresholds and rules governing whether a decision can be accepted or must abstain."""
    policy_id: str = "default_decision_policy"
    min_confidence_to_accept: float = 0.70
    max_contradiction_ratio: float = 0.25
    require_supporting_evidence: bool = True
    min_supporting_sources: int = 1
    max_uncertainty: float = 0.40
    ttl_seconds: float = 86400.0  # 24 hours


@dataclass
class DecisionRecord:
    """Authoritative, verifiable conclusion synthesized by Module 29."""
    decision_id: str
    subject_id: str
    decision_type: str
    state: DecisionState
    confidence_score: float
    uncertainty_score: float = 0.0
    primary_claim_id: Optional[str] = None
    summary: str = ""
    evaluated_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    actor_id: str = "system"
    policy_version: str = "1.0.0"
    metadata: Dict[str, Any] = field(default_factory=dict)
    claims: List[Claim] = field(default_factory=list)
    evidence_links: List[EvidenceLink] = field(default_factory=list)
    conflicts: List[DecisionConflict] = field(default_factory=list)

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "subject_id": self.subject_id,
            "decision_type": self.decision_type,
            "state": self.state.value,
            "confidence_score": round(self.confidence_score, 4),
            "uncertainty_score": round(self.uncertainty_score, 4),
            "primary_claim_id": self.primary_claim_id,
            "summary": self.summary,
            "evaluated_at": self.evaluated_at,
            "expires_at": self.expires_at,
            "actor_id": self.actor_id,
            "policy_version": self.policy_version,
            "metadata": self.metadata,
            "claims": [c.to_dict() for c in self.claims],
            "evidence_links": [l.to_dict() for l in self.evidence_links],
            "conflicts": [cf.to_dict() for cf in self.conflicts]
        }
