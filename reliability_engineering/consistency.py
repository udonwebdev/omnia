"""
Omnia Module 41: Autonomous Reliability Engineering, Resilience Testing & Disaster Recovery.
State Consistency Validator: Distributed State Auditing across Modules 15, 22, and 23.
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from reliability_engineering.models import (
    StateIntegrityFinding,
)
from reliability_engineering.persistence import ReliabilityRepository

logger = logging.getLogger("Omnia.Reliability.Consistency")


class StateConsistencyValidator:
    """
    Audits persistent task checkpoints, event streams, replicated state, and distributed consensus.
    Detects split-brain conditions, missing transaction logs, and stale replicas.
    """

    def __init__(self, repository: Optional[ReliabilityRepository] = None):
        self.repo = repository or ReliabilityRepository()

    def audit_subsystem_state(
        self,
        subsystem: str,
        expected_epoch: int,
        reported_epoch: int,
        checkpoint_count: int,
        replica_lag_sec: float = 0.0,
    ) -> List[StateIntegrityFinding]:
        """
        Validates state consistency for a given subsystem.
        Detects divergence such as stale epoch (split-brain) or replica lag.
        """
        findings: List[StateIntegrityFinding] = []

        # 1. Check epoch consensus (split-brain detection)
        if reported_epoch < expected_epoch:
            fid = f"sif-{uuid.uuid4().hex[:8]}"
            finding = StateIntegrityFinding(
                finding_id=fid,
                subsystem=subsystem,
                divergence_type="SPLIT_BRAIN_STALE_EPOCH",
                severity="CRITICAL",
                details=f"Reported epoch {reported_epoch} is stale compared to quorum epoch {expected_epoch}.",
            )
            self.repo.save_integrity_finding(finding)
            findings.append(finding)

        # 2. Check replica lag
        if replica_lag_sec > 30.0:
            fid = f"sif-{uuid.uuid4().hex[:8]}"
            finding = StateIntegrityFinding(
                finding_id=fid,
                subsystem=subsystem,
                divergence_type="EXCESSIVE_REPLICATION_LAG",
                severity="HIGH",
                details=f"Replica lag {replica_lag_sec}s breaches maximum allowed delta (30.0s).",
            )
            self.repo.save_integrity_finding(finding)
            findings.append(finding)

        # 3. Check checkpoint completeness
        if checkpoint_count == 0:
            fid = f"sif-{uuid.uuid4().hex[:8]}"
            finding = StateIntegrityFinding(
                finding_id=fid,
                subsystem=subsystem,
                divergence_type="MISSING_CHECKPOINT_STATE",
                severity="HIGH",
                details="Zero recovery checkpoints available for persistent tasks.",
            )
            self.repo.save_integrity_finding(finding)
            findings.append(finding)

        logger.info(f"State audit for '{subsystem}' completed with {len(findings)} integrity finding(s).")
        return findings

    def list_open_integrity_findings(self) -> List[StateIntegrityFinding]:
        return self.repo.list_integrity_findings()
