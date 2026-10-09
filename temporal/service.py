"""
Omnia Module 31: Temporal Knowledge & Causal State Service
Orchestrates bi-temporal state recording, point-in-time state reconstruction,
causal link assertions, and root-cause tracing.
"""

import uuid
import time
import logging
from typing import Dict, Any, List, Optional

from temporal.models import (
    TemporalStateRecord,
    CausalLink,
    CausalEvidenceBinding,
    CausalRelationType,
    CausalStatus,
    EvidenceSupportType,
    StateTransitionDiff,
    CausalChain,
)
from temporal.persistence import TemporalPersistence
from temporal.engine import TemporalEngine
from temporal.causal import CausalReasoner
from events.fabric import event_fabric, EventFabric
from events.models import Event, EventEnvelope
from capabilities.registry import capability_registry, CapabilityRegistry

logger = logging.getLogger("Omnia.Temporal.Service")


class TemporalCausalService:
    def __init__(
        self,
        persistence: Optional[TemporalPersistence] = None,
        event_bus: Optional[EventFabric] = None,
        registry: Optional[CapabilityRegistry] = None,
        engine: Optional[TemporalEngine] = None,
        reasoner: Optional[CausalReasoner] = None,
    ):
        self.persistence = persistence or TemporalPersistence()
        self.event_bus = event_bus or event_fabric
        self.registry = registry or capability_registry
        self.engine = engine or TemporalEngine(self.persistence)
        self.reasoner = reasoner or CausalReasoner(self.persistence)

        self._register_capabilities()

    def _register_capabilities(self) -> None:
        try:
            from capabilities.models import (
                Capability, CapabilityCategory, CapabilityProvider,
                CapabilityHealth, RiskLevel, SideEffectType, IdempotencyType
            )
            cap = Capability(
                capability_id="temporal.causal_operations",
                name="Temporal Knowledge & Causal State Engine",
                category=CapabilityCategory.MEMORY,
                provider=CapabilityProvider(
                    provider_id="provider.temporal.local",
                    name="Temporal Causal Engine",
                    node_id="local",
                    is_local=True
                ),
                version="1.0.0",
                health=CapabilityHealth.HEALTHY,
                risk_level=RiskLevel.LOW,
                side_effect_type=SideEffectType.READ,
                idempotency=IdempotencyType.STRICTLY_IDEMPOTENT
            )
            self.registry.register_capability(cap)
            logger.info("Registered temporal.causal_operations capability into registry.")
        except Exception as e:
            logger.debug(f"Temporal capability registration bypassed: {e}")

    def _emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        if self.event_bus:
            try:
                import asyncio
                envelope = EventEnvelope(
                    event_id=f"evt_{uuid.uuid4().hex[:12]}",
                    event_type=event_type,
                    source="temporal_causal_service"
                )
                ev = Event(envelope=envelope, payload=payload)
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(self.event_bus.publish(ev))
                    else:
                        loop.run_until_complete(self.event_bus.publish(ev))
                except RuntimeError:
                    asyncio.run(self.event_bus.publish(ev))
            except Exception as e:
                logger.debug(f"Temporal event emission bypassed: {e}")

    # --- TEMPORAL STATE OPERATIONS ---

    def _to_timestamp(self, val: Any) -> Optional[float]:
        if val is None or val == "":
            return None
        if isinstance(val, (int, float)):
            return float(val)
        from datetime import datetime
        if isinstance(val, datetime):
            return val.timestamp()
        if isinstance(val, str):
            try:
                return datetime.fromisoformat(val).timestamp()
            except Exception:
                return float(val)
        return None

    def record_entity_state(
        self,
        entity_id: str,
        state_payload: Dict[str, Any],
        valid_from: Optional[Any] = None,
        valid_until: Optional[Any] = None,
        recorded_by: str = "system",
        evidence_id: Optional[str] = None,
        auto_close_previous: bool = True,
    ) -> TemporalStateRecord:
        now = time.time()
        vf = self._to_timestamp(valid_from)
        vu = self._to_timestamp(valid_until)
        v_from = vf if vf is not None else now

        if auto_close_previous:
            self.persistence.close_previous_state(entity_id=entity_id, until_time=v_from)

        record_id = f"state-{uuid.uuid4().hex[:12]}"
        rec = TemporalStateRecord(
            state_id=record_id,
            entity_id=entity_id,
            valid_from=v_from,
            valid_until=vu,
            transaction_time=now,
            recorded_by=recorded_by,
            state_payload=state_payload,
            evidence_id=evidence_id,
            created_at=now,
        )
        self.persistence.record_state(rec)

        self._emit(
            "temporal.state_recorded",
            {
                "state_id": record_id,
                "entity_id": entity_id,
                "valid_from": v_from,
                "transaction_time": now,
            },
        )
        return rec

    def record_state(self, *args, **kwargs) -> TemporalStateRecord:
        """Alias for record_entity_state."""
        return self.record_entity_state(*args, **kwargs)

    def reconstruct_state_as_of(
        self,
        entity_id: str,
        valid_time: Any,
        transaction_time: Optional[Any] = None,
    ) -> Optional[TemporalStateRecord]:
        vt = self._to_timestamp(valid_time) or time.time()
        tt = self._to_timestamp(transaction_time)
        winner = self.engine.reconstruct_state_as_of(
            entity_id=entity_id,
            as_of_valid_time=vt,
            as_of_transaction_time=tt,
        )
        self._emit(
            "temporal.state_reconstructed",
            {
                "entity_id": entity_id,
                "as_of_valid_time": vt,
                "as_of_tx_time": tt or time.time(),
                "found": winner is not None,
            },
        )
        return winner

    def reconstruct_state(self, *args, **kwargs) -> Optional[TemporalStateRecord]:
        """Alias for reconstruct_state_as_of."""
        return self.reconstruct_state_as_of(*args, **kwargs)

    def detect_transitions(
        self,
        entity_id: str,
        start_valid_time: Optional[Any] = None,
        end_valid_time: Optional[Any] = None,
    ) -> List[StateTransitionDiff]:
        svt = self._to_timestamp(start_valid_time)
        evt = self._to_timestamp(end_valid_time)
        return self.engine.detect_state_transitions(
            entity_id=entity_id,
            start_valid_time=svt,
            end_valid_time=evt,
        )

    def detect_state_transitions(self, *args, **kwargs) -> List[StateTransitionDiff]:
        """Alias for detect_transitions."""
        return self.detect_transitions(*args, **kwargs)

    # --- CAUSAL OPERATIONS ---

    def assert_causal_link(
        self,
        cause_entity_id: str,
        effect_entity_id: str,
        relation_type: str = "RESULTED_IN",
        confidence: float = 1.0,
        evidence_ids: Optional[List[str]] = None,
        mechanism_description: Optional[str] = None,
        observed_lag_sec: float = 0.0,
        status: str = "HYPOTHESIZED",
    ) -> CausalLink:
        r_type = CausalRelationType(relation_type.upper()) if relation_type.upper() in CausalRelationType.__members__ else CausalRelationType.RESULTED_IN
        c_stat = CausalStatus(status.upper()) if status.upper() in CausalStatus.__members__ else CausalStatus.HYPOTHESIZED

        link_id = f"clink-{uuid.uuid4().hex[:12]}"
        now = time.time()
        link = CausalLink(
            causal_link_id=link_id,
            cause_entity_id=cause_entity_id,
            effect_entity_id=effect_entity_id,
            relation_type=r_type,
            confidence=confidence,
            evidence_ids=evidence_ids or [],
            mechanism_description=mechanism_description,
            observed_lag_sec=observed_lag_sec,
            status=c_stat,
            created_at=now,
            updated_at=now,
        )
        self.persistence.record_causal_link(link)

        # Bind evidence if provided
        if evidence_ids:
            for ev_id in evidence_ids:
                binding = CausalEvidenceBinding(
                    binding_id=f"bind-{uuid.uuid4().hex[:10]}",
                    causal_link_id=link_id,
                    evidence_id=ev_id,
                    support_type=EvidenceSupportType.SUPPORTS,
                    strength=confidence,
                    created_at=now,
                )
                self.persistence.bind_evidence(binding)

        self._emit(
            "causal.link_asserted",
            {
                "causal_link_id": link_id,
                "cause_entity_id": cause_entity_id,
                "effect_entity_id": effect_entity_id,
                "confidence": confidence,
            },
        )
        return link

    def trace_root_causes(self, effect_entity_id: str, max_depth: int = 5) -> List[CausalChain]:
        return self.reasoner.trace_root_causes(effect_entity_id=effect_entity_id, max_depth=max_depth)

    def trace_blast_radius(self, cause_entity_id: str, max_depth: int = 5) -> List[CausalChain]:
        return self.reasoner.trace_consequences(cause_entity_id=cause_entity_id, max_depth=max_depth)

    def trace_causal_chain(
        self,
        entity_id: str,
        direction: str = "ROOT_CAUSE",
        max_depth: int = 5
    ) -> CausalChain:
        """Traces backward for root cause or forward for consequence blast radius."""
        dir_clean = direction.upper()
        if dir_clean in ("ROOT_CAUSE", "BACKWARD"):
            chains = self.trace_root_causes(effect_entity_id=entity_id, max_depth=max_depth)
            if chains:
                # Return the most direct or highest confidence chain
                res = sorted(chains, key=lambda c: c.overall_confidence, reverse=True)[0]
                res.direction = "ROOT_CAUSE"
                return res
            # Return an identity chain if none found
            from temporal.models import CausalChainNode
            return CausalChain(
                root_cause_id=entity_id,
                target_effect_id=entity_id,
                nodes=[CausalChainNode(entity_id=entity_id, step_depth=0)],
                overall_confidence=1.0,
                direction="ROOT_CAUSE",
            )
        else:
            chains = self.trace_blast_radius(cause_entity_id=entity_id, max_depth=max_depth)
            if chains:
                res = sorted(chains, key=lambda c: c.overall_confidence, reverse=True)[0]
                res.direction = "CONSEQUENCE"
                return res
            from temporal.models import CausalChainNode
            return CausalChain(
                root_cause_id=entity_id,
                target_effect_id=entity_id,
                nodes=[CausalChainNode(entity_id=entity_id, step_depth=0)],
                overall_confidence=1.0,
                direction="CONSEQUENCE",
            )


# Default global instance
temporal_causal_service = TemporalCausalService()
