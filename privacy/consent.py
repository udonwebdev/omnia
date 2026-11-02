"""
privacy/consent.py
Consent & Privacy Preference Manager:
Maintains granular, purpose-specific consent grants, withdrawals, and policy versions.
Provides immediate check against unlawful processing when consent is withdrawn.
"""

import uuid
import time
import logging
from typing import List, Optional

from privacy.models import ConsentRecord, ConsentStatus
from privacy.persistence import PrivacyRepository

logger = logging.getLogger("omnia.privacy.consent")


class ConsentManager:
    def __init__(self, repo: PrivacyRepository):
        self.repo = repo

    def grant_consent(
        self,
        subject_id: str,
        purpose: str,
        policy_version: str = "1.0"
    ) -> ConsentRecord:
        """Records an explicit consent grant from a data subject for a designated purpose."""
        cid = f"cns_{uuid.uuid4().hex[:12]}"
        now = time.time()

        rec = ConsentRecord(
            consent_id=cid,
            subject_id=subject_id,
            purpose=purpose,
            status=ConsentStatus.GRANTED,
            granted_at=now,
            withdrawn_at=None,
            policy_version=policy_version
        )
        saved = self.repo.save_consent(rec)
        self.repo.log_audit("CONSENT_GRANTED", subject_id, {
            "consent_id": cid,
            "purpose": purpose,
            "policy_version": policy_version
        })
        logger.info(f"Consent granted: subject={subject_id}, purpose={purpose}, ver={policy_version}")
        return saved

    def withdraw_consent(
        self,
        subject_id: str,
        purpose: str
    ) -> ConsentRecord:
        """Withdraws consent for a specific purpose. Triggers immediate downstream processing cessation."""
        now = time.time()
        existing = self.repo.get_latest_consent(subject_id, purpose)

        if existing and existing.status == ConsentStatus.GRANTED:
            existing.status = ConsentStatus.WITHDRAWN
            existing.withdrawn_at = now
            saved = self.repo.save_consent(existing)
        else:
            cid = f"cns_{uuid.uuid4().hex[:12]}"
            saved = self.repo.save_consent(ConsentRecord(
                consent_id=cid,
                subject_id=subject_id,
                purpose=purpose,
                status=ConsentStatus.WITHDRAWN,
                granted_at=now,
                withdrawn_at=now,
                policy_version="1.0"
            ))

        self.repo.log_audit("CONSENT_WITHDRAWN", subject_id, {
            "consent_id": saved.consent_id,
            "purpose": purpose
        })
        logger.info(f"Consent withdrawn: subject={subject_id}, purpose={purpose}")
        return saved

    def has_valid_consent(self, subject_id: str, purpose: str) -> bool:
        """Checks if a data subject has active, non-withdrawn consent for a purpose."""
        latest = self.repo.get_latest_consent(subject_id, purpose)
        if not latest:
            return False
        return latest.status == ConsentStatus.GRANTED

    def get_consent_history(self, subject_id: str) -> List[ConsentRecord]:
        """Returns the full audit trail of consent events for a subject."""
        return self.repo.list_consents_for_subject(subject_id)
