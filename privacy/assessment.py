"""
privacy/assessment.py
Privacy Impact Assessment (PIA) & Data Protection Impact Assessment (DPIA) Engine:
Computes multi-dimensional risk scores across data sensitivity, processing volume,
automated/AI decision-making, and cross-border vendor disclosure, generating
actionable technical and organizational safeguards.
"""

import uuid
import time
import logging
from typing import List, Dict, Any, Optional

from privacy.models import PrivacyAssessment, PIAType, PIAStatus, SensitivityTier, DataCategory
from privacy.persistence import PrivacyRepository

logger = logging.getLogger("omnia.privacy.assessment")


class PrivacyAssessmentEngine:
    def __init__(self, repo: PrivacyRepository):
        self.repo = repo

    def conduct_assessment(
        self,
        activity_id: str,
        assessment_type: str = "DPIA",
        involves_ai: bool = False,
        involves_third_parties: bool = False,
        subject_count: int = 1000,
        has_encryption: bool = True,
        assessor: str = "omnia_privacy_architect"
    ) -> PrivacyAssessment:
        """Conducts a formal PIA/DPIA on a processing activity."""
        aid = f"ass_{uuid.uuid4().hex[:12]}"
        now = time.time()
        atype = PIAType(assessment_type.upper()) if assessment_type.upper() in PIAType._value2member_map_ else PIAType.DPIA

        # Fetch activity details
        activity = self.repo.get_processing_activity(activity_id)

        # Base risk calculation
        risk_score = 15.0
        findings = []
        safeguards = []

        if activity:
            # Check high-risk categories
            for cat in activity.data_categories:
                if cat in (DataCategory.HEALTH, DataCategory.BIOMETRIC, DataCategory.GOV_ID):
                    risk_score += 25.0
                    findings.append({
                        "risk_factor": "SPECIAL_CATEGORY_DATA",
                        "severity": "HIGH",
                        "description": f"Processing special category data: {cat.value}"
                    })
                    safeguards.append({
                        "safeguard": f"Implement field-level cryptographic tokenization for {cat.value}",
                        "mandatory": True
                    })
                elif cat in (DataCategory.FINANCIAL, DataCategory.CREDENTIALS):
                    risk_score += 20.0
                    findings.append({
                        "risk_factor": "FINANCIAL_OR_CREDENTIAL_DATA",
                        "severity": "HIGH",
                        "description": f"Processing financial or credential data: {cat.value}"
                    })
                    safeguards.append({
                        "safeguard": f"Ensure strict PCI-DSS / zero-plaintext storage for {cat.value}",
                        "mandatory": True
                    })

        # Scale factor
        if subject_count > 100000:
            risk_score += 20.0
            findings.append({
                "risk_factor": "LARGE_SCALE_PROCESSING",
                "severity": "MEDIUM",
                "description": f"Processing involves {subject_count} data subjects."
            })
            safeguards.append({
                "safeguard": "Conduct bi-annual external privacy audit.",
                "mandatory": False
            })

        # AI factor
        if involves_ai:
            risk_score += 20.0
            findings.append({
                "risk_factor": "AI_INFERENCE_OR_AUTOMATED_DECISION",
                "severity": "HIGH",
                "description": "Activity utilizes AI models or automated profiling."
            })
            safeguards.append({
                "safeguard": "Enable prompt redaction and verify training ban agreements with model providers.",
                "mandatory": True
            })

        # Third-party transfer
        if involves_third_parties:
            risk_score += 15.0
            findings.append({
                "risk_factor": "THIRD_PARTY_DISCLOSURE",
                "severity": "MEDIUM",
                "description": "Data is shared with external vendors or subprocessors."
            })
            safeguards.append({
                "safeguard": "Verify active DPA and standard contractual clauses (SCCs) are in place.",
                "mandatory": True
            })

        # Mitigation for encryption
        if has_encryption:
            risk_score = max(5.0, risk_score - 15.0)
        else:
            risk_score += 25.0
            findings.append({
                "risk_factor": "UNENCRYPTED_AT_REST",
                "severity": "CRITICAL",
                "description": "Target storage lacks AES-256 or hardware encryption at rest."
            })
            safeguards.append({
                "safeguard": "Mandate AES-256-GCM encryption at rest immediately.",
                "mandatory": True
            })

        risk_score = min(100.0, max(0.0, round(risk_score, 1)))

        # Determine status
        if risk_score <= 30.0:
            status = PIAStatus.APPROVED
        elif risk_score <= 70.0:
            status = PIAStatus.REVIEW_REQUIRED
        else:
            status = PIAStatus.REJECTED

        assessment = PrivacyAssessment(
            assessment_id=aid,
            activity_id=activity_id,
            assessment_type=atype,
            risk_score=risk_score,
            findings=findings,
            safeguards=safeguards,
            approval_status=status,
            assessed_at=now
        )
        saved = self.repo.save_assessment(assessment)
        self.repo.log_audit("ASSESSMENT_COMPLETED", assessor, {
            "assessment_id": aid,
            "activity_id": activity_id,
            "risk_score": risk_score,
            "status": status.value
        })
        logger.info(f"PIA/DPIA {aid} completed for {activity_id}: risk={risk_score}, status={status.value}")
        return saved
