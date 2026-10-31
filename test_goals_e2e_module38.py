"""
End-to-End Integration Scenario for Omnia Module 38:
Autonomous Goal Management, Outcome Tracking & Strategic Execution Intelligence.

Simulates complete 16-step strategic lifecycle:
1. Define intended strategic outcome.
2. Establish baseline and target measurements across multiple metric types.
3. Decompose the objective into initiatives and milestones.
4. Connect dependencies and required capabilities.
5. Allocate authorized resources.
6. Record task execution progress (simulate busywork).
7. Verify actual outcome measurements against independent evidence.
8. Evaluate goal health and trajectory.
9. Forecast target achievement via Module 32 bridge.
10. Detect off-track condition with schedule variance.
11. Generate corrective action alternatives.
12. Compare alternatives through Module 37 Decision Support.
13. Request and enforce Module 20 human approval token.
14. Record revised strategy and versioned snapshot.
15. Verify resulting outcome achievement.
16. Confirm that the system distinguishes completed tasks from achieved outcomes.
"""

import os
import tempfile
import unittest

from goals.models import (
    CorrectiveActionType,
    GoalHealthState,
    GoalLifecycleState,
    GoalPriority,
    GoalType,
    MetricType,
    VerificationTier,
)
from goals.persistence import GoalRepository
from goals.service import GoalExecutionIntelligenceOrchestrator
from persistence.migrations import apply_migrations
from strategy.models import CriterionDirection, DecisionCriterion, StrategicOptionRecord
from strategy.service import DecisionSupportOrchestrator


