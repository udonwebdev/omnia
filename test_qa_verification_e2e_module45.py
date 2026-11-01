"""
End-to-End Workflow Verification Drill for OMNIA Module 45:
Autonomous Quality Assurance, Software Verification & Continuous Testing Intelligence
"""
import unittest
import os
import uuid
import sqlite3

from persistence.migrations import MIGRATION_V30
from qa_verification.persistence import QAVerificationRepository
from qa_verification.models import (
    VerificationProject, RequirementType, VerificationStatus, TestCategory,
    DefectSeverity, DefectCategory, FlakyClassification, QualityTier
)
from qa_verification.service import QAVerificationOrchestrator


class TestModule45QAVerificationE2E(unittest.TestCase):

    def setUp(self):
        self.db_name = f"test_qa_e2e_{uuid.uuid4().hex[:8]}.db"
        conn = sqlite3.connect(self.db_name)
        conn.executescript(MIGRATION_V30)
        conn.close()

        self.repo = QAVerificationRepository(db_path=self.db_name)
        self.orchestrator = QAVerificationOrchestrator(db_path=self.db_name)

    def tearDown(self):
        if os.path.exists(self.db_name):
            try:
                os.remove(self.db_name)
            except Exception:
                pass

    def test_full_autonomous_qa_verification_lifecycle(self):
        """
        Comprehensive 12-step verification lifecycle:
        1. Register target software project.
        2. Ingest requirement specifications and identify subjective/ambiguous wording.
        3. Formulate risk-weighted verification strategy.
        4. Derive candidate test cases across multiple verification categories.
        5. Verify API endpoint contracts and isolate schema violations.
        6. Verify relational database integrity non-destructively.
        7. Execute property fuzzing to isolate invariant crashes.
        8. Inject deliberate critical defect and record stack trace.
        9. Evaluate quality gate (must fail closed to UNACCEPTABLE tier).
        10. Verify defect fix with regression detection.
        11. Detect and isolate intermittent flaky tests without masking failures.
        12. Evaluate final production quality gate (must reach PRODUCTION_READY tier).
        """
        # Step 1: Register Project
        project = self.orchestrator.register_project(
            name="Autonomous Core Platform Release 2.5",
            repository_ref="github.com/omnia/core-platform"
        )
        self.assertIsNotNone(project.project_id)

        # Step 2: Ingest Requirements
        req, criteria = self.orchestrator.requirement_analyzer.import_requirement(
            project_id=project.project_id,
            title="User Transaction Pipeline",
            description="The payment processor must handle settlements within 250ms and remain fast and robust.",
            requirement_type=RequirementType.FUNCTIONAL
        )
        self.assertTrue(req.is_ambiguous)  # contains 'fast' and 'robust'
        self.assertGreaterEqual(len(criteria), 1)

        # Step 3: Verification Strategy
        strategy = self.orchestrator.test_intelligence.generate_strategy(
            project_id=project.project_id,
            name="Platform-Release-Strategy",
            requirements=[req],
            allocated_budget_seconds=900.0
        )
        self.assertIn(TestCategory.UNIT, strategy.target_categories)

        # Step 4: Derive Tests
        tests = self.orchestrator.test_generator.generate_tests_for_criterion(criteria[0])
        self.assertGreaterEqual(len(tests), 1)

        # Step 5: Verify API Contracts
        schema = {"required": ["transaction_id", "status"]}
        api_result = self.orchestrator.verify_api_endpoint(
            endpoint_url="/api/v1/settlements",
            expected_schema=schema,
            actual_response={"transaction_id": "tx-99", "status": "SETTLED"},
            expected_status=200,
            actual_status=200,
            project_id=project.project_id,
            test_case_id=tests[0].test_case_id
        )
        self.assertTrue(api_result.passed)

        # Step 6: Verify Database Integrity
        db_result = self.orchestrator.verify_database_state(
            db_path=self.db_name,
            project_id=project.project_id,
            test_case_id=tests[0].test_case_id
        )
        self.assertTrue(db_result.passed)

        # Step 7: Property Fuzzing
        def math_invariant(x: str) -> int:
            return len(x)

        iterations, crashes = self.orchestrator.property_fuzzer.run_fuzz_trials(
            target_func=math_invariant,
            seed=2026,
            iterations=30
        )
        self.assertEqual(len(crashes), 0)

        # Step 8: Log Critical Defect
        defect = self.orchestrator.defect_intelligence.record_defect(
            project_id=project.project_id,
            execution_id="exec-e2e-err",
            title="Double spend race condition in ledger commit",
            category=DefectCategory.CONCURRENCY_RACE,
            severity=DefectSeverity.BLOCKER,
            reproduction_steps=["Fire simultaneous settlement requests for same balance"],
            stack_trace="DoubleSpendError: balance decremented past zero"
        )
        self.assertFalse(defect.is_resolved)

        # Step 9: Gate Check Before Fix (Must Fail Closed)
        gate_blocked = self.orchestrator.execute_quality_gate_assessment(
            project_id=project.project_id,
            mission_id="gate-pre-fix"
        )
        self.assertEqual(gate_blocked.tier, QualityTier.UNACCEPTABLE)

        # Step 10: Repair Verification
        repair_res = self.orchestrator.repair_verifier.verify_defect_repair(
            defect_id=defect.defect_id,
            patch_summary="Introduce row-level distributed lock on balance commit",
            failing_test_recheck_passed=True,
            regression_test_results={"tc-unit-1": True, "tc-contract-1": True}
        )
        self.assertTrue(repair_res.retest_passed and repair_res.regressions_found == 0)

        # Step 11: Flaky Test Detection
        flaky_rec = self.orchestrator.flaky_detector.evaluate_test_stability(
            test_case_id=tests[0].test_case_id,
            execution_results=[True, True, True, True, True]
        )
        self.assertEqual(flaky_rec.classification, FlakyClassification.STABLE_PASSING)

        # Step 12: Final Quality Gate Assessment
        final_assessment = self.orchestrator.execute_quality_gate_assessment(
            project_id=project.project_id,
            mission_id="gate-post-fix"
        )
        self.assertEqual(final_assessment.tier, QualityTier.PRODUCTION_READY)
        self.assertEqual(final_assessment.unresolved_defects_count, 0)

        # Verify QA Reporter output
        report = self.orchestrator.qa_reporter.compile_project_quality_report(project.project_id)
        self.assertTrue(report["gate_recommendation"]["promotable_to_production"])


if __name__ == "__main__":
    unittest.main()
