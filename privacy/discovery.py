"""
privacy/discovery.py
Sensitive Data Discovery Engine providing scoped, authorized, read-only scanning
of data sources without copying sensitive raw data.
"""

import uuid
import time
import logging
from typing import List, Dict, Any, Optional

from privacy.models import DiscoveryScan, DataCategory, SensitivityTier
from privacy.persistence import PrivacyRepository
from privacy.classifier import DataClassificationEngine

logger = logging.getLogger("omnia.privacy.discovery")


class SensitiveDataDiscoveryEngine:
    def __init__(self, repo: PrivacyRepository, classifier: DataClassificationEngine):
        self.repo = repo
        self.classifier = classifier

    def run_discovery_scan(
        self,
        target_scope: str,
        scanner_identity: str = "omnia_privacy_scanner",
        field_names: Optional[List[str]] = None,
        sample_payload: Optional[Dict[str, Any]] = None,
        asset_id: Optional[str] = None
    ) -> DiscoveryScan:
        """Executes an authorized, read-only discovery scan on target scope.

        Crucial Privacy Invariant:
        No raw sensitive payload values are stored in findings or persistent scan logs.
        Only metadata, categories, matched rules, and confidence are recorded.
        """
        scan_id = f"scn_{uuid.uuid4().hex[:12]}"
        now = time.time()
        findings: List[Dict[str, Any]] = []

        # 1. Field name scanning
        fields_to_check = list(field_names or [])
        if sample_payload and isinstance(sample_payload, dict):
            for k in sample_payload.keys():
                if k not in fields_to_check:
                    fields_to_check.append(k)

        dummy_asset_id = asset_id or f"discovered_{target_scope}"

        for fname in fields_to_check:
            samples = []
            if sample_payload and isinstance(sample_payload, dict):
                val = sample_payload.get(fname)
                if isinstance(val, list):
                    samples = [str(x) for x in val]
                elif val is not None:
                    samples = [str(val)]

            cls_result = self.classifier.classify_field(
                asset_id=dummy_asset_id,
                field_name=fname,
                sample_values=samples
            )

            # Record finding if non-public or sensitive category
            if cls_result.sensitivity_tier != SensitivityTier.PUBLIC and cls_result.confidence >= 0.70:
                findings.append({
                    "field_name": fname,
                    "category": cls_result.category.value,
                    "sensitivity_tier": cls_result.sensitivity_tier.value,
                    "confidence": cls_result.confidence,
                    "rule_matched": cls_result.rule_matched
                })

        scan = DiscoveryScan(
            scan_id=scan_id,
            target_scope=target_scope,
            scanner_identity=scanner_identity,
            findings_count=len(findings),
            sensitive_fields=findings,
            started_at=now,
            completed_at=time.time(),
            status="COMPLETED"
        )
        saved = self.repo.save_scan(scan)
        self.repo.log_audit("DISCOVERY_SCAN_COMPLETED", scanner_identity, {
            "scan_id": scan_id,
            "target_scope": target_scope,
            "findings_count": len(findings)
        })
        logger.info(f"Discovery scan {scan_id} completed for scope '{target_scope}' with {len(findings)} findings.")
        return saved
