"""
Unit Tests for Omnia Module 38: Autonomous Goal Management, Outcome Tracking & Strategic Execution Intelligence.
"""

import os
import tempfile
import unittest

from goals.models import (
    AlignmentStatus,
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


class TestGoalManagementModule38(unittest.TestCase):
    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_db_fd)
        apply_migrations(self.temp_db_path)
        self.repo = GoalRepository(self.temp_db_path)
        self.service = GoalExecutionIntelligenceOrchestrator(self.repo)

    def tearDown(self):
        try:
            if os.path.exists(self.temp_db_path):
                os.remove(self.temp_db_path)
        except Exception:
            pass

    def test_goal_creation_and_versioning(self):
        """Verify goal registration, activation, revision snapshotting, and audit logging."""
        goal = self.service.create_goal(
            title="Launch Omnia Resilient Node",
            description="Achieve 99.99% autonomous uptime across clusters.",
            purpose="High availability infrastructure",
            owner="infra_ops",
            goal_type=GoalType.OPERATIONAL,
            priority=GoalPriority.HIGH,
            target_date="2026-12-31T00:00:00Z",
            success_criteria=["Zero unrecovered failovers", "Uptime >= 99.99%"],
        )
        self.assertEqual(goal.state, GoalLifecycleState.DRAFT)
        self.assertEqual(goal.version, 1)

        # Activate
        active_goal = self.service.activate_goal(goal.goal_id, operator_id="admin_1")
        self.assertEqual(active_goal.state, GoalLifecycleState.ACTIVE)

        # Revise target date & criteria
        revised = self.service.registry.revise_goal(
            goal_id=goal.goal_id,
            author="lead_architect",
            rationale="Tighten recovery SLA based on cluster benchmark.",
            new_target_date="2026-11-30T00:00:00Z",
            new_success_criteria=["Zero unrecovered failovers", "Uptime >= 99.999%"],
        )
        self.assertEqual(revised.version, 2)
        self.assertEqual(revised.target_date, "2026-11-30T00:00:00Z")

        # Verify historical snapshot preserved
        versions = self.repo.get_goal_versions(goal.goal_id)
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0].version, 1)
        self.assertEqual(versions[0].target_date, "2026-12-31T00:00:00Z")

        # Verify audit trail
        trail = self.service.audit.get_goal_provenance(goal.goal_id)
        self.assertGreaterEqual(len(trail), 3)

    def test_metric_direction_and_progress_calculation(self):
        """Verify increasing vs decreasing vs threshold progress normalization."""
        goal = self.service.create_goal(
            title="Performance Optimization",
            description="Optimize system metrics",
            purpose="Performance",
            owner="perf_team",
        )

        # Increasing metric: Throughput from 100 to 500 req/s
        kr_inc = self.service.define_key_result(
            goal_id=goal.goal_id,
            metric_name="Throughput",
            description="API requests per second",
            unit="req/s",
            metric_type=MetricType.INCREASING,
            baseline_value=100.0,
            target_value=500.0,
        )
        # Current reported 300 -> (300 - 100) / 400 = 0.50
        ratio_inc = self.service.outcomes.calculate_progress_ratio(kr_inc, 300.0)
        self.assertAlmostEqual(ratio_inc, 0.50)

        # Decreasing metric: Latency from 200ms down to 50ms
        kr_dec = self.service.define_key_result(
            goal_id=goal.goal_id,
            metric_name="P99 Latency",
            description="P99 response time in milliseconds",
            unit="ms",
            metric_type=MetricType.DECREASING,
            baseline_value=200.0,
            target_value=50.0,
        )
        # Current reported 80ms -> (200 - 80) / (200 - 50) = 120 / 150 = 0.80
        ratio_dec = self.service.outcomes.calculate_progress_ratio(kr_dec, 80.0)
        self.assertAlmostEqual(ratio_dec, 0.80)

        # Binary metric
        kr_bin = self.service.define_key_result(
            goal_id=goal.goal_id,
            metric_name="SOC2 Compliance Audit",
            description="Pass external audit",
            unit="bool",
            metric_type=MetricType.BINARY,
            baseline_value=0.0,
            target_value=1.0,
        )
        self.assertEqual(self.service.outcomes.calculate_progress_ratio(kr_bin, 0.0), 0.0)
        self.assertEqual(self.service.outcomes.calculate_progress_ratio(kr_bin, 1.0), 1.0)

    def test_activity_vs_outcome_divergence_and_verification_tiers(self):
        """
        Verify that 100% completed tasks do NOT mark an objective complete
        if verified key results remain unsatisfied.
        """
        goal = self.service.create_goal(
            title="Database Latency Reduction",
            description="Slash query latency below 20ms",
            purpose="Database efficiency",
            owner="db_lead",
        )
        self.service.activate_goal(goal.goal_id, "admin")

        kr = self.service.define_key_result(
            goal_id=goal.goal_id,
            metric_name="Query Latency",
            description="Mean query time",
            unit="ms",
            metric_type=MetricType.DECREASING,
            baseline_value=100.0,
            target_value=20.0,
            required_verification_tier=VerificationTier.SYSTEM_OBSERVED,
        )

        init = self.service.decompose_initiative(
            goal_id=goal.goal_id,
            title="Query Index Refactoring",
            scope="Add covering indexes",
            expected_outcome="Reduce index scans",
            owner="db_lead",
        )

        ms = self.service.register_milestone(
            initiative_id=init.initiative_id,
            title="Index DDL migration script",
            description="Deploy schema migration",
            target_date="2026-11-01T00:00:00Z",
        )

        # Worker reports 100% milestone complete
        self.service.complete_milestone(ms.milestone_id)

        # Worker also self-reports metric at 20ms (SELF_REPORTED tier)
        self.service.record_reported_progress(kr.key_result_id, 20.0, reporter="worker_agent")

        # Progress check: task progress is 100%, BUT verified outcome is still 0% (baseline 100ms)
        prog = self.service.assess_progress(goal.goal_id)
        self.assertAlmostEqual(prog.reported_task_progress, 1.0)
        self.assertAlmostEqual(prog.verified_outcome_progress, 0.0)
        self.assertGreater(prog.activity_to_outcome_variance, 0.90)  # Deceptive busywork caught!

        # Health should detect high risk due to divergence
        health = self.service.evaluate_health(goal.goal_id)
        self.assertEqual(health.health_state, GoalHealthState.AT_RISK)

        # Now submit verified evidence (SYSTEM_OBSERVED tier with telemetry payload)
        self.service.verify_outcome_metric(
            key_result_id=kr.key_result_id,
            observed_value=18.5,
            verification_tier=VerificationTier.SYSTEM_OBSERVED,
            data_source="prometheus_query_engine",
            evidence_summary="Observed mean query duration over 100,000 queries",
            evidence_payload={"sample_count": 100000, "mean_latency_ms": 18.5},
            verified_by="telemetry_verifier",
        )

        # Re-assess
        prog2 = self.service.assess_progress(goal.goal_id)
        self.assertAlmostEqual(prog2.verified_outcome_progress, 1.0)
        health2 = self.service.evaluate_health(goal.goal_id)
        self.assertEqual(health2.health_state, GoalHealthState.COMPLETED)

    def test_strategic_alignment_and_contradiction_detection(self):
        """Verify detection of schedule contradictions and unmeasured objectives."""
        parent_goal = self.service.create_goal(
            title="Platform Q4 Release",
            description="Launch v2.0",
            purpose="Platform launch",
            owner="vp_eng",
            target_date="2026-11-15T00:00:00Z",
        )

        # Child goal with contradictory schedule (target date later than parent)
        child_goal = self.service.create_goal(
            title="Complex Subsystem Migration",
            description="Migrate legacy storage",
            purpose="Storage migration",
            owner="storage_eng",
            parent_goal_id=parent_goal.goal_id,
            target_date="2026-12-01T00:00:00Z",  # Contradicts parent deadline
        )

        alignment = self.service.alignment.evaluate_goal_alignment(child_goal.goal_id)
        schedule_issues = [iss for iss in alignment["issues"] if "Schedule contradiction" in iss]
        self.assertGreaterEqual(len(schedule_issues), 1)
        self.assertEqual(alignment["status"], AlignmentStatus.CONFLICTING.value)

    def test_corrective_action_proposal_and_approval_gate(self):
        """Verify that corrective actions formulate explainable proposals and require Module 20 token."""
        goal = self.service.create_goal(
            title="Scale Data Ingestion",
            description="Scale to 10k eps",
            purpose="Data pipeline",
            owner="data_team",
        )
        self.service.activate_goal(goal.goal_id, "admin")

        self.service.define_key_result(
            goal_id=goal.goal_id,
            metric_name="Ingestion Rate",
            description="Events per sec",
            unit="eps",
            metric_type=MetricType.INCREASING,
            baseline_value=1000.0,
            target_value=10000.0,
        )

        # Force schedule delay
        self.service.progress.assess_progress(goal.goal_id, schedule_variance_days=25.0)
        self.service.evaluate_health(goal.goal_id)

        proposals = self.service.generate_corrective_proposals(goal.goal_id)
        self.assertGreaterEqual(len(proposals), 1)

        deadline_prop = next(p for p in proposals if p.action_type == CorrectiveActionType.REVISE_DEADLINE)
        self.assertTrue(deadline_prop.requires_human_approval)

        # Attempt approval without token -> Must raise PermissionError
        with self.assertRaises(PermissionError):
            self.service.approve_corrective_action(deadline_prop.proposal_id, "operator", "")

        # Approve with valid approval token
        approved = self.service.approve_corrective_action(
            deadline_prop.proposal_id, "operator", "token-m20-verified-99b04739"
        )
        self.assertEqual(approved.status, "APPROVED")
        self.assertEqual(approved.approval_token, "token-m20-verified-99b04739")

    def test_reporting_and_portfolio_rollups(self):
        """Verify single goal and portfolio-level report synthesis."""
        goal = self.service.create_goal(
            title="Security Posture Hardening",
            description="Zero critical vulnerabilities",
            purpose="Cyber defense",
            owner="ciso",
        )
        self.service.activate_goal(goal.goal_id, "ciso")
        self.service.define_key_result(
            goal_id=goal.goal_id,
            metric_name="Critical CVEs",
            description="Unresolved CVE count",
            unit="count",
            metric_type=MetricType.DECREASING,
            baseline_value=12.0,
            target_value=0.0,
        )

        goal_report = self.service.reporting.generate_goal_report(goal.goal_id)
        self.assertEqual(goal_report["goal_id"], goal.goal_id)
        self.assertEqual(len(goal_report["key_results"]), 1)

        portfolio_report = self.service.reporting.generate_portfolio_report()
        self.assertGreaterEqual(portfolio_report["active_goals_count"], 1)


if __name__ == "__main__":
    unittest.main()
