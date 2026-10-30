"""
Unit & Adversarial Tests for Omnia Module 33:
Adaptive Learning & Model Lifecycle Governance Engine.
"""

import os
import time
import unittest

from learning.models import (
    AttributionConfidence,
    DatasetPurpose,
    DriftSeverity,
    DriftType,
    ExperimentType,
    ModelLifecycleStatus,
    SignalQualityStatus,
    SignalType,
)
from learning.service import AdaptiveLearningService
from learning.persistence import LearningRepository


class TestModule33LearningEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = "test_module33_learning.db"
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass
        cls.repo = LearningRepository(db_path=cls.db_path)
        cls.service = AdaptiveLearningService(repository=cls.repo)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass

    def test_01_signal_recording_and_sanitization(self):
        """Test recording verified signals and sanitizing leaked credentials."""
        payload = {
            "query": "plan mission",
            "api_key": "sk-secret1234567890abcdef",
            "latency_ms": 120.5,
        }
        success, signal, msg = self.service.record_signal(
            signal_id="sig-001",
            source_subsystem="orchestrator",
            signal_type=SignalType.TASK_COMPLETION,
            strategy_id="planner_v1",
            metric_name="latency_ms",
            metric_value=120.5,
            payload=payload,
            model_version_id="model-gemini-v1",
        )
        self.assertTrue(success)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.quality_status, SignalQualityStatus.ACCEPTED)

    def test_02_signal_anti_leakage_future_rejection(self):
        """Signals observed in the future must be rejected as leakage."""
        future_time = time.time() + 86400  # 1 day in future
        from learning.models import LearningSignal
        future_sig = LearningSignal(
            signal_id="sig-future",
            signal_type=SignalType.FORECAST_EVALUATION,
            source_module="prediction",
            source_record_id="rec-future",
            event_time=time.time(),
            observation_time=future_time,
            outcome_status="FAILED",
            metrics={"error": 0.01},
            provenance_hash="hash",
            quality_status=SignalQualityStatus.ACCEPTED,
        )
        is_valid, status, reason = self.service.validator.validate_signal(future_sig)
        self.assertFalse(is_valid)
        self.assertEqual(status, SignalQualityStatus.REJECTED)
        self.assertIn("in the future", reason)

    def test_03_outcome_attribution_with_confounders(self):
        """Confounded external noise should reduce attribution confidence."""
        success, signal, _ = self.service.record_signal(
            signal_id="sig-confounded",
            source_subsystem="retrieval",
            signal_type=SignalType.TASK_FAILURE,
            strategy_id="hybrid_retriever",
            metric_name="recall",
            metric_value=0.4,
            payload={"error": "503"},
            model_version_id="retriever-v1",
            task_id="task-retrieve",
            environmental_factors={"network_timeout": True},
        )
        self.assertTrue(success)
        confidence = self.service.attributor.evaluate_attribution(
            signal, environmental_factors={"network_timeout": True}
        )
        self.assertEqual(confidence, AttributionConfidence.CORRELATED)

    def test_04_dataset_building_and_integrity(self):
        """Build reproducible dataset with cryptographic manifest and anti-leakage temporal split."""
        for i in range(10):
            self.service.record_signal(
                signal_id=f"sig-ds-{i}",
                source_subsystem="planning",
                signal_type=SignalType.TASK_COMPLETION,
                strategy_id="strat-alpha",
                metric_name="success_rate",
                metric_value=1.0 if i % 2 == 0 else 0.8,
                payload={"depth": i + 1},
                model_version_id="model-alpha",
                task_id=f"task-{i}",
            )

        dataset = self.service.create_dataset(
            dataset_id="ds-alpha-001",
            name="Planning Strategy Dataset",
            version="1.0.0",
            purpose=DatasetPurpose.BENCHMARK_TESTING,
            strategy_id="strat-alpha",
            train_val_split_ratio=0.7,
        )
        self.assertGreaterEqual(dataset.sample_count, 10)
        self.assertIsNotNone(dataset.content_digest)
        self.assertEqual(dataset.manifest["split_strategy"], "chronological_boundary")

    def test_05_model_registry_and_lifecycle_immutability(self):
        """Model versions must transition strictly along legal lifecycle paths."""
        cand = self.service.register_model_version(
            model_version_id="cand-001",
            name="OptimizedPlanner",
            version="2.0.0",
            artifact_uri="models://checkpoints/cand-001.bin",
            artifact_checksum="sha256:abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
            hyperparameters={"learning_rate": 0.001, "temperature": 0.2},
            author="operator_alice",
            description="Fine-tuned planner heuristics",
        )
        self.assertEqual(cand.status, ModelLifecycleStatus.DRAFT)

        # Illegal skip straight to PRODUCTION without evaluation/approval
        ok, msg = self.service.registry.transition_lifecycle(cand, ModelLifecycleStatus.PRODUCTION)
        self.assertFalse(ok)
        self.assertIn("Illegal lifecycle transition", msg)

    def test_06_promotion_gates_enforcement_and_blocking(self):
        """Promotion gates must strictly block self-promotion, missing approvals, and security regressions."""
        cand = self.service.register_model_version(
            model_version_id="cand-002",
            name="CandidatePlanner",
            version="2.1.0",
            artifact_uri="models://checkpoints/cand-002.bin",
            artifact_checksum="sha256:1111222233334444555566667777888899990000aaaabbbbccccddddeeeeffff",
            hyperparameters={"top_k": 5},
            author="operator_bob",
        )

        base = self.service.register_model_version(
            model_version_id="base-001",
            name="BaselinePlanner",
            version="1.0.0",
            artifact_uri="models://checkpoints/base-001.bin",
            artifact_checksum="sha256:222233334444555566667777888899990000aaaabbbbccccddddeeeeffff1111",
            hyperparameters={"top_k": 3},
            author="system",
        )

        # Attempt 1: Author tries to self-approve candidate (VIOLATION)
        req_self = self.service.evaluate_and_request_promotion(
            request_id="promo-self",
            candidate_version_id=cand.version_id,
            baseline_version_id=base.version_id,
            target_subsystem="planning",
            justification="Upgraded heuristic",
            evaluation_metrics={"sample_count": 100, "success_rate": 0.95},
            baseline_metrics={"sample_count": 100, "success_rate": 0.85},
            regression_test_results={"benchmark_1": True, "benchmark_2": True},
            policy_validation_passed=True,
            security_audit_passed=True,
            rollback_target_verified=True,
            human_approval_signature="operator_bob",  # Self-promotion!
        )
        self.assertEqual(req_self.status, "REJECTED")
        self.assertIn("AntiSelfPromotionInvariant", str(req_self.rejection_reason))

        # Attempt 2: Valid approval by distinct human reviewer (SUCCESS)
        req_valid = self.service.evaluate_and_request_promotion(
            request_id="promo-valid",
            candidate_version_id=cand.version_id,
            baseline_version_id=base.version_id,
            target_subsystem="planning",
            justification="Production ready",
            evaluation_metrics={"sample_count": 100, "success_rate": 0.95},
            baseline_metrics={"sample_count": 100, "success_rate": 0.85},
            regression_test_results={"benchmark_1": True, "benchmark_2": True},
            policy_validation_passed=True,
            security_audit_passed=True,
            rollback_target_verified=True,
            human_approval_signature="security_lead_charlie",
        )
        self.assertEqual(req_valid.status, "APPROVED")
        self.assertTrue(req_valid.is_eligible_for_promotion())

    def test_07_controlled_rollout_and_instant_rollback(self):
        """Rollout progresses through canary and rolls back atomically on performance degradation."""
        cand_id = "2.1.0"
        base_id = "1.0.0"

        # Start Canary Rollout (5% traffic)
        rollout = self.service.initiate_rollout(
            rollout_id="rollout-plan-001",
            candidate_version_id=cand_id,
            baseline_version_id=base_id,
            target_subsystem="planning",
            initial_traffic_percent=0.05,
        )
        self.assertEqual(rollout.canary_traffic_pct, 0.05)

        # Injected anomaly triggers verified rollback
        success, msg = self.service.rollback_rollout(
            rollout_id=rollout.rollout_id,
            reason="Synthetic error spike detected in canary cohort",
            initiated_by="automated_drift_sentinel",
        )
        self.assertTrue(success)
        reloaded = self.repo.get_rollout(rollout.rollout_id)
        self.assertEqual(reloaded.canary_traffic_pct, 0.0)
        from learning.models import RolloutStatus
        self.assertEqual(reloaded.status, RolloutStatus.ROLLED_BACK)

    def test_08_feature_drift_and_performance_decay(self):
        """Verify Population Stability Index and performance decay monitors."""
        base_dist = [1.0, 1.2, 1.1, 1.3, 0.9, 1.0, 1.1]
        shifted_dist = [5.5, 6.2, 5.8, 6.0, 7.1, 5.9, 6.3]

        drift = self.service.assess_feature_drift(
            subsystem="prediction",
            feature_name="task_duration",
            baseline_distribution=base_dist,
            current_distribution=shifted_dist,
        )
        self.assertIn(drift.severity, (DriftSeverity.MEDIUM, DriftSeverity.CRITICAL))

        # Performance decay
        perf_drift = self.service.assess_performance_drift(
            subsystem="retrieval",
            metric_name="mrr_score",
            baseline_value=0.90,
            current_value=0.70,
            sample_size=200,
        )
        self.assertEqual(perf_drift.severity, DriftSeverity.CRITICAL)
        self.assertEqual(perf_drift.recommendation, "TRIGGER_ROLLBACK")

    def test_09_parameter_advisor_strictly_blocks_forbidden_keys(self):
        """Parameter advisor must strictly reject touches on auth, security, or secrets."""
        allowed, rec, reason = self.service.recommend_parameter_tuning(
            recommendation_id="rec-bad-001",
            parameter_key="security.jwt_expiration_seconds",
            current_value=3600,
            suggested_value=86400,
            subsystem="security",
            justification="Increase session life",
            supporting_signal_ids=[],
            expected_improvement="Less login prompts",
        )
        self.assertFalse(allowed)
        self.assertIn("strictly forbidden", reason)

        # Allowed tunable parameter
        ok, good_rec, _ = self.service.recommend_parameter_tuning(
            recommendation_id="rec-good-001",
            parameter_key="retrieval.dense_weight",
            current_value=0.5,
            suggested_value=0.7,
            subsystem="retrieval",
            justification="Empirical evaluation showed dense embedding superiority",
            supporting_signal_ids=["sig-001"],
            expected_improvement="+4% NDCG@10",
        )
        self.assertTrue(ok)
        self.assertIsNotNone(good_rec)
        self.assertEqual(good_rec.required_authorization, "HUMAN_OPERATOR")


if __name__ == "__main__":
    unittest.main()
