"""
Autonomous Quality Assurance — Orchestrator Service Facade
Central interface coordinating requirement analysis, test generation, verification execution,
defect management, flaky test detection, and comprehensive quality assessments.
"""
from typing import Dict, Any, List, Optional
import uuid
from datetime import datetime, timezone

from .models import (
    VerificationProject, VerificationRequirement, AcceptanceCriterion, TestStrategy,
    GeneratedTestCase, VerificationMission, VerificationExecution, VerificationResult,
    TestEvidence, CoverageRecord, DefectRecord, RegressionRecord, FlakyTestRecord,
    MutationTestResult, PerformanceAssessment, QualityAssessment, RepairVerification,
    RequirementType, VerificationStatus, TestCategory, DefectSeverity,
    DefectCategory, FlakyClassification, QualityTier
)
from .persistence import QAVerificationRepository
from .requirement_analyzer import RequirementAnalyzer
from .test_intelligence import TestIntelligenceEngine
from .test_generator import TestGenerator
from .test_data_manager import TestDataManager
from .api_verifier import APIContractVerifier
from .frontend_verifier import FrontendVerifier
from .database_verifier import DatabaseIntegrityVerifier
from .performance_verifier import PerformanceVerifier
from .property_fuzz import PropertyFuzzEngine
from .defect_intelligence import DefectIntelligenceEngine
from .flaky_detector import FlakyTestDetector
from .mutation_engine import MutationEngine
from .quality_score import QualityScoreEngine
from .repair_verifier import RepairVerifier
from .qa_reporter import QAReporter
try:
    from events import event_fabric, EventFabric
except Exception:
    event_fabric = None
    EventFabric = Any


