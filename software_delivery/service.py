"""
OMNIA Module 44: Autonomous Software Delivery, CI/CD Intelligence & Release Engineering
Subsystem Orchestrator & Facade - service.py

Provides the unified orchestrator facade for Module 44:
- Source Analyzer (`source_analyzer.py`)
- Change Impact Engine (`change_impact.py`)
- Pipeline Planner (`pipeline_planner.py`)
- Build Engine (`build_engine.py`)
- Test Orchestrator (`test_orchestrator.py`)
- Quality Gate (`quality_gate.py`)
- Dependency Intelligence (`dependency_intel.py`)
- Security Gate (`security_gate.py`)
- Artifact Manager (`artifact_manager.py`)
- Provenance Engine (`provenance.py`)
- Regression Detector (`regression.py`)
- Repair Coordinator (`repair_coordinator.py`)
- Release Manager (`release_manager.py`)
- Deployment Handoff Bridge (`handoff.py`)
- Event Fabric Integration (`events/`)
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from software_delivery.artifact_manager import ArtifactManager
from software_delivery.build_engine import BuildEngine
from software_delivery.change_impact import ChangeImpactEngine
from software_delivery.dependency_intel import DependencyIntelligenceEngine
from software_delivery.handoff import DeploymentHandoffBridge
from software_delivery.models import (
    ArtifactAttestation,
    BuildArtifactRecord,
    BuildExecutionRecord,
    ChangeImpactReport,
    DependencyAssessment,
    DeploymentHandoffRecord,
    PipelineDefinition,
    PipelineExecution,
    PipelineStageExecution,
    PipelineStageType,
    PipelineStatus,
    QualityGateResult,
    RegressionFinding,
    ReleaseCandidateRecord,
    ReleaseStage,
    RepairAttemptRecord,
    RepositoryType,
    SecurityAssessment,
    SourceRepository,
    SourceRevision,
    TestExecutionRecord,
)
from software_delivery.persistence import SoftwareDeliveryRepository
from software_delivery.pipeline_planner import PipelinePlanner
from software_delivery.provenance import ProvenanceEngine
from software_delivery.quality_gate import QualityGateEngine
from software_delivery.regression import RegressionDetector
from software_delivery.release_manager import ReleaseManager
from software_delivery.repair_coordinator import RepairCoordinator
from software_delivery.security_gate import SecurityGateEngine
from software_delivery.source_analyzer import SourceAnalyzer
from software_delivery.test_orchestrator import TestOrchestrator

logger = logging.getLogger("Omnia.SoftwareDelivery.Service")


class SoftwareDeliveryOrchestrator:
    """
    Unified entry point and coordinator for Module 44.
    """

    def __init__(
        self,
        repository: Optional[SoftwareDeliveryRepository] = None,
        event_fabric: Optional[Any] = None,
        infrastructure_service: Optional[Any] = None,
    ):
        self.repo = repository or SoftwareDeliveryRepository()
        self.event_fabric = event_fabric

        if infrastructure_service is None:
            try:
                from infrastructure_lifecycle.service import infrastructure_lifecycle_service
                self.infra_service = infrastructure_lifecycle_service
            except Exception:
                self.infra_service = None
        else:
            self.infra_service = infrastructure_service

        # Subsystem engines
        self.source_analyzer = SourceAnalyzer(self.repo)
        self.change_impact = ChangeImpactEngine(self.repo, self.source_analyzer)
        self.pipeline_planner = PipelinePlanner(self.repo)
        self.build_engine = BuildEngine(self.repo)
        self.test_orchestrator = TestOrchestrator(self.repo)
        self.quality_gate = QualityGateEngine(self.repo)
        self.dependency_intel = DependencyIntelligenceEngine(self.repo)
        self.security_gate = SecurityGateEngine(self.repo)
        self.artifact_manager = ArtifactManager(self.repo)
        self.provenance = ProvenanceEngine(self.repo)
        self.regression = RegressionDetector(self.repo)
        self.repair = RepairCoordinator(self.repo)
        self.release_manager = ReleaseManager(self.repo)
        self.handoff_bridge = DeploymentHandoffBridge(self.repo, self.infra_service)

    def _publish_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        if not self.event_fabric:
            return
        try:
            from events.models import Event, EventEnvelope
            envelope = EventEnvelope(
                event_type=event_type,
                source="module44.software_delivery",
            )
            ev = Event(envelope=envelope, payload=payload)
            self.event_fabric.publish(ev)
        except Exception as e:
            logger.debug(f"Failed to publish event {event_type}: {e}")

    # Facade operations
    def register_repository(
        self,
        name: str,
        clone_url: str,
        provider_type: RepositoryType = RepositoryType.GIT_LOCAL,
    ) -> SourceRepository:
        repo = self.source_analyzer.register_repository(name=name, clone_url=clone_url, provider_type=provider_type)
        self._publish_event("delivery.repository_registered", {"repository_id": repo.repository_id})
        return repo

    def analyze_source_revision(
        self,
        repository_id: str,
        commit_hash: str,
        branch: str,
        author: str,
        commit_message: str,
        changed_files: List[str],
    ) -> tuple[SourceRevision, ChangeImpactReport]:
        rev = self.source_analyzer.record_revision(
            repository_id=repository_id,
            commit_hash=commit_hash,
            branch=branch,
            author=author,
            commit_message=commit_message,
        )
        impact = self.change_impact.analyze_changes(
            revision_id=rev.revision_id,
            changed_files=changed_files,
        )
        self._publish_event("delivery.source_revision_detected", {"revision_id": rev.revision_id})
        self._publish_event("delivery.change_impact_analyzed", {"report_id": impact.report_id})
        return rev, impact

    def plan_delivery_pipeline(
        self,
        repository_id: str,
        pipeline_name: str,
        impact_report: ChangeImpactReport,
        target_environment: str = "TESTING",
    ) -> PipelineDefinition:
        pipe_def = self.pipeline_planner.create_pipeline_plan(
            repository_id=repository_id,
            name=pipeline_name,
            impact_report=impact_report,
            target_environment=target_environment,
        )
        self._publish_event("delivery.pipeline_planned", {"pipeline_id": pipe_def.pipeline_id})
        return pipe_def

    def execute_pipeline(
        self,
        pipeline_id: str,
        revision_id: str,
        working_dir: str = ".",
        simulate: bool = True,
        simulate_failure: bool = False,
    ) -> tuple[PipelineExecution, QualityGateResult, SecurityAssessment]:
        pipe_def = self.repo.get_pipeline_definition(pipeline_id)
        if not pipe_def:
            raise KeyError(f"Pipeline definition '{pipeline_id}' not found.")

        exec_id = f"exec-{uuid.uuid4().hex[:8]}"
        execution = PipelineExecution(
            execution_id=exec_id,
            pipeline_id=pipeline_id,
            revision_id=revision_id,
            status=PipelineStatus.RUNNING,
        )
        self.repo.save_pipeline_execution(execution)
        self._publish_event("delivery.pipeline_started", {"execution_id": exec_id})

        builds: List[BuildExecutionRecord] = []
        tests: List[TestExecutionRecord] = []

        # Execute stages
        for stage_type in pipe_def.stages:
            st_id = f"st-{uuid.uuid4().hex[:8]}"
            st_exec = PipelineStageExecution(
                stage_id=st_id,
                pipeline_execution_id=exec_id,
                stage_type=stage_type,
                status=PipelineStatus.RUNNING,
            )
            self.repo.save_stage_execution(st_exec)

            if stage_type == PipelineStageType.BUILD_COMPILE:
                b = self.build_engine.execute_build(
                    pipeline_execution_id=exec_id,
                    command="python setup.py build" if not simulate else "simulated_build",
                    working_dir=working_dir,
                    simulate=simulate,
                )
                builds.append(b)
            elif stage_type == PipelineStageType.UNIT_TEST:
                t = self.test_orchestrator.run_test_suite(
                    pipeline_execution_id=exec_id,
                    suite_name="test_unit",
                    simulate=simulate,
                    simulate_failure=simulate_failure,
                )
                tests.append(t)

            st_exec.status = PipelineStatus.SUCCEEDED
            self.repo.save_stage_execution(st_exec)
            execution.stages_executed.append(stage_type.value)

        # Quality & Security Evaluations
        q_result = self.quality_gate.evaluate_quality(
            pipeline_execution_id=exec_id,
            build_records=builds,
            test_records=tests,
        )
        sec_result = self.security_gate.audit_security(
            revision_id=revision_id,
            simulate_findings=[],
        )

        execution.status = PipelineStatus.SUCCEEDED if q_result.status.value == "PASSED" else PipelineStatus.FAILED
        self.repo.save_pipeline_execution(execution)

        self._publish_event("delivery.pipeline_completed", {"execution_id": exec_id, "status": execution.status.value})
        return execution, q_result, sec_result

    def register_artifact_and_attestation(
        self,
        pipeline_execution_id: str,
        name: str,
        artifact_type: str,
        storage_uri: str,
        source_repository: str,
        source_commit: str,
        checksum_sha256: Optional[str] = None,
    ) -> tuple[BuildArtifactRecord, ArtifactAttestation]:
        art = self.artifact_manager.register_artifact(
            pipeline_execution_id=pipeline_execution_id,
            name=name,
            artifact_type=artifact_type,
            storage_uri=storage_uri,
            checksum_sha256=checksum_sha256,
        )
        att = self.provenance.generate_attestation(
            artifact_id=art.artifact_id,
            source_repository=source_repository,
            source_commit=source_commit,
        )
        self._publish_event("delivery.artifact_registered", {"artifact_id": art.artifact_id})
        return art, att

    def create_and_promote_release(
        self,
        version: str,
        artifact_id: str,
        source_revision_id: str,
        target_stage: ReleaseStage = ReleaseStage.QUALIFIED,
        approval_token: Optional[str] = None,
        approver: Optional[str] = None,
    ) -> ReleaseCandidateRecord:
        rc = self.release_manager.create_release_candidate(
            version=version,
            artifact_id=artifact_id,
            source_revision_id=source_revision_id,
            release_notes=f"Release {version}",
        )
        promoted_rc = self.release_manager.promote_release(
            candidate_id=rc.candidate_id,
            target_stage=target_stage,
            approval_token=approval_token,
            approver=approver,
        )
        self._publish_event("delivery.release_promoted", {"candidate_id": rc.candidate_id, "stage": target_stage.value})
        return promoted_rc

    def handoff_deployment(
        self,
        release_candidate_id: str,
        target_environment_id: str,
        deployment_strategy: str = "DIRECT",
        approval_token: Optional[str] = None,
    ) -> DeploymentHandoffRecord:
        handoff = self.handoff_bridge.request_deployment_handoff(
            release_candidate_id=release_candidate_id,
            target_environment_id=target_environment_id,
            deployment_strategy=deployment_strategy,
            approval_token=approval_token,
        )
        self._publish_event("delivery.deployment_handoff_requested", {"handoff_id": handoff.handoff_id})
        return handoff


# Module-level singleton instance
software_delivery_service = SoftwareDeliveryOrchestrator()
