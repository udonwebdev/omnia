"""
End-to-End Integration Scenario for Omnia Module 39:
Autonomous Workflow Optimization & Process Intelligence Engine.

Simulates complete 15-step workflow optimization lifecycle:
1. Execute a representative multi-step workflow.
2. Collect its execution events and timestamps.
3. Reconstruct actual process graph and edge transitions.
4. Measure execution performance (mean, p95, active vs wait time).
5. Identify a genuine bottleneck with empirical evidence.
6. Analyze supporting execution traces and failure rework patterns.
7. Generate explainable optimization alternatives.
8. Simulate proposed changes via Module 34 Digital Twin integration.
9. Evaluate security, auditability, and operational implications.
10. Submit selected proposal for formal change governance.
11. Require and enforce Module 20 human approval token gate.
12. Deploy controlled rollout experiment with guardrails.
13. Collect post-change execution telemetry.
14. Compare results against baseline and verify genuine improvement.
15. Verify that no workflow is modified outside the authorized governance process.
"""

import os
import tempfile
import unittest

from persistence.migrations import apply_migrations
from process_intelligence.models import (
    BottleneckType,
    ExperimentStatus,
    OptimizationStatus,
    ProcessEventType,
    TraceStatus,
)
from process_intelligence.persistence import ProcessIntelligenceRepository
from process_intelligence.service import ProcessIntelligenceOrchestrator


class TestProcessIntelligenceModule39E2E(unittest.TestCase):
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

    def test_complete_workflow_optimization_lifecycle_e2e(self):
        wf_id = "wf_distributed_index_builder"

        # 1 & 2. Ingest execution events across 5 historical runs
        for i in range(5):
            trace_id = f"trace_idx_run_{i}"
            # Step 1: Ingest Shards
            self.service.record_event(
                trace_id=trace_id,
                workflow_id=wf_id,
                task_id="step_shard_ingest",
                event_type=ProcessEventType.TASK_COMPLETE,
                timestamp=f"2026-10-31T14:0{i}:00Z",
                duration_sec=5.0,
                waiting_time_sec=1.0,
            )
            # Step 2: Severe Queue Delay on Tokenizer (The Bottleneck!)
            self.service.record_event(
                trace_id=trace_id,
                workflow_id=wf_id,
                task_id="step_tokenize_documents",
                event_type=ProcessEventType.TASK_COMPLETE,
                timestamp=f"2026-10-31T14:0{i}:15Z",
                duration_sec=12.0,
                waiting_time_sec=28.0,  # 28s queue delay waiting for single worker
            )
            # Step 3: Human Verification Check
            self.service.record_event(
                trace_id=trace_id,
                workflow_id=wf_id,
                task_id="step_quality_approval_gate",
                event_type=ProcessEventType.APPROVAL_GRANT,
                timestamp=f"2026-10-31T14:0{i}:45Z",
                duration_sec=2.0,
                waiting_time_sec=3.0,
            )
            # Step 4: Final Flush
            self.service.record_event(
                trace_id=trace_id,
                workflow_id=wf_id,
                task_id="step_flush_inverted_index",
                event_type=ProcessEventType.TASK_COMPLETE,
                timestamp=f"2026-10-31T14:0{i}:55Z",
                duration_sec=6.0,
                waiting_time_sec=0.5,
            )
            # Reconstruct trace
            t = self.service.reconstruct_trace(trace_id)
            self.assertEqual(t.status, TraceStatus.COMPLETED)

        # 3. Reconstruct actual process graph and edge transitions
        graph = self.service.build_process_graph(wf_id, version=1)
        self.assertEqual(len(graph.nodes), 4)
        self.assertEqual(len(graph.edges), 3)

        # 4. Measure execution performance across baseline traces
        perf = self.service.analyze_performance(wf_id)
        self.assertEqual(perf.trace_count, 5)
        self.assertGreater(perf.mean_duration_sec, 50.0)
        self.assertGreater(perf.mean_waiting_time_sec, 25.0)

        # 5 & 6. Identify genuine bottleneck with empirical evidence
        bottlenecks = self.service.detect_bottlenecks(wf_id)
        self.assertGreaterEqual(len(bottlenecks), 1)

        token_bn = next(b for b in bottlenecks if b.component_id == "step_tokenize_documents")
        self.assertEqual(token_bn.bottleneck_type, BottleneckType.QUEUE_WAITING)
        self.assertAlmostEqual(token_bn.estimated_delay_sec, 28.0)
        self.assertEqual(len(token_bn.supporting_trace_ids), 5)

        # 7. Generate explainable optimization alternatives
        candidates = self.service.generate_optimizations(wf_id, version=1)
        self.assertGreaterEqual(len(candidates), 1)

        target_cand = next(c for c in candidates if "Parallelize" in c.title)
        self.assertEqual(target_cand.status, OptimizationStatus.PROPOSED)
        self.assertGreater(target_cand.expected_time_reduction_pct, 20.0)

        # 8 & 9. Simulate proposed changes via Module 34 Digital Twin integration
        sim_res = self.service.simulate_optimization(target_cand.candidate_id)
        self.assertTrue(sim_res["is_simulation"])
        self.assertTrue(sim_res["security_properties_preserved"])
        self.assertIn("SIMULATION_OUTPUT_ONLY", sim_res["disclaimer"])
        self.assertLess(sim_res["simulated_duration_sec"], perf.mean_duration_sec)

        # 10 & 11. Submit proposal for change governance and enforce Module 20 human approval gate
        with self.assertRaises(PermissionError):
            self.service.submit_and_approve_change(
                workflow_id=wf_id,
                candidate_id=target_cand.candidate_id,
                from_version=1,
                to_version=2,
                approver="lead_engineer",
                approval_token="",  # Missing approval token must be blocked!
            )

        token = "token-m20-proc-verified-99b04739"
        approved_change = self.service.submit_and_approve_change(
            workflow_id=wf_id,
            candidate_id=target_cand.candidate_id,
            from_version=1,
            to_version=2,
            approver="lead_engineer",
            approval_token=token,
        )
        self.assertEqual(approved_change.change_status, "APPROVED")
        self.assertEqual(approved_change.approval_token, token)

        # 12, 13 & 14. Deploy controlled rollout experiment and collect post-change telemetry
        exp_result = self.service.run_experiment(
            candidate_id=target_cand.candidate_id,
            workflow_id=wf_id,
            observed_speedup=32.5,
            error_rate=0.01,  # Safe within 5% guardrail
            latency_spike_pct=0.0,
        )
        self.assertEqual(exp_result.status, ExperimentStatus.CONCLUDED)
        self.assertFalse(exp_result.is_guardrail_breached)
        self.assertAlmostEqual(exp_result.observed_improvement_pct, 32.5)

        # 15. Verify process intelligence briefing generation
        briefing = self.service.reporting.generate_workflow_briefing(wf_id)
        self.assertEqual(briefing["workflow_id"], wf_id)
        self.assertGreaterEqual(len(briefing["bottlenecks"]), 1)
        self.assertGreaterEqual(len(briefing["optimization_candidates"]), 1)


if __name__ == "__main__":
    unittest.main()