class TestGoalManagementModule38E2E(unittest.TestCase):
    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_db_fd)
        apply_migrations(self.temp_db_path)
        self.repo = GoalRepository(self.temp_db_path)
        self.service = GoalExecutionIntelligenceOrchestrator(self.repo)
        self.strategy_service = DecisionSupportOrchestrator(db_path=self.temp_db_path)

    def tearDown(self):
        try:
            if os.path.exists(self.temp_db_path):
                os.remove(self.temp_db_path)
        except Exception:
            pass

    def test_complete_strategic_execution_lifecycle_e2e(self):
        # 1. Define strategic objective
        goal = self.service.create_goal(
            title="Next-Gen High Throughput Ingestion Fabric",
            description="Scale Omnia telemetry pipeline to 50,000 eps with sub-15ms p99 latency.",
            purpose="Support enterprise distributed sensor streams without backpressure.",
            owner="chief_architect",
            goal_type=GoalType.STRATEGIC,
            priority=GoalPriority.CRITICAL,
            target_date="2026-12-31T00:00:00Z",
            success_criteria=[
                "Sustained throughput >= 50,000 eps",
                "P99 latency <= 15ms",
                "Zero data loss during failover",
            ],
            constraints=["Memory budget <= 16GB", "Cloud cost <= $500/mo"],
            dependencies=["infra.network.vpc_peering", "storage.nvme_provisioning"],
        )
        self.assertEqual(goal.version, 1)

        # Activate goal
        self.service.activate_goal(goal.goal_id, operator_id="executive_sponsor")

        # 2. Establish baseline & target key results (Increasing & Decreasing)
        kr_throughput = self.service.define_key_result(
            goal_id=goal.goal_id,
            metric_name="Sustained Telemetry Throughput",
            description="Events ingested per second under continuous load",
            unit="eps",
            metric_type=MetricType.INCREASING,
            baseline_value=5000.0,
            target_value=50000.0,
            required_verification_tier=VerificationTier.SYSTEM_OBSERVED,
        )

        kr_latency = self.service.define_key_result(
            goal_id=goal.goal_id,
            metric_name="P99 Ingestion Latency",
            description="99th percentile end-to-end ingestion latency",
            unit="ms",
            metric_type=MetricType.DECREASING,
            baseline_value=120.0,
            target_value=15.0,
            required_verification_tier=VerificationTier.SYSTEM_OBSERVED,
        )

        # 3. Decompose objective into initiatives and milestones
        init = self.service.decompose_initiative(
            goal_id=goal.goal_id,
            title="Zero-Copy Ring Buffer & SIMD Parser",
            scope="Rewrite serialization layer using zero-copy shared memory queues.",
            expected_outcome="5x reduction in heap allocations and 10x throughput multiplier.",
            owner="systems_eng",
            required_capabilities=["rust.compiler", "linux.hugepages"],
            task_graph_id="task-graph-simd-001",
        )

        ms1 = self.service.register_milestone(
            initiative_id=init.initiative_id,
            title="SIMD Protobuf Decoder",
            description="Implement AVX-512 parser benchmark",
            target_date="2026-11-15T00:00:00Z",
        )
        ms2 = self.service.register_milestone(
            initiative_id=init.initiative_id,
            title="Lock-Free Ring Buffer Queue",
            description="Stress test ring buffer with 64 concurrent writers",
            target_date="2026-11-30T00:00:00Z",
        )

        # 4 & 5. Simulate task execution progress without verified outcome (Activity != Achievement)
        self.service.complete_milestone(ms1.milestone_id)
        self.service.complete_milestone(ms2.milestone_id)

        # Worker self-reports completion of tasks
        self.service.record_reported_progress(kr_throughput.key_result_id, 50000.0, "worker_agent_simd")
        self.service.record_reported_progress(kr_latency.key_result_id, 14.0, "worker_agent_simd")

        # 6. Assess progress: 100% tasks completed, BUT verified outcome is still 0%
        prog_busy = self.service.assess_progress(goal.goal_id)
        self.assertAlmostEqual(prog_busy.reported_task_progress, 1.0)
        self.assertAlmostEqual(prog_busy.verified_outcome_progress, 0.0)
        self.assertGreater(prog_busy.activity_to_outcome_variance, 0.90)

        # 7. Health Monitor catches activity-to-outcome divergence
        health_busy = self.service.evaluate_health(goal.goal_id)
        self.assertEqual(health_busy.health_state, GoalHealthState.AT_RISK)

        # 8. Forecast target achievement using Module 32 integration
        forecast = self.service.forecasting.forecast_goal_outcome(goal.goal_id)
        self.assertIn("completion_probability", forecast)
        self.assertEqual(forecast["forecaster_provenance"], "Module 32 Predictive Trend & Risk Forecaster")

        # 9. Off-Track Detection: Introduce schedule delay and evaluate corrective alternatives
        self.service.progress.assess_progress(goal.goal_id, schedule_variance_days=28.0)
        health_offtrack = self.service.evaluate_health(goal.goal_id)
        self.assertEqual(health_offtrack.health_state, GoalHealthState.OFF_TRACK)

        # 10. Generate Corrective Action Proposals
        proposals = self.service.generate_corrective_proposals(goal.goal_id)
        self.assertGreaterEqual(len(proposals), 2)

        deadline_proposal = next(p for p in proposals if p.action_type == CorrectiveActionType.REVISE_DEADLINE)

        # 11 & 12. Evaluate corrective alternatives through Module 37 Decision Support Engine
        case = self.strategy_service.create_decision_case(
            title=f"Remediation Strategy: {goal.title}",
            description="Evaluate options to recover off-track high throughput ingestion goal.",
            owner_id="chief_architect",
            category="INFRASTRUCTURE",
            desired_outcomes=["Restore goal schedule alignment", "Preserve 50k eps target"],
            constraints=["Budget cap $500/mo"],
            available_resources=["2 senior engineers", "Cloud GPU bench"],
        )

        opt_baseline = self.strategy_service.register_strategic_option(
            case_id=case.case_id,
            title="Status Quo (Maintain Unchanged Schedule)",
            description="Make no changes; accept risk of missing launch deadline.",
            is_baseline=True,
            expected_outcome="Probable failure to deliver on time.",
            estimated_cost=0.0,
            implementation_complexity="LOW",
            reversibility_score=1.0,
            time_horizon_days=60,
            origin="GOAL_ENGINE_M38",
        )

        opt_extend = self.strategy_service.register_strategic_option(
            case_id=case.case_id,
            title="Extend Milestone & Goal Target Date by 30 Days",
            description="Formally revise timeline to accommodate zero-copy verification benchmarks.",
            is_baseline=False,
            expected_outcome="Realistic delivery with fully verified outcome.",
            estimated_cost=2000.0,
            implementation_complexity="MEDIUM",
            reversibility_score=0.9,
            time_horizon_days=90,
            origin="GOAL_ENGINE_M38",
        )

        crit_prob = self.strategy_service.register_decision_criterion(
            case_id=case.case_id,
            name="Success Probability",
            weight=0.60,
            direction=CriterionDirection.MAXIMIZE,
        )
        crit_cost = self.strategy_service.register_decision_criterion(
            case_id=case.case_id,
            name="Cost Impact",
            weight=0.40,
            direction=CriterionDirection.MINIMIZE,
        )

        eval_matrix = {
            opt_baseline.option_id: {crit_prob.criterion_id: 0.20, crit_cost.criterion_id: 0.0},
            opt_extend.option_id: {crit_prob.criterion_id: 0.95, crit_cost.criterion_id: 2000.0},
        }
        risk_matrix = {
            opt_baseline.option_id: {
                "probability_of_failure": 0.80,
                "severity_of_failure": 0.90,
                "financial_exposure": 50000.0,
                "operational_disruption": "HIGH",
                "security_risk": "LOW",
                "opportunity_cost_notes": "Customer loss due to missed deadline",
                "mitigation_strategy": "None",
            },
            opt_extend.option_id: {
                "probability_of_failure": 0.05,
                "severity_of_failure": 0.20,
                "financial_exposure": 2000.0,
                "operational_disruption": "LOW",
                "security_risk": "LOW",
                "opportunity_cost_notes": "Slight feature delay",
                "mitigation_strategy": "Overtime QA verification",
            },
        }
        analysis_res = self.strategy_service.run_strategic_analysis(
            case.case_id, eval_matrix, risk_matrix
        )
        self.assertEqual(analysis_res["recommendation"]["recommended_option_id"], opt_extend.option_id)

        # 13. Enforce Module 20 human approval token gate for corrective approval
        with self.assertRaises(PermissionError):
            self.service.approve_corrective_action(deadline_proposal.proposal_id, "chief_architect", "")

        app_token = "token-m20-human-authorized-99b04739"
        approved_action = self.service.approve_corrective_action(
            deadline_proposal.proposal_id, "chief_architect", app_token
        )
        self.assertEqual(approved_action.status, "APPROVED")

        # 14. Record revised strategy and versioned snapshot (Version 2)
        revised_goal = self.service.registry.revise_goal(
            goal_id=goal.goal_id,
            author="chief_architect",
            rationale="Approved 30-day schedule extension per Module 37 MCDA trade-off recommendation.",
            new_target_date="2027-01-31T00:00:00Z",
            approval_token=app_token,
        )
        self.assertEqual(revised_goal.version, 2)
        self.assertEqual(revised_goal.target_date, "2027-01-31T00:00:00Z")

        # 15. Submit independent telemetry evidence to verify actual outcomes
        self.service.verify_outcome_metric(
            key_result_id=kr_throughput.key_result_id,
            observed_value=52400.0,
            verification_tier=VerificationTier.SYSTEM_OBSERVED,
            data_source="distributed_load_test_runner",
            evidence_summary="Verified sustained 52.4k eps over 4-hour soak test",
            evidence_payload={"throughput_eps": 52400, "duration_seconds": 14400, "drop_rate": 0.0},
            verified_by="qa_load_bench",
        )

        self.service.verify_outcome_metric(
            key_result_id=kr_latency.key_result_id,
            observed_value=12.8,
            verification_tier=VerificationTier.SYSTEM_OBSERVED,
            data_source="distributed_load_test_runner",
            evidence_summary="Verified p99 latency at 12.8ms across 200M events",
            evidence_payload={"p99_latency_ms": 12.8, "p95_latency_ms": 8.4, "p50_latency_ms": 3.1},
            verified_by="qa_load_bench",
        )

        # 16. Final progress and health verification: Outcome achievement confirmed!
        final_prog = self.service.assess_progress(goal.goal_id, schedule_variance_days=0.0)
        self.assertAlmostEqual(final_prog.verified_outcome_progress, 1.0)
        self.assertAlmostEqual(final_prog.activity_to_outcome_variance, 0.0)

        final_health = self.service.evaluate_health(goal.goal_id)
        self.assertEqual(final_health.health_state, GoalHealthState.COMPLETED)

        # Generate final comprehensive briefing report
        report = self.service.reporting.generate_goal_report(goal.goal_id)
        self.assertEqual(report["health_state"], "COMPLETED")
        self.assertTrue(all(kr["is_satisfied"] for kr in report["key_results"]))


if __name__ == "__main__":
    unittest.main()
