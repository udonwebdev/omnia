"""
Authoritative Service Orchestrator for Module 29 Evidence & Decision Engine.
Integrates with Module 09 (Policy), Module 17 (Capabilities), Module 18 (Event Fabric), and Module 28 (Retrieval).
"""

import uuid
import time
import logging
from typing import Dict, Any, List, Optional, Tuple

from decision.models import (
    DecisionRecord,
    DecisionState,
    Claim,
    ClaimStatus,
    DecisionConflict,
    EvidenceLink,
    DecisionPolicy
)
from decision.evaluator import DecisionEvaluator
from decision.persistence import DecisionPersistence
from retrieval.models import SearchQuery, SearchFilter, SearchResult, EvidenceItem, DataClassification
from retrieval.service import UnifiedSearchService, unified_search_service
from events.fabric import event_fabric
from events.models import Event, EventEnvelope
from policy_engine import policy_engine
from capabilities.registry import capability_registry
from capabilities.models import (
    Capability, CapabilityCategory, CapabilityProvider,
    CapabilityHealth, RiskLevel, SideEffectType, IdempotencyType
)

logger = logging.getLogger("Omnia.Decision.Service")


class EvidenceDecisionService:
    """Coordinates evidence aggregation, claim evaluation, conflict resolution, and policy-driven conclusions."""

    def __init__(
        self,
        persistence: Optional[DecisionPersistence] = None,
        evaluator: Optional[DecisionEvaluator] = None,
        retrieval_service: Optional[UnifiedSearchService] = None,
        node_id: str = "local_node"
    ):
        self.node_id = node_id
        self.persistence = persistence or DecisionPersistence()
        self.evaluator = evaluator or DecisionEvaluator()
        self.retrieval = retrieval_service or unified_search_service

        self._register_capabilities()

    def _register_capabilities(self) -> None:
        try:
            cap = Capability(
                capability_id="decision.evaluate_subject",
                name="Evaluate Evidence & Reach Decision",
                category=CapabilityCategory.DECISION,
                provider=CapabilityProvider(
                    provider_id=f"provider.decision.{self.node_id}",
                    name="Evidence & Decision Engine",
                    node_id=self.node_id,
                    is_local=True
                ),
                version="1.0.0",
                health=CapabilityHealth.HEALTHY,
                risk_level=RiskLevel.LOW,
                side_effect_type=SideEffectType.READ,
                idempotency=IdempotencyType.STRICTLY_IDEMPOTENT
            )
            capability_registry.register_capability(cap)
            logger.info("Registered decision.evaluate_subject capability into registry.")
        except Exception as e:
            logger.debug(f"Decision capability registration bypassed: {e}")

    def evaluate(
        self,
        subject_id: str,
        decision_type: str,
        claims_text: List[str],
        policy: Optional[DecisionPolicy] = None,
        actor_id: str = "system",
        pre_gathered_evidence: Optional[List[EvidenceItem]] = None
    ) -> DecisionRecord:
        """Evaluates claims against aggregated evidence and commits an authoritative conclusion."""
        t0 = time.perf_counter()
        active_policy = policy or DecisionPolicy()
        decision_id = f"dec_{uuid.uuid4().hex[:12]}"

        # 1. Policy Authorization Check
        allowed, reason = policy_engine.verify_action("decision.evaluate", {
            "actor_id": actor_id,
            "subject_id": subject_id,
            "decision_type": decision_type
        })
        if not allowed:
            logger.warning(f"Decision evaluation denied by policy: {reason}")
            dec = DecisionRecord(
                decision_id=decision_id,
                subject_id=subject_id,
                decision_type=decision_type,
                state=DecisionState.ABSTAINED,
                confidence_score=0.0,
                uncertainty_score=1.0,
                summary=f"Policy Denied: {reason}",
                evaluated_at=time.time(),
                actor_id=actor_id
            )
            self._emit_event("decision.abstained", {
                "decision_id": decision_id,
                "reason": f"POLICY_DENIED: {reason}"
            })
            return dec

        # 2. Gather Evidence if not pre-provided
        evidence_items = pre_gathered_evidence or []
        if not evidence_items:
            for text in claims_text:
                search_res = self.retrieval.search(
                    query_text=text,
                    filters=SearchFilter(max_classification=DataClassification.INTERNAL),
                    limit=5,
                    actor_id=actor_id
                )
                evidence_items.extend(search_res.evidence_items)

        # 3. Instantiate Claims
        claims = [
            Claim(
                claim_id=f"clm_{uuid.uuid4().hex[:12]}",
                decision_id=decision_id,
                statement=stmt
            )
            for stmt in claims_text
        ]

        # 4. Evaluate Claims & Detect Conflicts
        evaluated_claims, links, conflicts = self.evaluator.evaluate_claims(
            decision_id=decision_id,
            claims=claims,
            evidence_items=evidence_items,
            policy=active_policy
        )

        # 5. Synthesize Verifiable Conclusion
        decision_record = self.evaluator.synthesize_decision(
            decision_id=decision_id,
            subject_id=subject_id,
            decision_type=decision_type,
            claims=evaluated_claims,
            evidence_links=links,
            conflicts=conflicts,
            policy=active_policy,
            actor_id=actor_id
        )

        # 6. Durable Persistence
        self.persistence.save_decision(decision_record)

        # 7. Event Fabric Notification
        self._emit_event("decision.evaluated", {
            "decision_id": decision_record.decision_id,
            "subject_id": decision_record.subject_id,
            "state": decision_record.state.value,
            "confidence_score": decision_record.confidence_score
        })

        if conflicts:
            self._emit_event("decision.conflict_detected", {
                "conflict_id": conflicts[0].conflict_id,
                "claim_id": conflicts[0].claim_id,
                "conflicting_evidence": len(conflicts)
            })

        return decision_record

    def get_decision(self, decision_id: str) -> Optional[DecisionRecord]:
        return self.persistence.get_decision(decision_id)

    def _emit_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        try:
            evt = Event(
                id=f"evt_{uuid.uuid4().hex[:12]}",
                type=event_type,
                source="decision.engine",
                timestamp=time.time(),
                payload=payload
            )
            event_fabric.publish(EventEnvelope(event=evt))
        except Exception as e:
            logger.debug(f"Event emission bypassed: {e}")


evidence_decision_service = EvidenceDecisionService()
