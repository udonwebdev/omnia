"""
privacy/processing_registry.py
Record of Processing Activities (RoPA) Registry conforming to GDPR Article 30.
Tracks lawful bases, purpose bindings, data categories, and periodic review schedules
to prevent unauthorized or purpose-deviating processing.
"""

import uuid
import time
import logging
from typing import List, Dict, Any, Optional, Tuple

from privacy.models import ProcessingActivity, LawfulBasis, DataCategory
from privacy.persistence import PrivacyRepository

logger = logging.getLogger("omnia.privacy.processing_registry")


class ProcessingActivityRegistry:
    def __init__(self, repo: PrivacyRepository):
        self.repo = repo

    def register_activity(
        self,
        name: str,
        purpose: str,
        lawful_basis: str,
        owner: str,
        data_categories: List[str],
        retention_schedule: str = "P3Y",
        is_approved: bool = False,
        activity_id: Optional[str] = None
    ) -> ProcessingActivity:
        """Registers a processing activity in the RoPA registry."""
        aid = activity_id or f"act_{uuid.uuid4().hex[:12]}"
        now = time.time()

        lbasis = LawfulBasis(lawful_basis.upper()) if lawful_basis.upper() in LawfulBasis._value2member_map_ else LawfulBasis.LEGITIMATE_INTERESTS
        cats = []
        for c in data_categories:
            if c.upper() in DataCategory._value2member_map_:
                cats.append(DataCategory(c.upper()))
            else:
                cats.append(DataCategory.PII)

        activity = ProcessingActivity(
            activity_id=aid,
            name=name,
            purpose=purpose,
            lawful_basis=lbasis,
            owner=owner,
            data_categories=cats,
            retention_schedule=retention_schedule,
            is_approved=is_approved,
            review_date=now + 31536000.0  # 1 year review cycle
        )
        saved = self.repo.save_processing_activity(activity)
        self.repo.log_audit("PROCESSING_ACTIVITY_REGISTERED", owner, {
            "activity_id": aid,
            "purpose": purpose,
            "lawful_basis": lbasis.value,
            "approved": is_approved
        })
        logger.info(f"Processing activity registered: {aid} ({name}, purpose={purpose})")
        return saved

    def approve_activity(self, activity_id: str, approver: str = "omnia_dpo") -> Optional[ProcessingActivity]:
        """Formally approves a processing activity after privacy review."""
        activity = self.repo.get_processing_activity(activity_id)
        if not activity:
            return None
        activity.is_approved = True
        saved = self.repo.save_processing_activity(activity)
        self.repo.log_audit("PROCESSING_ACTIVITY_APPROVED", approver, {"activity_id": activity_id})
        logger.info(f"Processing activity {activity_id} approved by {approver}.")
        return saved

    def validate_processing(
        self,
        purpose: str,
        data_categories: Optional[List[str]] = None
    ) -> Tuple[bool, str]:
        """Validates whether processing data for the given purpose is legally authorized.

        Returns (is_valid, reason).
        """
        activity = self.repo.get_processing_activity_by_purpose(purpose)
        if not activity:
            return False, f"PURPOSE_UNREGISTERED: Purpose '{purpose}' has not been registered in RoPA."

        if not activity.is_approved:
            return False, f"PURPOSE_UNAPPROVED: Activity '{activity.name}' is pending DPO approval."

        if time.time() > activity.review_date:
            return False, f"REVIEW_EXPIRED: Activity '{activity.name}' requires periodic review before continued processing."

        if data_categories:
            registered_cats = set(c.value for c in activity.data_categories)
            for req_cat in data_categories:
                if req_cat.upper() not in registered_cats:
                    return False, f"CATEGORY_MISMATCH: Category '{req_cat}' is not authorized under purpose '{purpose}'."

        return True, "Processing is lawful and validated."
