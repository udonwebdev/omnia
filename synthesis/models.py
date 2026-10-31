"""
OMNIA Module 36: Autonomous Knowledge Synthesis & Intelligence Briefing Models
Provides typed contracts for intelligence products, synthesized claims, contradictions,
development changes, significance assessments, briefing versions, and delivery records.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional
import time
import uuid


class ProductType(str, Enum):
    EXECUTIVE_BRIEF = "EXECUTIVE_BRIEF"
    TECHNICAL_REPORT = "TECHNICAL_REPORT"
    SITUATION_REPORT = "SITUATION_REPORT"
    THREAT_SUMMARY = "THREAT_SUMMARY"
    RESEARCH_DIGEST = "RESEARCH_DIGEST"
    CHANGE_IMPACT = "CHANGE_IMPACT"
    DECISION_SUPPORT = "DECISION_SUPPORT"
    MISSION_SUMMARY = "MISSION_SUMMARY"
    PERSONALIZED_DIGEST = "PERSONALIZED_DIGEST"


class AudienceLevel(str, Enum):
    EXECUTIVE = "EXECUTIVE"
    TECHNICAL = "TECHNICAL"
    OPERATIONAL = "OPERATIONAL"
    RESEARCH = "RESEARCH"
    INTERNAL = "INTERNAL"


class ProductLifecycleState(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    STALE = "STALE"
    ARCHIVED = "ARCHIVED"


class EpistemicClaimType(str, Enum):
    DIRECT_OBSERVATION = "DIRECT_OBSERVATION"
    VERIFIED_FACT = "VERIFIED_FACT"
    INTERPRETATION = "INTERPRETATION"
    STATISTICAL_FINDING = "STATISTICAL_FINDING"
    FORECAST = "FORECAST"
    SIMULATION_RESULT = "SIMULATION_RESULT"
    HYPOTHESIS = "HYPOTHESIS"
    RECOMMENDATION = "RECOMMENDATION"
    UNKNOWN = "UNKNOWN"


class ChangeType(str, Enum):
    NEW = "NEW"
    UPDATED = "UPDATED"
    CONFIRMED = "CONFIRMED"
    CONTRADICTED = "CONTRADICTED"
    RESOLVED = "RESOLVED"
    EXPIRED = "EXPIRED"
    RETRACTED = "RETRACTED"
    NO_MATERIAL_CHANGE = "NO_MATERIAL_CHANGE"


class ContradictionStatus(str, Enum):
    UNRESOLVED = "UNRESOLVED"
    PARTIALLY_RESOLVED = "PARTIALLY_RESOLVED"
    RESOLVED = "RESOLVED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


class DeliveryStatus(str, Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


@dataclass
class IntelligenceProductRecord:
    product_id: str
    name: str
    purpose: str
    product_type: ProductType
    domain: str
    intended_audience: AudienceLevel
    authorized_scope: str
    required_sources: List[str]
    update_cadence: str  # e.g., "DAILY", "EVENT_DRIVEN", "ON_DEMAND"
    max_length_words: int = 1500
    freshness_window_sec: float = 86400.0  # 24 hours
    retention_days: int = 90
    approval_required: bool = False
    version: int = 1
    state: ProductLifecycleState = ProductLifecycleState.ACTIVE
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "product_id": self.product_id,
            "name": self.name,
            "purpose": self.purpose,
            "product_type": self.product_type.value,
            "domain": self.domain,
            "intended_audience": self.intended_audience.value,
            "authorized_scope": self.authorized_scope,
            "required_sources": self.required_sources,
            "update_cadence": self.update_cadence,
            "max_length_words": self.max_length_words,
            "freshness_window_sec": self.freshness_window_sec,
            "retention_days": self.retention_days,
            "approval_required": self.approval_required,
            "version": self.version,
            "state": self.state.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class SynthesizedClaim:
    claim_id: str
    briefing_version_id: str
    claim_text: str
    claim_type: EpistemicClaimType
    supporting_evidence_refs: List[str]
    contradictory_evidence_refs: List[str] = field(default_factory=list)
    confidence_assessment: str = "HIGH"  # HIGH, MEDIUM, LOW, PROVISIONAL
    confidence_score: float = 0.85
    temporal_scope: str = "CURRENT"
    known_assumptions: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "briefing_version_id": self.briefing_version_id,
            "claim_text": self.claim_text,
            "claim_type": self.claim_type.value,
            "supporting_evidence_refs": self.supporting_evidence_refs,
            "contradictory_evidence_refs": self.contradictory_evidence_refs,
            "confidence_assessment": self.confidence_assessment,
            "confidence_score": self.confidence_score,
            "temporal_scope": self.temporal_scope,
            "known_assumptions": self.known_assumptions,
            "limitations": self.limitations,
            "created_at": self.created_at,
        }


@dataclass
class ContradictionRecord:
    contradiction_id: str
    product_id: str
    claim_a: str
    claim_b: str
    source_a_ref: str
    source_b_ref: str
    divergence_reason: str
    status: ContradictionStatus = ContradictionStatus.UNRESOLVED
    resolution_evidence_needed: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contradiction_id": self.contradiction_id,
            "product_id": self.product_id,
            "claim_a": self.claim_a,
            "claim_b": self.claim_b,
            "source_a_ref": self.source_a_ref,
            "source_b_ref": self.source_b_ref,
            "divergence_reason": self.divergence_reason,
            "status": self.status.value,
            "resolution_evidence_needed": self.resolution_evidence_needed,
            "created_at": self.created_at,
        }


@dataclass
class DevelopmentRecord:
    development_id: str
    product_id: str
    change_type: ChangeType
    summary: str
    previous_state: Optional[str] = None
    new_state: Optional[str] = None
    source_refs: List[str] = field(default_factory=list)
    significance_score: float = 0.5  # 0.0 to 1.0
    detected_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "development_id": self.development_id,
            "product_id": self.product_id,
            "change_type": self.change_type.value,
            "summary": self.summary,
            "previous_state": self.previous_state,
            "new_state": self.new_state,
            "source_refs": self.source_refs,
            "significance_score": self.significance_score,
            "detected_at": self.detected_at,
        }


@dataclass
class SignificanceAssessment:
    assessment_id: str
    event_or_change_id: str
    urgency: float  # 0.0 to 1.0
    potential_impact: float  # 0.0 to 1.0
    evidence_reliability: float  # 0.0 to 1.0
    affected_blast_radius: int  # count of affected entities/subsystems
    overall_significance: float  # weighted score
    reasoning: str
    is_provisional: bool = False
    assessed_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "event_or_change_id": self.event_or_change_id,
            "urgency": self.urgency,
            "potential_impact": self.potential_impact,
            "evidence_reliability": self.evidence_reliability,
            "affected_blast_radius": self.affected_blast_radius,
            "overall_significance": self.overall_significance,
            "reasoning": self.reasoning,
            "is_provisional": self.is_provisional,
            "assessed_at": self.assessed_at,
        }


@dataclass
class BriefingQualityScore:
    passed: bool
    evidence_traceability_pct: float
    citation_integrity: bool
    epistemic_labeling_verified: bool
    contradiction_visibility: bool
    unsupported_claims_count: int
    quality_notes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "evidence_traceability_pct": self.evidence_traceability_pct,
            "citation_integrity": self.citation_integrity,
            "epistemic_labeling_verified": self.epistemic_labeling_verified,
            "contradiction_visibility": self.contradiction_visibility,
            "unsupported_claims_count": self.unsupported_claims_count,
            "quality_notes": self.quality_notes,
        }


@dataclass
class BriefingVersion:
    version_id: str
    product_id: str
    version_number: int
    title: str
    audience_level: AudienceLevel
    executive_summary: str
    rendered_content_markdown: str
    content_digest_sha256: str
    evidence_sources_count: int
    claims_count: int
    quality_score: Dict[str, Any]
    approval_token: Optional[str] = None
    is_stale: bool = False
    generated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version_id": self.version_id,
            "product_id": self.product_id,
            "version_number": self.version_number,
            "title": self.title,
            "audience_level": self.audience_level.value,
            "executive_summary": self.executive_summary,
            "rendered_content_markdown": self.rendered_content_markdown,
            "content_digest_sha256": self.content_digest_sha256,
            "evidence_sources_count": self.evidence_sources_count,
            "claims_count": self.claims_count,
            "quality_score": self.quality_score,
            "approval_token": self.approval_token,
            "is_stale": self.is_stale,
            "generated_at": self.generated_at,
        }


@dataclass
class DeliveryRecord:
    delivery_id: str
    briefing_version_id: str
    recipient_id: str
    channel: str  # e.g., "SLACK", "EMAIL", "HUD", "CONNECTOR"
    status: DeliveryStatus
    idempotency_key: str
    error_message: Optional[str] = None
    delivered_at: Optional[float] = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "delivery_id": self.delivery_id,
            "briefing_version_id": self.briefing_version_id,
            "recipient_id": self.recipient_id,
            "channel": self.channel,
            "status": self.status.value,
            "idempotency_key": self.idempotency_key,
            "error_message": self.error_message,
            "delivered_at": self.delivered_at,
            "created_at": self.created_at,
        }
