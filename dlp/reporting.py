"""
dlp/reporting.py
Operations Center & Cryptographically Sealed Reporting for OMNIA Module 52:
Autonomous Data Loss Prevention, Sensitive Information Monitoring & Exfiltration Defense Intelligence.
"""

import uuid
import time
import hashlib
import json
from typing import Dict, Any, Optional

from dlp.models import DLPReport
from dlp.persistence import DLPRepository


class DLPReportingEngine:
    """
    Synthesizes comprehensive operational metrics across findings, movement events,
    blocked transfers, and active alerts, sealing reports with a SHA-256 cryptographic seal.
    """

    def __init__(self, repo: DLPRepository):
        self.repo = repo

    def generate_operations_report(
        self,
        title: str = "OMNIA DLP Operations Intelligence Report",
        reporting_actor: str = "dlp_operations_officer",
        metadata: Optional[Dict[str, Any]] = None
    ) -> DLPReport:
        """
        Gathers operational metrics, builds structured report JSON, computes
        SHA-256 cryptographic seal, and persists into dlp_reports.
        """
        now = time.time()
        rep_id = f"rep_dlp_{uuid.uuid4().hex[:10]}"
        metrics = self.repo.get_operations_metrics()

        # Query recent alerts and incidents
        recent_alerts = self.repo.list_exfiltration_alerts(limit=10)
        recent_incidents = self.repo.list_incidents(limit=10)
        active_policies = self.repo.list_policies(active_only=True)
        fingerprints = self.repo.list_fingerprints(active_only=True)

        report_data = {
            "report_id": rep_id,
            "title": title,
            "generated_at": now,
            "reporting_actor": reporting_actor,
            "operational_metrics": metrics,
            "active_policy_count": len(active_policies),
            "protected_fingerprints_count": len(fingerprints),
            "recent_alerts": [a.to_dict() for a in recent_alerts],
            "recent_incidents": [i.to_dict() for i in recent_incidents],
            "metadata": metadata or {},
        }

        # Deterministic cryptographic seal
        seal_string = json.dumps(report_data, sort_keys=True)
        sha256_seal = hashlib.sha256(seal_string.encode("utf-8")).hexdigest()
        report_data["sha256_seal"] = sha256_seal

        report = DLPReport(
            report_id=rep_id,
            title=title,
            findings_count=metrics["findings_count"],
            blocked_transfers_count=metrics["blocked_transfers_count"],
            active_alerts_count=metrics["active_alerts_count"],
            sha256_seal=sha256_seal,
            generated_at=now,
            report_data=report_data,
        )

        return self.repo.save_report(report)
