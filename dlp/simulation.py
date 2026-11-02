"""
dlp/simulation.py
DLP Policy Testing & Synthetic Traffic Simulation Engine for OMNIA Module 52:
Autonomous Data Loss Prevention, Sensitive Information Monitoring & Exfiltration Defense Intelligence.
"""

import uuid
import time
import hashlib
import json
from typing import List, Dict, Any, Optional

from dlp.models import (
    DLPPolicy, MovementEvent, SensitiveFinding,
    TransferDecision, DLPDecision, ActionStatus
)
from dlp.policy_engine import DLPPolicyEngine
from dlp.persistence import DLPRepository


class DLPPolicySimulator:
    """
    Simulates proposed DLP policies against historical traffic or synthetic scenarios
    without impacting production systems or executing containment actions.
    """

    def __init__(self, repo: DLPRepository, policy_engine: DLPPolicyEngine):
        self.repo = repo
        self.policy_engine = policy_engine

    def simulate_policy_impact(
        self,
        candidate_policy: DLPPolicy,
        events: Optional[List[MovementEvent]] = None,
        findings_map: Optional[Dict[str, List[SensitiveFinding]]] = None
    ) -> Dict[str, Any]:
        """
        Replays candidate policy against provided or historical movement events.
        Produces a simulated impact report with false-positive estimations.
        """
        eval_events = events
        if not eval_events:
            eval_events = self.repo.list_movement_events(limit=200)

        findings_lookup = findings_map or {}
        
        breakdown: Dict[str, int] = {
            DLPDecision.ALLOW.value: 0,
            DLPDecision.BLOCK.value: 0,
            DLPDecision.QUARANTINE.value: 0,
            DLPDecision.APPROVAL_REQUIRED.value: 0,
            DLPDecision.REDACT.value: 0,
        }

        impacted_actors = set()
        blocked_volume = 0
        detailed_simulated_outcomes: List[Dict[str, Any]] = []

        for ev in eval_events:
            ev_findings = findings_lookup.get(ev.event_id, [])
            
            # Check match against candidate policy specifically
            if self.policy_engine._matches_policy(candidate_policy, ev, ev_findings, None, []):
                decision_type, reason = self.policy_engine._resolve_decision(candidate_policy, ev, ev_findings, None, [])
                breakdown[decision_type.value] = breakdown.get(decision_type.value, 0) + 1
                
                if decision_type in (DLPDecision.BLOCK, DLPDecision.QUARANTINE, DLPDecision.APPROVAL_REQUIRED):
                    impacted_actors.add(ev.actor_id)
                    blocked_volume += ev.volume_bytes

                detailed_simulated_outcomes.append({
                    "event_id": ev.event_id,
                    "simulated_decision": decision_type.value,
                    "reason": reason,
                    "actor_id": ev.actor_id,
                    "volume_bytes": ev.volume_bytes,
                    "action_status": ActionStatus.SIMULATED.value,
                })
            else:
                breakdown[DLPDecision.ALLOW.value] += 1

        total_evaluated = len(eval_events)
        blocked_or_quarantined = breakdown[DLPDecision.BLOCK.value] + breakdown[DLPDecision.QUARANTINE.value]
        block_rate = (blocked_or_quarantined / total_evaluated) if total_evaluated > 0 else 0.0

        if block_rate > 0.40:
            fp_risk = "HIGH_FALSE_POSITIVE_RISK: Policy blocks over 40% of baseline traffic."
        elif block_rate > 0.15:
            fp_risk = "MODERATE_IMPACT: Policy will disrupt 15-40% of current movements."
        else:
            fp_risk = "LOW_IMPACT: Narrowly targeted policy with minimal disruption to normal workflows."

        summary_payload = {
            "policy_id": candidate_policy.policy_id,
            "policy_name": candidate_policy.name,
            "total_events_replayed": total_evaluated,
            "decisions_breakdown": breakdown,
            "impacted_actors_count": len(impacted_actors),
            "blocked_volume_bytes": blocked_volume,
            "estimated_false_positive_risk": fp_risk,
            "simulated_at": time.time(),
        }

        seal = hashlib.sha256(json.dumps(summary_payload, sort_keys=True).encode()).hexdigest()
        summary_payload["simulation_seal"] = seal
        summary_payload["detailed_simulated_outcomes"] = detailed_simulated_outcomes[:20]

        return summary_payload
