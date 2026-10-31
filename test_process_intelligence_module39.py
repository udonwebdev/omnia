"""
Unit Tests for Omnia Module 39: Autonomous Workflow Optimization & Process Intelligence Engine.
"""

import os
import tempfile
import unittest

from persistence.migrations import apply_migrations
from process_intelligence.models import (
    BottleneckType,
    DeviationType,
    ExperimentStatus,
    OptimizationStatus,
    OptimizationType,
    ProcessEventType,
    TraceStatus,
)
from process_intelligence.persistence import ProcessIntelligenceRepository
from process_intelligence.service import ProcessIntelligenceOrchestrator


class TestProcessIntelligenceModule39(unittest.TestCase):
    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_db_fd)
        apply_migrations(self.temp_db_path)
        self.repo = ProcessIntelligenceRepository(self.temp_db_path)
        self.service = ProcessIntelligenceOrchestrator(self.repo)

    def tearDown(self):
        try:
            if os.path.exists(self.temp_db_path):
                os.remove(self.temp_db_path)
        except Exception:
            pass

    def test_trace_reconstruction_and_active_wait_split(self):
        """Verify out-of-order event ingestion, chronological reconstruction, and duration splits."""
        wf_id = "wf_payment_pipeline"
        trace_id = "trace_001"

        # Ingest events out of chronological order
        self.service.record_event(
            trace_id=trace_id,
            workflow_id=wf_id,
            task_id="step_2_fraud_check",
            event_type=ProcessEventType.TASK_COMPLETE,
            timestamp="2026-10-31T20:00:15Z",
            duration_sec=3.5,
            waiting_time_sec=1.5,
        )
        self.service.record_event(
            trace_id=trace_id,
            workflow_id=wf_id,
            task_id="step_1_validate_card",
            event_type=ProcessEventType.TASK_START,
            timestamp="2026-10-31T20:00:00Z",
            duration_sec=2.0,
            waiting_time_sec=0.5,
        )
        self.service.record_event(
            trace_id=trace_id,
            workflow_id=wf_id,
            task_id="step_3_settle_ledger",
            event_type=ProcessEventType.TASK_COMPLETE,
            timestamp="2026-10-31T20:00:30Z",
            duration_sec=4.0,
            waiting_time_sec=2.0,
        )

        trace = self.service.reconstruct_trace(trace_id)
        self.assertEqual(trace.status, TraceStatus.COMPLETED)
        self.assertTrue(trace.is_complete)
        self.assertEqual(trace.events_count, 3)
        self.assertAlmostEqual(trace.total_active_sec, 9.5)   # 3.5 + 2.0 + 4.0
        self.assertAlmostEqual(trace.total_waiting_sec, 4.0)  # 1.5 + 0.5 + 2.0
        self.assertAlmostEqual(trace.total_duration_sec, 13.5)

    def test_process_graph_construction_and_path_aggregation(self):
        """Verify graph node aggregation, edge transitions, and common path extraction."""
        wf_id = "wf_order_fulfillment"

        # Trace 1: A -> B -> C
        self.service.record_event("tr_1", wf_id, "inventory_check", ProcessEventType.TASK_COMPLETE, "2026-10-31T10:00:00Z", duration_sec=1.0)
        self.service.record_event("tr_1", wf_id, "payment_charge", ProcessEventType.TASK_COMPLETE, "2026-10-31T10:00:05Z", duration_sec=2.0)
        self.service.record_event("tr_1", wf_id, "dispatch_courier", ProcessEventType.TASK_COMPLETE, "2026-10-31T10:00:10Z", duration_sec=3.0)
        self.service.reconstruct_trace("tr_1")

        # Trace 2: A -> B -> C
        self.service.record_event("tr_2", wf_id, "inventory_check", ProcessEventType.TASK_COMPLETE, "2026-10-31T10:05:00Z", duration_sec=1.2)
        self.service.record_event("tr_2", wf_id, "payment_charge", ProcessEventType.TASK_COMPLETE, "2026-10-31T10:05:05Z", duration_sec=2.1)
        self.service.record_event("tr_2", wf_id, "dispatch_courier", ProcessEventType.TASK_COMPLETE, "2026-10-31T10:05:10Z", duration_sec=2.8)
        self.service.reconstruct_trace("tr_2")

        graph = self.service.build_process_graph(wf_id, version=1)
        self.assertEqual(len(graph.nodes), 3)
        self.assertEqual(len(graph.edges), 2)  # inventory -> payment, payment -> dispatch
        self.assertEqual(graph.nodes["inventory_check"].execution_count, 2)
        self.assertEqual(len(graph.common_paths), 1)
        self.assertEqual(graph.common_paths[0], ["inventory_check", "payment_charge", "dispatch_courier"])

    def test_bottleneck_detection_for_queue_delays_and_retries(self):
        """Verify detection of queue delays and retry loops."""
        wf_id = "wf_ingest_batch"

        # Generate 4 traces with severe queue waiting on step_db_flush
        for i in range(4):
            tid = f"tr_ingest_{i}"
            self.service.record_event(tid, wf_id, "step_parse", ProcessEventType.TASK_COMPLETE, f"2026-10-31T11:0{i}:00Z", duration_sec=1.0, waiting_time_sec=0.2)
            self.service.record_event(tid, wf_id, "step_db_flush", ProcessEventType.TASK_RETRY, f"2026-10-31T11:0{i}:10Z", duration_sec=2.0, waiting_time_sec=18.0)
            self.service.record_event(tid, wf_id, "step_db_flush", ProcessEventType.TASK_COMPLETE, f"2026-10-31T11:0{i}:20Z", duration_sec=1.5, waiting_time_sec=0.1)
            self.service.reconstruct_trace(tid)

        findings = self.service.detect_bottlenecks(wf_id)
        self.assertGreaterEqual(len(findings), 1)

        queue_bns = [b for b in findings if b.bottleneck_type == BottleneckType.QUEUE_WAITING]
        self.assertEqual(len(queue_bns), 1)
        self.assertEqual(queue_bns[0].component_id, "step_db_flush")
        self.assertGreater(queue_bns[0].estimated_delay_sec, 5.0)

    def test_process_conformance_and_skipped_approval_gates(self):
        """Verify auditing detects skipped mandatory approval gates."""
        wf_id = "wf_prod_deploy"
        trace_id = "tr_deploy_unauthorized"

        self.service.record_event(trace_id, wf_id, "step_build", ProcessEventType.TASK_COMPLETE, "2026-10-31T12:00:00Z")
        self.service.record_event(trace_id, wf_id, "step_deploy_prod", ProcessEventType.TASK_COMPLETE, "2026-10-31T12:05:00Z")
        self.service.reconstruct_trace(trace_id)

        # Expected sequence requires human approval gate
        mandatory_gates = ["step_build", "step_human_approval_gate", "step_deploy_prod"]
        deviations = self.service.audit_conformance(trace_id, mandatory_gates)

        self.assertEqual(len(deviations), 1)
        self.assertEqual(deviations[0].deviation_type, DeviationType.SKIPPED_APPROVAL_GATE)

    def test_optimization_candidate_generation_and_simulation(self):
        """Verify synthesis of optimization proposals and counterfactual digital-twin simulation."""
        wf_id = "wf_data_transform"
        trace_id = "tr_data_1"

        self.service.record_event(trace_id, wf_id, "step_extract", ProcessEventType.TASK_COMPLETE, "2026-10-31T13:00:00Z", duration_sec=10.0, waiting_time_sec=22.0)
        self.service.reconstruct_trace(trace_id)
        self.service.analyze_performance(wf_id)
        self.service.detect_bottlenecks(wf_id)

        cands = self.service.generate_optimizations(wf_id, version=1)
        self.assertGreaterEqual(len(cands), 1)

        sim_res = self.service.simulate_optimization(cands[0].candidate_id)
        self.assertTrue(sim_res["is_simulation"])
        self.assertIn("simulated_speedup_pct", sim_res)
        self.assertIn("SIMULATION_OUTPUT_ONLY", sim_res["disclaimer"])

    def test_experiment_guardrails_and_approval_governance(self):
        """Verify experiment rollback on guardrail breach and Module 20 approval gate for changes."""
        wf_id = "wf_export_service"
        cand_id = "opt_cand_export"

        # Save candidate
        from process_intelligence.models import OptimizationCandidate
        cand = OptimizationCandidate(
            candidate_id=cand_id,
            workflow_id=wf_id,
            current_version=1,
            optimization_type=OptimizationType.PARALLELIZE_INDEPENDENT_TASKS,
            title="Parallel Export",
            description="Parallelize file slicing",
            current_behavior="Serial export",
            proposed_behavior="Concurrent export",
            expected_time_reduction_pct=30.0,
            expected_cost_reduction_pct=10.0,
            reversibility_score=0.9,
            validation_strategy="Shadow test",
            rollback_strategy="Revert to 1 thread",
        )
        self.repo.save_optimization_candidate(cand)

        # Run experiment with breached error rate (10% vs max 5%) -> triggers rollback
        exp_res = self.service.run_experiment(
            candidate_id=cand_id,
            workflow_id=wf_id,
            observed_speedup=25.0,
            error_rate=0.10,  # Guardrail breach!
        )
        self.assertEqual(exp_res.status, ExperimentStatus.ROLLED_BACK)
        self.assertTrue(exp_res.is_guardrail_breached)

        # Attempt to approve change without Module 20 approval token -> Must raise PermissionError
        with self.assertRaises(PermissionError):
            self.service.submit_and_approve_change(
                workflow_id=wf_id,
                candidate_id=cand_id,
                from_version=1,
                to_version=2,
                approver="admin_operator",
                approval_token="",
            )

        # Approve with valid approval token
        app = self.service.submit_and_approve_change(
            workflow_id=wf_id,
            candidate_id=cand_id,
            from_version=1,
            to_version=2,
            approver="admin_operator",
            approval_token="token-m20-human-gov-39",
        )
        self.assertEqual(app.change_status, "APPROVED")
        self.assertEqual(app.approval_token, "token-m20-human-gov-39")


if __name__ == "__main__":
    unittest.main()
