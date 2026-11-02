"""
privacy/minimization.py
Data Minimization & Privacy-by-Design Engine:
Analyzes schemas, collection forms, and processing requests against purpose necessity,
flagging over-collection, excessive sensitive fields, and disproportionate retention.
"""

import logging
from typing import List, Dict, Any, Set

from privacy.models import DataCategory, SensitivityTier

logger = logging.getLogger("omnia.privacy.minimization")


class DataMinimizationEngine:
    # Purpose to strictly necessary categories mapping
    PURPOSE_NECESSITY_RULES = {
        "NEWSLETTER": {DataCategory.PII},
        "BILLING": {DataCategory.FINANCIAL, DataCategory.PII, DataCategory.LOCATION},
        "AUTHENTICATION": {DataCategory.CREDENTIALS, DataCategory.PII},
        "ANALYTICS": {DataCategory.LOCATION, DataCategory.BEHAVIORAL},
        "ORDER_FULFILLMENT": {DataCategory.PII, DataCategory.LOCATION, DataCategory.FINANCIAL},
        "PATIENT_CARE": {DataCategory.HEALTH, DataCategory.PII, DataCategory.GOV_ID},
    }

    # Highly restricted categories that should almost never be collected for common business purposes
    HIGH_RISK_CATEGORIES = {
        DataCategory.GOV_ID,
        DataCategory.BIOMETRIC,
        DataCategory.HEALTH,
        DataCategory.CREDENTIALS,
    }

    def evaluate_schema_minimization(
        self,
        purpose: str,
        classified_fields: List[Dict[str, Any]],
        proposed_retention_days: int = 365
    ) -> Dict[str, Any]:
        """Evaluates whether proposed fields and retention are strictly necessary for the purpose.

        Returns minimization findings, excessive fields list, and privacy-by-design recommendations.
        """
        norm_purpose = purpose.upper().strip()
        necessary_cats = self.PURPOSE_NECESSITY_RULES.get(norm_purpose)

        excessive_fields = []
        high_risk_detected = []
        recommendations = []

        for f in classified_fields:
            fname = f.get("field_name", "unknown")
            raw_cat = f.get("category", "")
            cat = DataCategory(raw_cat) if raw_cat in DataCategory._value2member_map_ else DataCategory.PII
            tier = f.get("sensitivity_tier", SensitivityTier.INTERNAL.value)

            # Check if category exceeds necessity
            if necessary_cats is not None and cat not in necessary_cats:
                excessive_fields.append({
                    "field_name": fname,
                    "category": cat.value,
                    "sensitivity_tier": tier,
                    "reason": f"Category '{cat.value}' is not strictly necessary for purpose '{norm_purpose}'."
                })
                recommendations.append(f"Remove or mask '{fname}' as it is disproportionate for {norm_purpose}.")

            # Check high-risk categories in low-sensitivity contexts
            if norm_purpose in ("NEWSLETTER", "ANALYTICS") and cat in self.HIGH_RISK_CATEGORIES:
                high_risk_detected.append(fname)
                recommendations.append(f"CRITICAL: Drop high-risk field '{fname}' ({cat.value}) from {norm_purpose}.")

        # Check over-retention
        retention_warning = None
        if norm_purpose in ("ANALYTICS", "SESSION", "TELEMETRY", "NEWSLETTER") and proposed_retention_days > 90:
            retention_warning = f"Retention of {proposed_retention_days} days for {norm_purpose} exceeds the recommended 90 days."
            recommendations.append("Reduce data retention period to 90 days and apply automated pseudonymization.")
        elif proposed_retention_days > 730:
            retention_warning = f"Retention of {proposed_retention_days} days exceeds standard maximum limits."
            recommendations.append("Apply automated pseudonymization and retention limits.")

        score = max(0.0, 100.0 - (len(excessive_fields) * 20.0) - (len(high_risk_detected) * 35.0))

        return {
            "purpose": norm_purpose,
            "minimization_score": score,
            "is_minimized": len(excessive_fields) == 0 and len(high_risk_detected) == 0,
            "excessive_fields": excessive_fields,
            "high_risk_fields": high_risk_detected,
            "retention_warning": retention_warning,
            "recommendations": recommendations
        }
