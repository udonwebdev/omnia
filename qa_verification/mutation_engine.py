"""
OMNIA Module 45: Autonomous Quality Assurance, Software Verification & Continuous Testing Intelligence
Mutation Testing Engine - mutation_engine.py

Assesses test suite effectiveness by injecting controlled semantic faults
(operator swap, boundary shift, inverted condition) and measuring kill rates.
"""

from __future__ import annotations

import logging
import uuid
from typing import Callable, List, Optional

from qa_verification.models import MutationTestResult
from qa_verification.persistence import QAVerificationRepository

logger = logging.getLogger("Omnia.QAVerification.MutationEngine")


class MutationEngine:
    """
    Evaluates test harness vigilance against synthesized code mutants.
    """

    def __init__(self, repository: Optional[QAVerificationRepository] = None):
        self.repo = repository or QAVerificationRepository()

    def run_mutation_trial(
        self,
        mission_id: str,
        mutant_type: str,
        test_harness: Callable[[], bool],
        mutation_id: Optional[str] = None,
    ) -> MutationTestResult:
        """
        Executes test harness against a simulated mutant.
        If the test harness fails (detects the mutant), the mutant is 'killed'.
        """
        mid = mutation_id or f"mut-{uuid.uuid4().hex[:8]}"

        try:
            # If test harness returns True, mutant survived (test didn't catch fault)
            test_passed = test_harness()
            killed = not test_passed
        except Exception:
            # Test crashed or raised assertion error -> Mutant killed!
            killed = True

        res = MutationTestResult(
            mutation_id=mid,
            mission_id=mission_id,
            mutant_type=mutant_type,
            killed=killed,
            surviving_details=None if killed else "Mutant survived: test suite lacked assertion on boundary condition",
        )
        self.repo.save_mutation(res)
        logger.info(f"Mutation test '{mid}' ({mutant_type}): Killed={killed}")
        return res
