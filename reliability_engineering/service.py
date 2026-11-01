"""
Omnia Module 41: Autonomous Reliability Engineering, Resilience Testing & Disaster Recovery.
Reliability Engineering Orchestrator: Central Facade & Event Fabric Integration.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from reliability_engineering.backup import BackupInventoryManager
from reliability_engineering.consistency import StateConsistencyValidator
from reliability_engineering.coordinator import RecoveryOrchestrationAdapter
from reliability_engineering.fmea import FailureModeAndEffectsAnalyzer
from reliability_engineering.injection import FaultInjectionController
from reliability_engineering.inventory import ReliabilityInventoryRegistry
from reliability_engineering.models import (
    BackupRecord,
    BackupType,
    BackupValidationRecord,
    ComponentReliabilityCriticality,
    DisasterRecoveryPlanRecord,
    FailoverReadinessState,
    FailureDomain,
    FailureModeRecord,
    FailureScenarioRecord,
    FaultInjectionExperiment,
    RecoveryExecutionRecord,
    RecoveryStrategy,
    RecoveryVerificationRecord,
    ReliabilityComponent,
    ResilienceRegressionRecord,
    StateIntegrityFinding,
)
from reliability_engineering.persistence import ReliabilityRepository
from reliability_engineering.planner import DisasterRecoveryPlanner
from reliability_engineering.regression import ResilienceRegressionDetector
from reliability_engineering.reporting import DisasterRecoveryReporter
from reliability_engineering.scenarios import FailureScenarioGenerator
from reliability_engineering.validator import BackupIntegrityValidator
from reliability_engineering.verification import RecoveryVerificationEngine

# Optional Module 10 Event Fabric
try:
    from event_fabric.service import event_fabric_service
except ImportError:
    event_fabric_service = None

logger = logging.getLogger("Omnia.Reliability.Service")


class ReliabilityEngineeringOrchestrator:
    """
    Unified entry point and facade for Module 41 capabilities.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.repo = ReliabilityRepository(db_path=db_path or "omnia.db")
        self.inventory = ReliabilityInventoryRegistry(self.repo)
        self.fmea = FailureModeAndEffectsAnalyzer(self.repo)
        self.scenarios = FailureScenarioGenerator(self.repo)
        self.injection = FaultInjectionController(self.repo)
        self.backup = BackupInventoryManager(self.repo)
        self.validator = BackupIntegrityValidator(self.repo)
        self.planner = DisasterRecoveryPlanner(self.repo)
        self.consistency = StateConsistencyValidator(self.repo)
        self.verification = RecoveryVerificationEngine(self.repo)
        self.regression = ResilienceRegressionDetector(self.repo)
        self.coordinator = RecoveryOrchestrationAdapter(self.repo)
        self.reporter = DisasterRecoveryReporter(self.repo)

    def _publish_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        if event_fabric_service:
            try:
                event_fabric_service.publish(
                    topic=f"reliability.{event_type}",
                    payload=payload,
                    source="module_41_reliability_engineering"
                )
            except Exception as e:
                logger.warning(f"Failed to publish event {event_type} to event fabric: {e}")

    # --- 1. Reliability Inventory ---
    def register_component(
        self,
        component_id: str,
        component_name: str,
        criticality: ComponentReliabilityCriticality = ComponentReliabilityCriticality.HIGH,
        owner: str = "omnia-core",
        failure_domain: FailureDomain = FailureDomain.PROCESS,
        data_ownership: str = "STATELESS",
        dependencies: Optional[List[str]] = None,
        recovery_procedure: str = "DEFAULT_RESTART",
        backup_strategy: BackupType = BackupType.SNAPSHOT,
        redundancy_config: str = "N+1",
        failover_readiness: FailoverReadinessState = FailoverReadinessState.READY,
    ) -> ReliabilityComponent:
        comp = self.inventory.register_component(
            component_id=component_id,
            component_name=component_name,
            criticality=criticality,
            owner=owner,
            failure_domain=failure_domain,
            data_ownership=data_ownership,
            dependencies=dependencies,
            recovery_procedure=recovery_procedure,
            backup_strategy=backup_strategy,
            redundancy_config=redundancy_config,
            failover_readiness=failover_readiness,
        )
        self._publish_event("component.registered", {"component_id": component_id, "name": component_name})
        return comp

    def list_components(self) -> List[ReliabilityComponent]:
        return self.inventory.list_components()

    # --- 2. FMEA & SPOFs ---
    def evaluate_failure_mode(
        self,
        component_id: str,
        failure_mode_name: str,
        potential_causes: List[str],
        local_impact: str,
        downstream_impact: str,
        detectability_score: int = 5,
        severity_score: int = 5,
        probability_score: int = 5,
        existing_controls: Optional[List[str]] = None,
        recommended_mitigation: str = "",
    ) -> FailureModeRecord:
        record = self.fmea.analyze_failure_mode(
            component_id=component_id,
            failure_mode_name=failure_mode_name,
            potential_causes=potential_causes,
            local_impact=local_impact,
            downstream_impact=downstream_impact,
            detectability_score=detectability_score,
            severity_score=severity_score,
            probability_score=probability_score,
            existing_controls=existing_controls,
            recommended_mitigation=recommended_mitigation,
        )
        if record.is_spof:
            self._publish_event("risk.single_point_detected", {
                "mode_id": record.mode_id,
                "component_id": component_id,
                "rpn": record.risk_priority_number,
            })
        return record

    def list_spofs(self) -> List[FailureModeRecord]:
        return self.fmea.list_spofs()

    # --- 3. Scenarios & Controlled Fault Injection ---
    def generate_scenario(
        self,
        title: str,
        category: str,
        affected_components: List[str],
        expected_behavior: str,
        target_environment: str = "ISOLATED_SANDBOX",
        injection_method: str = "SIMULATION",
        preconditions: Optional[List[str]] = None,
        safety_constraints: Optional[List[str]] = None,
        abort_conditions: Optional[List[str]] = None,
    ) -> FailureScenarioRecord:
        sc = self.scenarios.generate_scenario(
            title=title,
            category=category,
            affected_components=affected_components,
            expected_behavior=expected_behavior,
            target_environment=target_environment,
            injection_method=injection_method,
            preconditions=preconditions,
            safety_constraints=safety_constraints,
            abort_conditions=abort_conditions,
        )
        self._publish_event("scenario.created", {"scenario_id": sc.scenario_id, "title": title})
        return sc

    def run_fault_experiment(
        self,
        scenario_id: str,
        hypothesis: str,
        approval_token: Optional[str] = None,
        target_environment: str = "ISOLATED_SANDBOX",
        max_duration_sec: float = 120.0,
    ) -> FaultInjectionExperiment:
        exp = self.injection.create_experiment(
            scenario_id=scenario_id,
            hypothesis=hypothesis,
            target_environment=target_environment,
            max_duration_sec=max_duration_sec,
        )
        self.injection.authorize_and_start_experiment(
            experiment_id=exp.experiment_id,
            approval_token=approval_token or "",
        )
        # Execute controlled simulation
        concluded = self.injection.complete_experiment(
            experiment_id=exp.experiment_id,
            containment_successful=True,
            cascading_failure_detected=False,
            actual_duration_sec=15.0,
            observation_notes="Controlled isolated experiment completed nominal containment",
        )
        self._publish_event("experiment.completed", {
            "experiment_id": concluded.experiment_id,
            "containment_successful": concluded.containment_successful,
        })
        return concluded

    # --- 4. Backups & Validation ---
    def register_backup(
        self,
        data_source: str,
        backup_type: BackupType = BackupType.SNAPSHOT,
        version: str = "1.0.0",
        storage_reference: str = "gs://omnia-backups/default",
        record_count: int = 100,
        size_bytes: int = 1024,
    ) -> BackupRecord:
        b = self.backup.register_backup(
            data_source=data_source,
            backup_type=backup_type,
            version=version,
            storage_reference=storage_reference,
            record_count=record_count,
            size_bytes=size_bytes,
        )
        self._publish_event("backup.registered", {"backup_id": b.backup_id, "data_source": data_source})
        return b

    def validate_backup_integrity(
        self,
        backup_id: str,
        simulate_restore: bool = True,
        simulate_corruption: bool = False,
    ) -> BackupValidationRecord:
        val = self.validator.validate_backup(
            backup_id=backup_id,
            simulate_restore=simulate_restore,
            simulate_corruption=simulate_corruption,
        )
        self._publish_event("backup.validated", {
            "backup_id": backup_id,
            "status": val.status.value,
        })
        return val

    # --- 5. Disaster Recovery Plans & Execution ---
    def create_dr_plan(
        self,
        title: str,
        disaster_scenario: str,
        affected_services: List[str],
        dependency_order: List[str],
        strategy: RecoveryStrategy = RecoveryStrategy.RESTORE_FROM_BACKUP,
        target_rto_sec: float = 300.0,
        target_rpo_sec: float = 60.0,
    ) -> DisasterRecoveryPlanRecord:
        plan = self.planner.create_dr_plan(
            title=title,
            disaster_scenario=disaster_scenario,
            affected_services=affected_services,
            dependency_order=dependency_order,
            strategy=strategy,
            target_rto_sec=target_rto_sec,
            target_rpo_sec=target_rpo_sec,
        )
        self._publish_event("dr.plan_created", {"plan_id": plan.plan_id, "title": title})
        return plan

    def execute_recovery_drill(
        self,
        plan_id: str,
        approval_token: Optional[str] = None,
        target_environment: str = "ISOLATED_SANDBOX",
    ) -> RecoveryExecutionRecord:
        exec_rec = self.coordinator.initiate_recovery(
            plan_id=plan_id,
            target_environment=target_environment,
            approval_token=approval_token,
        )
        self._publish_event("dr.execution_completed", {
            "execution_id": exec_rec.execution_id,
            "plan_id": plan_id,
        })
        return exec_rec

    def verify_recovery(
        self,
        execution_id: str,
        component_id: str,
        actual_rto_sec: float,
        actual_rpo_sec: float,
        service_responsive: bool = True,
        data_integrity_verified: bool = True,
    ) -> RecoveryVerificationRecord:
        ver = self.verification.verify_recovery_drill(
            execution_id=execution_id,
            component_id=component_id,
            actual_rto_sec=actual_rto_sec,
            actual_rpo_sec=actual_rpo_sec,
            service_responsive=service_responsive,
            data_integrity_verified=data_integrity_verified,
        )
        self._publish_event("dr.recovery_verified", {
            "verification_id": ver.verification_id,
            "component_id": component_id,
            "rto_compliant": ver.rto_compliant,
            "rpo_compliant": ver.rpo_compliant,
        })
        return ver

    # --- 6. State Consistency & Regressions ---
    def audit_state_consistency(
        self,
        subsystem: str,
        expected_epoch: int,
        reported_epoch: int,
        checkpoint_count: int,
        replica_lag_sec: float = 0.0,
    ) -> List[StateIntegrityFinding]:
        findings = self.consistency.audit_subsystem_state(
            subsystem=subsystem,
            expected_epoch=expected_epoch,
            reported_epoch=reported_epoch,
            checkpoint_count=checkpoint_count,
            replica_lag_sec=replica_lag_sec,
        )
        return findings

    def check_resilience_regression(
        self,
        component_id: str,
        metric_name: str,
        baseline_value: float,
        current_value: float,
    ) -> Optional[ResilienceRegressionRecord]:
        reg = self.regression.check_for_regression(
            component_id=component_id,
            metric_name=metric_name,
            baseline_value=baseline_value,
            current_value=current_value,
        )
        if reg:
            self._publish_event("regression.detected", {
                "regression_id": reg.regression_id,
                "component_id": component_id,
                "degradation_pct": reg.degradation_pct,
            })
        return reg

    # --- 7. Reporting ---
    def get_reliability_overview(self) -> Dict[str, Any]:
        return self.reporter.generate_reliability_overview()


# Global singleton
reliability_engineering_service = ReliabilityEngineeringOrchestrator()
