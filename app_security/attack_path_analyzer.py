"""
OMNIA Module 46: Autonomous Application Security Testing, Vulnerability Intelligence & Defensive Validation
Attack Path & Exposure Analysis Engine - attack_path_analyzer.py

Models threat propagation across authorized asset relationships (APIs, identities, boundaries).
Distinguishes theoretical attack paths from validated paths. Never executes lateral movement.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app_security.models import AttackPath, SecurityFinding
from app_security.persistence import AppSecurityRepository

logger = logging.getLogger("Omnia.AppSecurity.AttackPathAnalyzer")


class AttackPathAnalyzer:
    """
    Evaluates multi-step vulnerability chains traversing trust boundaries.
    """

    def __init__(self, repository: Optional[AppSecurityRepository] = None):
        self.repo = repository or AppSecurityRepository()

    def synthesize_attack_path(
        self,
        assessment_id: str,
        entry_asset_id: str,
        target_asset_id: str,
        contributing_findings: List[SecurityFinding],
        hops_description: List[str]
    ) -> AttackPath:
        pid = f"path-{uuid.uuid4().hex[:8]}"

        hops = []
        for idx, desc in enumerate(hops_description, start=1):
            hops.append({
                "hop_index": idx,
                "description": desc,
                "trust_boundary_crossed": True if idx > 1 else False
            })

        # Calculate path risk based on finding severities
        severity_weights = {"LOW": 1.0, "MEDIUM": 2.5, "HIGH": 5.0, "CRITICAL": 10.0}
        total_risk = sum(severity_weights.get(f.severity.value, 1.0) for f in contributing_findings)
        aggregate_score = min(100.0, total_risk * 10.0)

        path = AttackPath(
            path_id=pid,
            assessment_id=assessment_id,
            entry_asset_id=entry_asset_id,
            target_asset_id=target_asset_id,
            path_hops=hops,
            aggregate_risk_score=aggregate_score,
            is_validated=False
        )

        with self.repo._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sec_attack_paths (
                    path_id, assessment_id, entry_asset_id, target_asset_id,
                    path_hops_json, aggregate_risk_score, is_validated, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    path.path_id, path.assessment_id, path.entry_asset_id, path.target_asset_id,
                    json.dumps(path.path_hops), path.aggregate_risk_score,
                    1 if path.is_validated else 0, path.created_at
                )
            )

        logger.info(f"Synthesized attack path {pid} from '{entry_asset_id}' to '{target_asset_id}' (Score: {aggregate_score})")
        return path
