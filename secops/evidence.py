"""
OMNIA Module 47: Autonomous Threat Detection, Behavioral Analytics & Real-Time Security Operations Intelligence
Evidence Preservation & Detection Evaluator - evidence.py & evaluator.py
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from secops.models import DetectionEvaluation, EvidencePackage
from secops.persistence import SecOpsRepository

logger = logging.getLogger("Omnia.SecOps.Evidence")


class EvidencePreservationEngine:
    """
    Assembles tamper-evident forensic evidence packages cryptographically sealed with SHA-256.
    Integrates with Module 29 Evidence & Decision system contracts.
    """

    def __init__(self, repository: Optional[SecOpsRepository] = None):
        self.repo = repository or SecOpsRepository()

    def seal_incident_evidence_package(
        self,
        incident_id: str,
        sealed_by: str,
        investigation_id: Optional[str] = None,
        additional_evidence: Optional[Dict[str, Any]] = None,
    ) -> EvidencePackage:
        inc = self.repo.get_incident(incident_id)
        if not inc:
            raise ValueError(f"Incident {incident_id} not found.")

        timelines = self.repo.get_timeline_entries(incident_id)

        manifest = {
            "incident": {
                "id": inc.incident_id,
                "title": inc.title,
                "severity": inc.severity.value,
                "status": inc.status.value,
                "created_at": inc.created_at,
            },
            "timeline": [
                {
                    "timestamp": t.entry_timestamp,
                    "type": t.entry_type,
                    "desc": t.description,
                    "actor": t.actor,
                }
                for t in timelines
            ],
            "artifacts": additional_evidence or {},
        }

        manifest_bytes = json.dumps(manifest, sort_keys=True).encode("utf-8")
        pkg_digest = hashlib.sha256(manifest_bytes).hexdigest()

        pkg_id = f"pkg-{uuid.uuid4().hex[:8]}"
        pkg = EvidencePackage(
            package_id=pkg_id,
            incident_id=incident_id,
            investigation_id=investigation_id,
            package_digest_sha256=pkg_digest,
            evidence_manifest=manifest,
            sealed_by=sealed_by,
            sealed_at=datetime.now(timezone.utc).isoformat(),
        )

        self.repo.save_evidence_package(pkg)
        logger.info(f"Sealed immutable evidence package {pkg_id} for Incident {incident_id} (SHA-256: {pkg_digest[:16]}...)")
        return pkg


class DetectionEvaluationEngine:
    """
    Measures detection efficacy, precision, recall, and false positive rates against labeled benchmark scenarios.
    """

    def __init__(self, repository: Optional[SecOpsRepository] = None):
        self.repo = repository or SecOpsRepository()

    def evaluate_benchmark(
        self,
        dataset_name: str,
        true_positives: int,
        false_positives: int,
        false_negatives: int,
        true_negatives: int,
    ) -> DetectionEvaluation:
        total = true_positives + false_positives + false_negatives + true_negatives
        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        eid = f"eval-{uuid.uuid4().hex[:8]}"
        eval_record = DetectionEvaluation(
            eval_id=eid,
            dataset_name=dataset_name,
            total_samples=total,
            true_positives=true_positives,
            false_positives=false_positives,
            false_negatives=false_negatives,
            true_negatives=true_negatives,
            precision_score=round(precision, 4),
            recall_score=round(recall, 4),
            f1_score=round(f1, 4),
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )

        with self.repo._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO soc_detection_evaluations (
                    eval_id, dataset_name, total_samples, true_positives,
                    false_positives, false_negatives, true_negatives,
                    precision_score, recall_score, f1_score, evaluated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    eval_record.eval_id,
                    eval_record.dataset_name,
                    eval_record.total_samples,
                    eval_record.true_positives,
                    eval_record.false_positives,
                    eval_record.false_negatives,
                    eval_record.true_negatives,
                    eval_record.precision_score,
                    eval_record.recall_score,
                    eval_record.f1_score,
                    eval_record.evaluated_at,
                ),
            )
        logger.info(f"Evaluated benchmark '{dataset_name}': Precision={precision:.2%}, Recall={recall:.2%}, F1={f1:.2%}")
        return eval_record
