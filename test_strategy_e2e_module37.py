"""
End-to-End integration test for Omnia Module 37: Decision Support, Strategic Options & Trade-off Analysis Engine.
"""

import os
import unittest
import tempfile
import shutil

from strategy.models import (
    CriterionDirection,
    RecommendationOutcome,
    DecisionLifecycleState,
)
from strategy.service import DecisionSupportOrchestrator


class TestStrategyModule37E2E(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_strategy_e2e.db")
        self.service = DecisionSupportOrchestrator(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_complete_strategic_decision_support_lifecycle(self):
        """
        Full end-to-end strategic decision support loop:
        1. Register complex strategic decision case (e.g. Distributed Database Engine Selection)
        2. Automatically establish status-quo baseline alternative
        3. Register multi-source candidate alternatives (Research findings, Forecast, Simulation)
        4. Configure weighted multi-criteria (Cost, Latency, High Availability, Reversibility)
        5. Run strategic analysis (MCDA, Risk matrix, Sensitivity check, Value of Information)
        6. Verify explainable recommendation generation
        7. Enforce Module 20 human approval boundary
        8. Record authoritative human decision
        9. Monitor operational outcome & trigger versioned reassessment on assumption failure
        """
        # Step 1: Initialize Decision Case
        case = self.service.create_decision_case(
            title="Cluster Storage Layer Strategic Migration",
            description="Select primary storage engine to support 100k IOPS with zero data loss",
            owner_id="chief_architect",
            category="STORAGE_INFRASTRUCTURE",
            risk_tolerance="HIGH",
        )
        self.assertIsNotNone(case.case_id)
        self.assertEqual(case.state, DecisionLifecycleState.DRAFT)

        # Step 2: Register Candidate Options (including Baseline status-quo)
        opt_spanner = self.service.register_strategic_option(
            case_id=case.case_id,
            title="Adopt Cloud Spanner Distributed Architecture",
            description="Globally consistent relational storage with synchronous cross-region replication",
            is_baseline=False,
            expected_outcome="Sub-15ms global read latency with 99.999% availability SLA",
            estimated_cost=36000.0,
            implementation_complexity="MEDIUM",
            reversibility_score=0.85,
            time_horizon_days=60,
            benefits=["Global consistency", "Zero manual sharding", "Automated failover"],
            disadvantages=["Higher baseline monthly cost"],
            critical_assumptions=["Network transit latency stays under 40ms"],
            origin="RESEARCH_MODULE_35",
        )

        opt_self_hosted = self.service.register_strategic_option(
            case_id=case.case_id,
            title="Self-Hosted Sharded PostgreSQL on Kubernetes",
            description="Deploy Patroni-managed PG cluster on local NVMe storage nodes",
            is_baseline=False,
            expected_outcome="Maximum raw write IOPS at lowest infrastructure cost",
            estimated_cost=18000.0,
            implementation_complexity="HIGH",
            reversibility_score=0.60,
            time_horizon_days=90,
            benefits=["Lowest direct hardware cost", "Complete local data sovereignty"],
            disadvantages=["Operational burden", "Manual cross-region disaster recovery"],
            critical_assumptions=["Local SRE team can manage 24/7 on-call failover"],
            origin="HUMAN_PROPOSAL",
        )

        # Step 3: Register Decision Criteria
        crit_cost = self.service.register_decision_criterion(
            case_id=case.case_id,
            name="Financial Cost",
            weight=0.25,
            direction=CriterionDirection.MINIMIZE,
        )
        crit_latency = self.service.register_decision_criterion(
            case_id=case.case_id,
            name="P99 Latency (ms)",
            weight=0.35,
            direction=CriterionDirection.MINIMIZE,
            is_mandatory=True,
            minimum_threshold=50.0,  # Must be under 50ms
        )
        crit_availability = self.service.register_decision_criterion(
            case_id=case.case_id,
            name="Availability Nines",
            weight=0.25,
            direction=CriterionDirection.MAXIMIZE,
        )
        crit_reversibility = self.service.register_decision_criterion(
            case_id=case.case_id,
            name="Architectural Reversibility",
            weight=0.15,
            direction=CriterionDirection.MAXIMIZE,
        )

        # Step 4: Execute Strategic Analysis
        # Retrieve baseline ID
        baseline_opt = self.service.options.ensure_baseline_option(case.case_id)

        metrics_matrix = {
            opt_spanner.option_id: {
                crit_cost.criterion_id: 36000.0,
                crit_latency.criterion_id: 12.0,
                crit_availability.criterion_id: 5.0,  # 5 nines
                crit_reversibility.criterion_id: 8.5,
            },
            opt_self_hosted.option_id: {
                crit_cost.criterion_id: 18000.0,
                crit_latency.criterion_id: 28.0,
                crit_availability.criterion_id: 3.5,  # 3.5 nines
                crit_reversibility.criterion_id: 6.0,
            },
            baseline_opt.option_id: {
                crit_cost.criterion_id: 5000.0,
                crit_latency.criterion_id: 85.0,  # Violates mandatory 50ms threshold!
                crit_availability.criterion_id: 3.0,
                crit_reversibility.criterion_id: 10.0,
            }
        }

        risk_matrix = {
            opt_spanner.option_id: {
                "prob": 0.1, "sev": 0.3, "exposure": 10000.0, "disruption": "MINOR", "mitigation": "Multi-region failover",
            },
            opt_self_hosted.option_id: {
                "prob": 0.35, "sev": 0.7, "exposure": 50000.0, "disruption": "MAJOR", "mitigation": "Automated Patroni failover",
            },
            baseline_opt.option_id: {
                "prob": 0.6, "sev": 0.9, "exposure": 100000.0, "disruption": "CATASTROPHIC",
            }
        }

        analysis_res = self.service.run_strategic_analysis(
            case_id=case.case_id,
            raw_metrics_matrix=metrics_matrix,
            risk_inputs_matrix=risk_matrix,
            known_information_gaps=["Cloud provider cross-region egress price volatility"],
            has_active_contradictions=False,
        )
        self.assertTrue(analysis_res["success"])

        # Step 5: Verify Recommendation & Sensitivity
        rec = analysis_res["recommendation"]
        self.assertEqual(rec["outcome"], RecommendationOutcome.RECOMMENDED.value)
        self.assertEqual(rec["recommended_option_id"], opt_spanner.option_id)
        self.assertIn("Cloud Spanner", rec["primary_justification"])

        # Baseline must violate mandatory latency constraint (>50ms)
        assessments = analysis_res["assessments"]
        base_ass = next(a for a in assessments if a["option_id"] == baseline_opt.option_id)
        self.assertTrue(base_ass["violates_mandatory_constraint"])

        # Step 6 & 7: Human Authority Gate & Final Decision
        # Missing token raises PermissionError on high-risk case
        with self.assertRaises(PermissionError):
            self.service.record_human_decision(
                case_id=case.case_id,
                selected_option_id=opt_spanner.option_id,
                decided_by="chief_architect",
                approval_token=None,
            )

        # Valid approval token authorizes final decision
        approval_token = "approval-token-exec-board-99"
        final_case = self.service.record_human_decision(
            case_id=case.case_id,
            selected_option_id=opt_spanner.option_id,
            decided_by="chief_architect",
            approval_token=approval_token,
        )
        self.assertEqual(final_case.state, DecisionLifecycleState.DECIDED)
        self.assertEqual(final_case.selected_option_id, opt_spanner.option_id)
        self.assertEqual(final_case.approval_token, approval_token)

        # Step 8: Post-Decision Outcome Monitoring & Reassessment Trigger
        # Record reality: Cloud provider hiked transit latency >40ms (assumption invalid)
        mon = self.service.record_outcome_monitoring(
            case_id=case.case_id,
            actual_cost=38000.0,
            expected_cost=36000.0,  # ~5.5% variance
            assumptions_status={"Network transit latency stays under 40ms": False},
        )
        self.assertTrue(mon.reassessment_triggered)
        self.assertIn("Invalidated assumptions", mon.reassessment_reason)

        # Verify case automatically transitioned to REOPENED with version bump
        reopened_case = self.service.repo.get_case(case.case_id)
        self.assertEqual(reopened_case.state, DecisionLifecycleState.REOPENED)
        self.assertEqual(reopened_case.version, 2)


if __name__ == "__main__":
    unittest.main()
