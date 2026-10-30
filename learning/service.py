"""
Omnia Module 33: Adaptive Learning & Model Lifecycle Governance Service
Primary facade orchestrating learning signals, datasets, experiments,
model registry, non-bypassable promotion gates, rollouts, rollbacks,
and drift monitoring with Event Fabric integration.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from events.fabric import EventFabric, event_fabric
from events.models import Event, EventEnvelope
from learning.advisor import ParameterAdvisor
from learning.attribution import OutcomeAttributor
from learning.datasets import DatasetBuilder
from learning.drift import DriftMonitor
from learning.experiments import ExperimentEngine
from learning.gates import PromotionGatekeeper
from learning.models import (
    AttributionConfidence,
    DatasetPurpose,
    DriftRecord,
    ExperimentConfig,
    ExperimentStatus,
    ExperimentType,
    GateResult,
    LearningDataset,
    LearningSignal,
    ModelLifecycleStatus,
    ModelVersion,
    ParameterRecommendation,
    PromotionRequest,
    RolloutRecord,
    RolloutStage,
    RolloutStatus,
    SignalQualityStatus,
    SignalType,
)
from learning.persistence import LearningRepository
from learning.registry import ModelRegistry
from learning.rollback import RollbackCoordinator
from learning.rollout import RolloutCoordinator
from learning.tracking import StrategyPerformanceTracker
from learning.validation import SignalValidator

logger = logging.getLogger(__name__)


class AdaptiveLearningService:
    """
    Unified production facade for Module 33: Adaptive Learning & Model Lifecycle Governance.
    """

    def __init__(
        self,
        repository: Optional[LearningRepository] = None,
        event_bus: Optional[EventFabric] = None,
    ) -> None:
        self.repository = repository or LearningRepository()
        self.event_bus = event_bus or event_fabric

        self.validator = SignalValidator()
        self.attributor = OutcomeAttributor()
        self.dataset_builder = DatasetBuilder()
        self.tracker = StrategyPerformanceTracker()
        self.experiment_engine = ExperimentEngine()
        self.advisor = ParameterAdvisor()
        self.registry = ModelRegistry()
        self.gatekeeper = PromotionGatekeeper()
        self.rollout_coordinator = RolloutCoordinator()
        self.rollback_coordinator = RollbackCoordinator()
        self.drift_monitor = DriftMonitor()

    # -------------------------------------------------------------
    # 1. SIGNAL INGESTION & ATTRIBUTION
    # -------------------------------------------------------------
    def record_signal(
        self,
        signal_id: str,
        source_subsystem: str,
        signal_type: SignalType,
        strategy_id: str,
        metric_name: str,
        metric_value: float,
        payload: Dict[str, Any],
        model_version_id: Optional[str] = None,
        task_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        outcome_status: str = "SUCCESS",
        environmental_factors: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[LearningSignal], str]:
        """
        Validates, sanitizes, attributes, and persists a learning signal.
        """
        clean_payload = self.validator.sanitize_payload(payload)
        provenance_hash = self.validator.compute_payload_hash(clean_payload)

        metrics = {metric_name: metric_value}

        signal = LearningSignal(
            signal_id=signal_id,
            signal_type=signal_type,
            source_module=source_subsystem,
            source_record_id=execution_id or signal_id,
            event_time=time.time(),
            observation_time=time.time(),
            outcome_status=outcome_status,
            metrics=metrics,
            task_id=task_id,
            model_version=model_version_id,
            strategy_id=strategy_id,
            is_verified=False,
            quality_status=SignalQualityStatus.ACCEPTED,
            provenance_hash=provenance_hash,
            created_at=time.time(),
        )

        is_valid, quality_status, reason = self.validator.validate_signal(signal)
        signal.quality_status = quality_status

        if not is_valid:
            logger.warning("Learning signal %s rejected: %s", signal_id, reason)
            return False, signal, reason

        self.attributor.attribute_outcome(signal, environmental_factors)
        self.repository.save_signal(signal)

        self._emit_event(
            event_type="learning.signal_recorded",
            source=source_subsystem,
            payload={
                "signal_id": signal_id,
                "strategy_id": strategy_id,
                "metric_name": metric_name,
                "metric_value": metric_value,
            },
        )

        return True, signal, "Signal recorded successfully"

    # -------------------------------------------------------------
    # 2. DATASET BUILDING
    # -------------------------------------------------------------
    def create_dataset(
        self,
        dataset_id: str,
        name: str,
        version: str,
        purpose: DatasetPurpose,
        strategy_id: Optional[str] = None,
        source_subsystem: Optional[str] = None,
        train_val_split_ratio: float = 0.8,
        temporal_cutoff: Optional[float] = None,
    ) -> LearningDataset:
        signals = self.repository.list_signals(strategy_id=strategy_id, source_module=source_subsystem, limit=1000)
        dataset = self.dataset_builder.build_dataset(
            dataset_id=dataset_id,
            version=version,
            purpose=purpose,
            signals=signals,
            train_val_split_ratio=train_val_split_ratio,
            temporal_cutoff=temporal_cutoff,
        )
        self.repository.save_dataset(dataset)

        self._emit_event(
            event_type="learning.dataset_materialized",
            source="learning.dataset_builder",
            payload={
                "dataset_id": dataset_id,
                "version": version,
                "sample_count": dataset.sample_count,
                "content_digest": dataset.content_digest,
            },
        )
        return dataset

    # -------------------------------------------------------------
    # 3. MODEL / STRATEGY REGISTRATION
    # -------------------------------------------------------------
    def register_model_version(
        self,
        model_version_id: str,
        name: str,
        version: str,
        artifact_uri: str,
        artifact_checksum: str,
        hyperparameters: Dict[str, Any],
        author: str = "system",
        description: str = "",
        model_family: str = "orchestration",
    ) -> ModelVersion:
        m_version = self.registry.register_version(
            model_id=name,
            version_id=version,
            model_family=model_family,
            artifact_ref=artifact_uri,
            artifact_digest=artifact_checksum,
            created_by=author,
            limitations=[description] if description else [],
            evaluation_summary={"hyperparameters": hyperparameters},
        )
        self.repository.save_model_version(m_version)

        self._emit_event(
            event_type="learning.model_version_registered",
            source="learning.registry",
            payload={
                "model_id": name,
                "version_id": version,
                "artifact_digest": artifact_checksum,
                "author": author,
            },
        )
        return m_version

    # -------------------------------------------------------------
    # 4. EVALUATION & PROMOTION GATES
    # -------------------------------------------------------------
    def evaluate_and_request_promotion(
        self,
        request_id: str,
        candidate_version_id: str,
        baseline_version_id: Optional[str],
        target_subsystem: str,
        justification: str,
        evaluation_metrics: Dict[str, float],
        baseline_metrics: Dict[str, float],
        regression_test_results: Dict[str, bool],
        policy_validation_passed: bool,
        security_audit_passed: bool,
        rollback_target_verified: bool,
        human_approval_signature: Optional[str] = None,
    ) -> PromotionRequest:
        candidate = self.repository.get_model_version(candidate_version_id)
        if not candidate:
            raise ValueError(f"Candidate model version not found: {candidate_version_id}")

        baseline = self.repository.get_model_version(baseline_version_id) if baseline_version_id else None

        req = PromotionRequest(
            request_id=request_id,
            candidate_id=candidate.model_id,
            candidate_version=candidate.version_id,
            baseline_version=baseline.version_id if baseline else "none",
            risk_level="LOW",
            status="PENDING",
            gate_results=[],
            approval_request_id=f"appr-{request_id}",
            approved_by=human_approval_signature,
            approved_at=time.time() if human_approval_signature else None,
            target_rollout_stage=RolloutStage.CANARY,
            current_rollout_stage=RolloutStage.OFFLINE,
            rollback_target_version=baseline.version_id if baseline else "none",
            created_at=time.time(),
            updated_at=time.time(),
        )

        all_passed, gate_results = self.gatekeeper.evaluate_gates(
            request=req,
            candidate_version=candidate,
            baseline_version=baseline,
            evaluation_metrics=evaluation_metrics,
            baseline_metrics=baseline_metrics,
            regression_test_results=regression_test_results,
            policy_validation_passed=policy_validation_passed,
            security_audit_passed=security_audit_passed,
            rollback_target_verified=rollback_target_verified,
            human_approval_signature=human_approval_signature,
        )

        req.gate_results = gate_results
        req.status = "APPROVED" if (all_passed and human_approval_signature) else "REJECTED"

        if not all_passed:
            failed_gates = [g.gate_name for g in gate_results if not g.passed]
            req.rejection_reason = f"Failed mandatory gates: {failed_gates}"
            candidate.status = ModelLifecycleStatus.REJECTED
        elif human_approval_signature:
            candidate.status = ModelLifecycleStatus.APPROVED
        else:
            req.rejection_reason = "Missing mandatory human approval signature"
            candidate.status = ModelLifecycleStatus.APPROVAL_PENDING

        self.repository.save_promotion_request(req)
        self.repository.save_model_version(candidate)

        self._emit_event(
            event_type="learning.promotion_evaluated",
            source="learning.promotion_gatekeeper",
            payload={
                "request_id": request_id,
                "candidate_id": candidate.model_id,
                "all_gates_passed": all_passed,
                "status": req.status,
            },
        )
        return req

    # -------------------------------------------------------------
    # 5. CONTROLLED ROLLOUT & VERIFIED ROLLBACK
    # -------------------------------------------------------------
    def initiate_rollout(
        self,
        rollout_id: str,
        candidate_version_id: str,
        baseline_version_id: str,
        target_subsystem: str,
        initial_traffic_percent: float = 0.05,
        stage: RolloutStage = RolloutStage.CANARY,
    ) -> RolloutRecord:
        candidate = self.repository.get_model_version(candidate_version_id)
        if not candidate or candidate.status not in (ModelLifecycleStatus.APPROVED, ModelLifecycleStatus.STAGING, ModelLifecycleStatus.CANARY):
            raise ValueError(f"Candidate {candidate_version_id} must be in APPROVED/STAGING/CANARY state")

        record = RolloutRecord(
            rollout_id=rollout_id,
            request_id=f"req-{rollout_id}",
            candidate_version=candidate.version_id,
            baseline_version=baseline_version_id,
            current_stage=stage,
            canary_traffic_pct=initial_traffic_percent,
            status=RolloutStatus.IN_PROGRESS,
            started_at=time.time(),
            updated_at=time.time(),
        )
        candidate.status = ModelLifecycleStatus.CANARY

        self.repository.save_rollout(record)
        self.repository.save_model_version(candidate)

        self._emit_event(
            event_type="learning.rollout_started",
            source="learning.rollout_coordinator",
            payload={
                "rollout_id": rollout_id,
                "candidate_version": candidate.version_id,
                "canary_traffic_pct": initial_traffic_percent,
            },
        )
        return record

    def rollback_rollout(
        self,
        rollout_id: str,
        reason: str,
        initiated_by: str = "system",
    ) -> Tuple[bool, str]:
        record = self.repository.get_rollout(rollout_id)
        if not record:
            return False, f"Rollout record not found: {rollout_id}"

        candidate = self.repository.get_model_version(record.candidate_version)
        record.canary_traffic_pct = 0.0
        record.status = RolloutStatus.ROLLED_BACK
        record.halt_reason = reason
        record.completed_at = time.time()
        record.updated_at = time.time()

        if candidate:
            candidate.status = ModelLifecycleStatus.REVOKED
            self.repository.save_model_version(candidate)

        self.repository.save_rollout(record)

        self._emit_event(
            event_type="learning.rollback_executed",
            source="learning.rollback_coordinator",
            payload={
                "rollout_id": rollout_id,
                "candidate_version": record.candidate_version,
                "reason": reason,
            },
        )
        return True, f"Successfully rolled back rollout {rollout_id} to baseline {record.baseline_version}"

    # -------------------------------------------------------------
    # 6. DRIFT MONITORING
    # -------------------------------------------------------------
    def assess_feature_drift(
        self,
        subsystem: str,
        feature_name: str,
        baseline_distribution: List[float],
        current_distribution: List[float],
        model_id: str = "omnia-model",
        version_id: str = "v1",
    ) -> DriftRecord:
        record = self.drift_monitor.evaluate_feature_drift(
            model_id=model_id,
            version_id=version_id,
            feature_name=feature_name,
            baseline_distribution=baseline_distribution,
            current_distribution=current_distribution,
        )
        self.repository.save_drift(record)

        self._emit_event(
            event_type="learning.drift_detected",
            source="learning.drift_monitor",
            payload={
                "record_id": record.record_id,
                "feature": feature_name,
                "severity": record.severity.value,
            },
        )
        return record

    def assess_performance_drift(
        self,
        subsystem: str,
        metric_name: str,
        baseline_value: float,
        current_value: float,
        sample_size: int = 100,
        model_id: str = "omnia-model",
        version_id: str = "v1",
    ) -> DriftRecord:
        record = self.drift_monitor.evaluate_performance_decay(
            model_id=model_id,
            version_id=version_id,
            metric_name=metric_name,
            baseline_value=baseline_value,
            current_value=current_value,
        )
        self.repository.save_drift(record)

        self._emit_event(
            event_type="learning.performance_decay_detected",
            source="learning.drift_monitor",
            payload={
                "record_id": record.record_id,
                "metric": metric_name,
                "severity": record.severity.value,
            },
        )
        return record

    # -------------------------------------------------------------
    # 7. ADVISOR
    # -------------------------------------------------------------
    def recommend_parameter_tuning(
        self,
        recommendation_id: str,
        parameter_key: str,
        current_value: Any,
        suggested_value: Any,
        subsystem: str,
        justification: str,
        supporting_signal_ids: List[str],
        expected_improvement: str,
    ) -> Tuple[bool, Optional[ParameterRecommendation], str]:
        return self.advisor.recommend_adjustment(
            recommendation_id=recommendation_id,
            parameter_key=parameter_key,
            current_value=current_value,
            proposed_value=suggested_value,
            subsystem=subsystem,
            justification=justification,
            supporting_signal_ids=supporting_signal_ids,
            expected_improvement=expected_improvement,
        )

    # -------------------------------------------------------------
    # INTERNAL HELPERS
    # -------------------------------------------------------------
    def _emit_event(self, event_type: str, source: str, payload: Dict[str, Any]) -> None:
        try:
            envelope = EventEnvelope(
                event_type=event_type,
                source=f"omnia.{source}",
            )
            event = Event(
                envelope=envelope,
                payload=payload,
            )
            self.event_bus.publish(event)
        except Exception as e:
            logger.debug("Failed to publish event %s: %s", event_type, e)


# Global singleton instance
adaptive_learning_service = AdaptiveLearningService()
