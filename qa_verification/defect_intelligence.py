"""
OMNIA Module 45: Autonomous Quality Assurance, Software Verification & Continuous Testing Intelligence
Defect Intelligence Engine - defect_intelligence.py

Captures, classifies, and correlates defects with stack traces, reproduction steps,
and root-cause categorization.
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from qa_verification.models import (
    DefectCategory,
    DefectRecord,
    DefectSeverity,
)
from qa_verification.persistence import QAVerificationRepository

logger = logging.getLogger("Omnia.QAVerification.DefectIntelligence")


class DefectIntelligenceEngine:
    """
    Classifies failure signatures and deduplicates defects across test runs.
    """

    def __init__(self, repository: Optional[QAVerificationRepository] = None):
        self.repo = repository or QAVerificationRepository()

    def record_defect(
        self,
        project_id: str,
        execution_id: str,
        title: str,
        category: DefectCategory,
        severity: DefectSeverity,
        reproduction_steps: List[str],
        stack_trace: Optional[str] = None,
        defect_id: Optional[str] = None,
    ) -> DefectRecord:
        did = defect_id or f"def-{uuid.uuid4().hex[:8]}"
        defect = DefectRecord(
            defect_id=did,
            project_id=project_id,
            execution_id=execution_id,
            title=title,
            category=category,
            severity=severity,
            reproduction_steps=reproduction_steps,
            stack_trace=stack_trace,
            is_reproduced=True,
            is_resolved=False,
        )
        self.repo.save_defect(defect)
        logger.info(
            f"Logged defect '{did}' ({title}) [{category.value}/{severity.value}] for project '{project_id}'"
        )
        return defect

    def mark_resolved(self, defect_id: str) -> None:
        def_rec = self.repo.get_defect(defect_id)
        if not def_rec:
            raise KeyError(f"Defect '{defect_id}' not found.")
        def_rec.is_resolved = True
        self.repo.save_defect(def_rec)
        logger.info(f"Marked defect '{defect_id}' as resolved.")