class QAVerificationOrchestrator:
    def __init__(self, db_path: str = "omnia.db", event_fabric: Optional[EventFabric] = None):
        self.repo = QAVerificationRepository(db_path=db_path)
        self.event_fabric = event_fabric

        self.requirement_analyzer = RequirementAnalyzer(self.repo)
        self.test_intelligence = TestIntelligenceEngine(self.repo)
        self.test_generator = TestGenerator(self.repo)
        self.test_data_mgr = TestDataManager()
        self.api_verifier = APIContractVerifier()
        self.frontend_verifier = FrontendVerifier()
        self.database_verifier = DatabaseIntegrityVerifier()
        self.performance_verifier = PerformanceVerifier()
        self.property_fuzzer = PropertyFuzzEngine()
        self.defect_intelligence = DefectIntelligenceEngine(self.repo)
        self.flaky_detector = FlakyTestDetector(self.repo)
        self.mutation_engine = MutationEngine(self.repo)
        self.quality_scorer = QualityScoreEngine(self.repo)
        self.repair_verifier = RepairVerifier(self.repo)
        self.qa_reporter = QAReporter(self.repo)

    def register_project(self, name: str, repository_ref: str = "repo/local") -> VerificationProject:
        project_id = f"proj-{uuid.uuid4().hex[:8]}"
        project = VerificationProject(
            project_id=project_id,
            name=name,
            repository_ref=repository_ref
        )
        self.repo.save_project(project)
        self._emit_event("qa.project_registered", {"project_id": project_id, "name": name})
        return project

    def import_and_analyze_requirements(
        self,
        project_id: str,
        spec_text: str,
        requirement_type: RequirementType = RequirementType.FUNCTIONAL
    ) -> List[VerificationRequirement]:
        lines = [line.strip() for line in spec_text.strip().split("\n") if line.strip()]
        imported_reqs = []
        for line in lines:
            req, _ = self.requirement_analyzer.import_requirement(
                project_id=project_id,
                title=line[:60],
                description=line,
                requirement_type=requirement_type
            )
            imported_reqs.append(req)

        self._emit_event("qa.requirements_imported", {
            "project_id": project_id,
            "count": len(imported_reqs)
        })
        return imported_reqs

    def generate_strategy_and_tests(
        self,
        project_id: str,
        risk_profile: str = "BALANCED"
    ) -> Dict[str, Any]:
        reqs = self.repo.list_requirements(project_id)
        budget = 1200.0 if risk_profile == "HIGH_SECURITY" else 600.0
        strategy = self.test_intelligence.generate_strategy(
            project_id=project_id,
            name=f"Strategy-{risk_profile}",
            requirements=reqs,
            allocated_budget_seconds=budget
        )
        generated_tests = []
        for req in reqs:
            criteria = self.repo.list_acceptance_criteria(req.requirement_id)
            for c in criteria:
                tests = self.test_generator.generate_tests_for_criterion(c)
                generated_tests.extend(tests)

        self._emit_event("qa.tests_generated", {
            "project_id": project_id,
            "strategy_id": strategy.strategy_id,
            "test_count": len(generated_tests)
        })
        return {
            "strategy": strategy,
            "test_cases": generated_tests
        }

    def verify_api_endpoint(
        self,
        endpoint_url: str,
        expected_schema: Dict[str, Any],
        actual_response: Dict[str, Any],
        expected_status: int = 200,
        actual_status: int = 200,
        project_id: str = "proj-default",
        test_case_id: str = "tc-api"
    ) -> VerificationResult:
        passed, violations = self.api_verifier.verify_contract(
            endpoint_url=endpoint_url,
            expected_schema=expected_schema,
            actual_response=actual_response,
            expected_status=expected_status,
            actual_status=actual_status
        )
        # Ensure dummy mission and execution exist if saving to DB
        exec_id = f"exec-{uuid.uuid4().hex[:8]}"
        mission_id = f"mis-{uuid.uuid4().hex[:8]}"
        try:
            mission = VerificationMission(
                mission_id=mission_id,
                project_id=project_id,
                strategy_id="strat-default",
                status=VerificationStatus.PASSED if passed else VerificationStatus.FAILED
            )
            self.repo.save_mission(mission)
            execution = VerificationExecution(
                execution_id=exec_id,
                mission_id=mission_id,
                test_case_id=test_case_id,
                status=VerificationStatus.PASSED if passed else VerificationStatus.FAILED
            )
            self.repo.save_execution(execution)
        except Exception:
            pass

        res = VerificationResult(
            result_id=f"res-{uuid.uuid4().hex[:8]}",
            execution_id=exec_id,
            passed=passed,
            observed_output=actual_response,
            discrepancies=violations
        )
        try:
            self.repo.save_result(res)
        except Exception:
            pass

        self._emit_event("qa.api_verified", {
            "project_id": project_id,
            "test_case_id": test_case_id,
            "passed": passed
        })
        return res

    def verify_database_state(
        self,
        db_path: str = "omnia.db",
        project_id: str = "proj-default",
        test_case_id: str = "tc-db"
    ) -> VerificationResult:
        passed, violations = self.database_verifier.verify_sqlite_integrity(db_path=db_path)
        exec_id = f"exec-{uuid.uuid4().hex[:8]}"
        mission_id = f"mis-{uuid.uuid4().hex[:8]}"
        try:
            mission = VerificationMission(
                mission_id=mission_id,
                project_id=project_id,
                strategy_id="strat-default",
                status=VerificationStatus.PASSED if passed else VerificationStatus.FAILED
            )
            self.repo.save_mission(mission)
            execution = VerificationExecution(
                execution_id=exec_id,
                mission_id=mission_id,
                test_case_id=test_case_id,
                status=VerificationStatus.PASSED if passed else VerificationStatus.FAILED
            )
            self.repo.save_execution(execution)
        except Exception:
            pass

        res = VerificationResult(
            result_id=f"res-{uuid.uuid4().hex[:8]}",
            execution_id=exec_id,
            passed=passed,
            observed_output={"db_path": db_path},
            discrepancies=violations
        )
        try:
            self.repo.save_result(res)
        except Exception:
            pass

        self._emit_event("qa.db_verified", {
            "project_id": project_id,
            "test_case_id": test_case_id,
            "passed": passed
        })
        return res

    def execute_quality_gate_assessment(
        self,
        project_id: str,
        mission_id: str = "default-gate"
    ) -> QualityAssessment:
        unresolved = self.repo.list_unresolved_defects(project_id)
        reqs = self.repo.list_requirements(project_id)
        pass_rate = 1.0 if not unresolved else max(0.0, 1.0 - (len(unresolved) * 0.2))
        cov_score = 0.95 if reqs else 0.5
        assessment = self.quality_scorer.evaluate_quality_assessment(
            project_id=project_id,
            mission_id=mission_id,
            functional_pass_rate=pass_rate,
            coverage_score=cov_score,
            unresolved_defects=unresolved
        )
        self._emit_event("qa.assessment_completed", {
            "project_id": project_id,
            "tier": assessment.tier.value,
            "score": assessment.overall_score
        })
        return assessment

    def _emit_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        if self.event_fabric:
            try:
                self.event_fabric.publish(
                    event_type=event_type,
                    payload=payload,
                    source="qa_verification_service"
                )
            except Exception:
                pass


# Global singleton instance
qa_verification_service = QAVerificationOrchestrator()
