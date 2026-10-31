"""
Omnia Module 38: Autonomous Goal Management, Outcome Tracking & Strategic Execution Intelligence.
Outcome Verification Service: Multi-Tier Evidence Auditing & Truth Enforcement.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from goals.models import (
    KeyResultDefinition,
    OutcomeEvidenceRecord,
    VerificationTier,
)
from goals.outcomes import OutcomeDefinitionEngine
from goals.persistence import GoalRepository

logger = logging.getLogger("Omnia.Goals.Verification")


TIER_HIERARCHY = {
    VerificationTier.SELF_REPORTED: 1,
    VerificationTier.SYSTEM_OBSERVED: 2,
    VerificationTier.EXTERNALLY_VERIFIED: 3,
    VerificationTier.HUMAN_CONFIRMED: 4,
    VerificationTier.INDEPENDENTLY_AUDITED: 5,
}


class OutcomeVerificationService:
    """
    Guarantees that outcome claims are validated against independent, verifiable evidence.
    Distinguishes self-reported worker claims from verified ground truth.
    """

    def __init__(
        self,
        repository: Optional[GoalRepository] = None,
        outcomes_engine: Optional[OutcomeDefinitionEngine] = None,
    ):
        self.repo = repository or GoalRepository()
        self.engine = outcomes_engine or OutcomeDefinitionEngine(self.repo)

    def record_reported_metric(self, key_result_id: str, reported_value: float, reporter: str) -> KeyResultDefinition:
        """
        Records a worker's self-reported progress without promoting it to verified value.
        Updates reported progress only.
        """
        kr = self.repo.get_key_result(key_result_id)
        if not kr:
            raise ValueError(f"Key result '{key_result_id}' not found.")

        kr.current_reported_value = reported_value
        kr.last_updated = datetime.now(timezone.utc).isoformat()
        self.repo.save_key_result(kr)
        logger.info(f"Reported value for KR '{key_result_id}': {reported_value} (by {reporter})")
        return kr

    def submit_and_verify_evidence(
        self,
        key_result_id: str,
        observed_value: float,
        verification_tier: VerificationTier,
        data_source: str,
        evidence_summary: str,
        evidence_payload: Dict[str, Any],
        verified_by: str,
        approval_token: Optional[str] = None,
        evidence_id: Optional[str] = None,
    ) -> OutcomeEvidenceRecord:
        """
        Submits evidence for a key result. If the evidence tier meets or exceeds the required
        tier, the verified value is updated and satisfaction is evaluated.
        """
        kr = self.repo.get_key_result(key_result_id)
        if not kr:
            raise ValueError(f"Key result '{key_result_id}' not found.")

        # Compute SHA-256 digest of payload for cryptographic immutability
        payload_bytes = json.dumps(evidence_payload, sort_keys=True).encode("utf-8")
        evidence_hash = hashlib.sha256(payload_bytes).hexdigest()

        # Check approval token if human confirmation tier is claimed
        if verification_tier == VerificationTier.HUMAN_CONFIRMED and not approval_token:
            logger.warning(f"HUMAN_CONFIRMED verification submitted without approval token for KR '{key_result_id}'. Marked invalid.")
            is_valid = False
        else:
            is_valid = True

        eid = evidence_id or f"ev-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()
        record = OutcomeEvidenceRecord(
            evidence_id=eid,
            key_result_id=key_result_id,
            goal_id=kr.goal_id,
            verification_tier=verification_tier,
            data_source=data_source,
            observed_value=observed_value,
            evidence_summary=evidence_summary,
            evidence_payload=evidence_payload,
            evidence_hash=evidence_hash,
            verified_by=verified_by,
            approval_token=approval_token,
            verified_at=now,
            is_valid=is_valid,
        )
        self.repo.save_evidence_record(record)

        # Evaluate if evidence tier satisfies KR requirement
        submitted_level = TIER_HIERARCHY.get(verification_tier, 0)
        required_level = TIER_HIERARCHY.get(kr.required_verification_tier, 0)

        if is_valid and submitted_level >= required_level:
            kr.current_verified_value = observed_value
            # Also update reported if reported is lagging
            kr.current_reported_value = observed_value
            kr.is_satisfied = self.engine.evaluate_key_result_satisfaction(kr)
            kr.last_updated = now
            self.repo.save_key_result(kr)
            logger.info(
                f"Verified KR '{key_result_id}': Value={observed_value} ({verification_tier.value}), Satisfied={kr.is_satisfied}"
            )
        else:
            logger.warning(
                f"Evidence '{eid}' tier ({verification_tier.value}) does not satisfy required ({kr.required_verification_tier.value}) or is invalid."
            )

        return record
