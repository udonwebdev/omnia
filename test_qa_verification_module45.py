"""
Unit Tests for OMNIA Module 45: Autonomous Quality Assurance, Software Verification & Continuous Testing Intelligence
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
from qa_verification.requirement_analyzer import RequirementAnalyzer
from qa_verification.test_intelligence import TestIntelligenceEngine
from qa_verification.test_generator import TestGenerator
from qa_verification.api_verifier import APIContractVerifier
from qa_verification.database_verifier import DatabaseIntegrityVerifier
from qa_verification.property_fuzz import PropertyFuzzEngine
from qa_verification.defect_intelligence import DefectIntelligenceEngine
from qa_verification.flaky_detector import FlakyTestDetector
from qa_verification.quality_score import QualityScoreEngine
from qa_verification.repair_verifier import RepairVerifier
from qa_verification.service import QAVerificationOrchestrator


class TestModule45QAVerification(unittest.TestCase):

    def setUp(self):
        self.db_name = f"test_qa_{uuid.uuid4().hex[:8]}.db"
        conn = sqlite3.connect(self.db_name)
        conn.executescript(MIGRATION_V30)
        conn.close()

        self.repo = QAVerificationRepository(db_path=self.db_name)
        self.orchestrator = QAVerificationOrchestrator(db_path=self.db_name)
        self.project = self.orchestrator.register_project(
            name="Omnia QA Engine Test",
            repository_ref="repo/test"
        )
        self.project_id = self.project.project_id

    def tearDown(self):
        if os.path.exists(self.db_name):
            try:
                os.remove(self.db_name)
            except Exception:
                pass

    def test_requirement_analysis_and_acceptance_criteria(self):
        """Test decomposing user specifications into measurable acceptance criteria."""
        spec = "The authentication service must authenticate tokens in under 200ms and remain fast under load."
        req, criteria = self.orchestrator.requirement_analyzer.import_requirement(
            project_id=self.project_id,
            title="User Auth",
            description=spec,
            requirement_type=RequirementType.FUNCTIONAL
        )
        self.assertIsNotNone(req)
        self.assertTrue(req.is_ambiguous)  # Contains 'fast'
        self.assertGreaterEqual(len(criteria), 1)

    def test_test_strategy_and_test_generation(self):
        """Test generating risk-weighted strategies and test cases."""
        spec = "Payment Gateway: Process transactions securely."
        req, criteria = self.orchestrator.requirement_analyzer.import_requirement(
            project_id=self.project_id,
            title="Payments",
            description=spec,
            requirement_type=RequirementType.API_CONTRACT
        )
        strategy = self.orchestrator.test_intelligence.generate_strategy(
            project_id=self.project_id,
            name="SecurityStrategy",
            requirements=[req],
            allocated_budget_seconds=1200.0
        )
        self.assertIn(TestCategory.API_CONTRACT, strategy.target_categories)
        
        # Test case generation
        generated = self.orchestrator.test_generator.generate_tests_for_criterion(criteria[0])
        self.assertGreaterEqual(len(generated), 1)
        self.assertEqual(generated[0].criterion_id, criteria[0].criterion_id)

    def test_api_contract_verification(self):
        """Test API contract verification and failure isolation."""
        verifier = self.orchestrator.api_verifier
        
        expected_schema = {"required": ["id", "status"]}
        good_response = {"id": "123", "status": "ok"}
        bad_response = {"id": "123"}  # missing status

        passed, violations = verifier.verify_contract(
            endpoint_url="/api/test",
            expected_schema=expected_schema,
            actual_response=good_response,
            expected_status=200,
            actual_status=200
        )
        self.assertTrue(passed)
        self.assertEqual(len(violations), 0)

        fail_passed, fail_violations = verifier.verify_contract(
            endpoint_url="/api/test",
            expected_schema=expected_schema,
            actual_response=bad_response,
            expected_status=200,
            actual_status=200
        )
        self.assertFalse(fail_passed)
        self.assertGreater(len(fail_violations), 0)

    def test_database_integrity_verification(self):
        """Test database non-destructive verification."""
        verifier = self.orchestrator.database_verifier
        passed, violations = verifier.verify_sqlite_integrity(db_path=self.db_name)
        self.assertTrue(passed)
        self.assertEqual(len(violations), 0)

    def test_property_fuzzing(self):
        """Test property-based invariant testing and seed isolation."""
        fuzzer = self.orchestrator.property_fuzzer
        
        def safe_parser(payload: str):
            if payload == "crash_me":
                raise ValueError("Boom")
            return len(payload)

        # Invariant: function should not throw unexpected exception
        iterations, crashes = fuzzer.run_fuzz_trials(
            target_func=safe_parser,
            seed=42,
            iterations=50
        )
        self.assertEqual(len(crashes), 0)

    def test_defect_logging_and_repair_verification(self):
        """Test logging defects and verifying repair without regressions."""
        defect = self.orchestrator.defect_intelligence.record_defect(
            project_id=self.project_id,
            execution_id="exec-1",
            title="Authentication token leak",
            category=DefectCategory.SECURITY_VULNERABILITY,
            severity=DefectSeverity.CRITICAL,
            reproduction_steps=["Submit malformed token header"],
            stack_trace="Traceback: leaked memory at 0xdeadbeef"
        )
        self.assertFalse(defect.is_resolved)

        # Verify repair with regression (fails)
        verif_fail = self.orchestrator.repair_verifier.verify_defect_repair(
            defect_id=defect.defect_id,
            patch_summary="Sanitize header parser",
            failing_test_recheck_passed=True,
            regression_test_results={"tc-reg-1": False}
        )
        self.assertFalse(verif_fail.retest_passed and verif_fail.regressions_found == 0)
        rechecked_defect = self.repo.get_defect(defect.defect_id)
        self.assertFalse(rechecked_defect.is_resolved)

        # Verify repair cleanly
        verif_ok = self.orchestrator.repair_verifier.verify_defect_repair(
            defect_id=defect.defect_id,
            patch_summary="Sanitize header parser v2",
            failing_test_recheck_passed=True,
            regression_test_results={"tc-reg-1": True, "tc-reg-2": True}
        )
        self.assertTrue(verif_ok.retest_passed and verif_ok.regressions_found == 0)
        rechecked_defect2 = self.repo.get_defect(defect.defect_id)
        self.assertTrue(rechecked_defect2.is_resolved)

    def test_flaky_test_detection(self):
        """Test isolating intermittent flakiness vs stable pass/fail."""
        detector = self.orchestrator.flaky_detector
        
        history = [True, False, True, True, False, True]
        rec = detector.evaluate_test_stability(
            test_case_id="tc-flaky-test",
            execution_results=history
        )
        self.assertEqual(rec.classification, FlakyClassification.INTERMITTENT_FLAKY)
        self.assertGreater(rec.variance_score, 0.0)

    def test_multi_dimensional_quality_assessment(self):
        """Test comprehensive quality scoring and production readiness gate."""
        # Unacceptable tier when critical defect is open
        defect = self.orchestrator.defect_intelligence.record_defect(
            project_id=self.project_id,
            execution_id="exec-fatal",
            title="Deadlock in storage sync",
            category=DefectCategory.CONCURRENCY_RACE,
            severity=DefectSeverity.BLOCKER,
            reproduction_steps=["Run concurrent writers"]
        )
        assessment = self.orchestrator.execute_quality_gate_assessment(
            project_id=self.project_id,
            mission_id="mission-gate-1"
        )
        self.assertEqual(assessment.tier, QualityTier.UNACCEPTABLE)
        self.assertGreater(assessment.unresolved_defects_count, 0)


if __name__ == "__main__":
    unittest.main()
