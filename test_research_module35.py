"""Unit tests for Omnia Module 35: Autonomous Research, Scientific Discovery & Hypothesis Testing Engine."""

import os
import unittest
import tempfile
import shutil

from research.models import (
    ResearchRequest,
    ResearchState,
    HypothesisRecord,
    HypothesisType,
    HypothesisState,
    ExperimentDefinition,
    ExperimentType,
    ExperimentExecutionResult,
    HypothesisTestResult,
    ResearchConclusion,
    ConclusionState,
    ReproducibilityManifest,
)
from research.persistence import ResearchRepository
from research.planner import ResearchPlanner
from research.hypotheses import HypothesisEngine
from research.experiments import ExperimentDesigner
from research.execution import InvestigationExecutor
from research.testing import HypothesisTestingEngine
from research.reproducibility import ReproducibilityManager
from research.service import ResearchOrchestrator


class TestResearchModule35(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_research.db")
        self.repo = ResearchRepository(self.db_path)
        self.planner = ResearchPlanner(self.repo)
        self.hypo_engine = HypothesisEngine(self.repo)
        self.designer = ExperimentDesigner(self.repo)
        self.executor = InvestigationExecutor(self.repo)
        self.tester = HypothesisTestingEngine(self.repo)
        self.repro = ReproducibilityManager(self.repo)
        self.service = ResearchOrchestrator(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_research_planner_and_knowledge_gaps(self):
        question = "How does database indexing impact latency in high-concurrency environments?"
        req = self.planner.initialize_investigation(
            question=question,
            domain="DATABASE_PERFORMANCE",
            scope="STORAGE_ENGINE",
            risk_level="LOW",
            requires_approval=False,
        )
        self.assertEqual(req.state, ResearchState.INITIALIZED)
        self.assertEqual(req.original_question, question)

        # Gap analysis
        gaps = self.planner.identify_knowledge_gaps(
            research_id=req.research_id,
            known_evidence=["B-Tree indexing speeds up equality searches", "Write amplification occurs on updates"],
            required_signals=["P99 query latency under 1000 QPS", "Lock contention duration"],
        )
        self.assertGreaterEqual(len(gaps), 1)

        saved_gaps = self.repo.list_knowledge_gaps(req.research_id)
        self.assertEqual(len(saved_gaps), len(gaps))

    def test_hypothesis_lifecycle(self):
        req = self.service.create_investigation("What is the effect of caching on API throughput?")
        
        # 1. Valid Alternative Hypothesis
        h1 = self.hypo_engine.register_hypothesis(
            research_id=req.research_id,
            statement="Redis LRU caching reduces P99 latency by at least 40% under 1000 QPS",
            hypothesis_type=HypothesisType.ALTERNATIVE,
            scope="API_GATEWAY",
            expected_observations=["P99 latency drops below 60ms"],
            falsification_conditions=["P99 latency reduction is less than 10% under 1000 QPS"],
        )
        self.assertEqual(h1.state, HypothesisState.PROPOSED)

        # 2. Competing Null Hypothesis
        h0 = self.hypo_engine.register_hypothesis(
            research_id=req.research_id,
            statement="Redis LRU caching has no statistically significant effect on P99 latency under 1000 QPS",
            hypothesis_type=HypothesisType.NULL,
            scope="API_GATEWAY",
            falsification_conditions=["P99 latency difference has p-value < 0.05 and > 20% improvement"],
        )
        self.assertEqual(h0.hypothesis_type, HypothesisType.NULL)

        # Evidence linking
        self.hypo_engine.link_evidence(h1.hypothesis_id, "Benchmark run A showed 45ms P99", is_supporting=True)
        fetched_h1 = self.repo.get_hypothesis(h1.hypothesis_id)
        self.assertEqual(len(fetched_h1.supporting_evidence), 1)

    def test_experiment_design_and_approval_gate(self):
        req = self.service.create_investigation("Testing database write load")
        h = self.service.register_hypothesis(
            research_id=req.research_id,
            statement="Bulk insert batches of 500 reduce IOPS by 30%",
            hypothesis_type=HypothesisType.ALTERNATIVE,
        )

        # Live experiment requiring approval
        live_exp = self.designer.design_experiment(
            research_id=req.research_id,
            hypothesis_id=h.hypothesis_id,
            title="Live Production Batch Benchmark",
            objective="Evaluate IOPS impact on production DB",
            experiment_type=ExperimentType.BENCHMARK,
            independent_variables=["batch_size"],
            dependent_variables=["iops_rate", "elapsed_ms"],
            controlled_variables=["network_latency", "query_payload"],
            baseline_condition="batch_size=1",
            treatment_condition="batch_size=500",
            requires_approval=True,
            isolation_environment="LIVE_CLUSTER",
        )
        self.assertTrue(live_exp.requires_approval)

        # Execution without approval must fail closed
        res = self.executor.execute_experiment(live_exp.experiment_id)
        self.assertFalse(res.get("success"))
        self.assertIn("approval", res.get("error", "").lower())

        # Authorize experiment with Module 20 token
        token = "approval-token-sec-999"
        auth_ok = self.service.authorize_experiment(live_exp.experiment_id, token)
        self.assertTrue(auth_ok)

        # Now execution proceeds
        res_auth = self.executor.execute_experiment(live_exp.experiment_id)
        self.assertTrue(res_auth.get("success"))

    def test_statistical_hypothesis_testing_rigor(self):
        req = self.service.create_investigation("Statistical latency test")
        h = self.service.register_hypothesis(
            research_id=req.research_id,
            statement="Optimization reduces response time from 100ms to 50ms",
            hypothesis_type=HypothesisType.ALTERNATIVE,
        )

        # 1. Inconclusive if sample size n < 3
        test_res_small = self.tester.evaluate_hypothesis(
            hypothesis_id=h.hypothesis_id,
            baseline_values=[100.0, 102.0],
            treatment_values=[50.0, 52.0],
            expected_effect_direction="DECREASE",
        )
        self.assertEqual(test_res_small.evaluated_state, HypothesisState.INCONCLUSIVE)
        self.assertIn("strictly insufficient", test_res_small.reasoning)

        # 2. Significant test with adequate observations (n = 10 each)
        ctrl_obs = [100.0, 102.0, 98.0, 101.0, 99.0, 103.0, 97.0, 100.5, 99.5, 101.5]
        treat_obs = [50.0, 52.0, 48.0, 51.0, 49.0, 53.0, 47.0, 50.5, 49.5, 51.5]

        test_res_sig = self.tester.evaluate_hypothesis(
            hypothesis_id=h.hypothesis_id,
            baseline_values=ctrl_obs,
            treatment_values=treat_obs,
            expected_effect_direction="DECREASE",
        )
        self.assertEqual(test_res_sig.evaluated_state, HypothesisState.SUPPORTED)
        self.assertIsNotNone(test_res_sig.confidence_interval)
        self.assertLess(test_res_sig.effect_size, 0)

    def test_reproducibility_report_generation(self):
        req = self.service.create_investigation("Memory pooling benchmark")
        h = self.service.register_hypothesis(
            research_id=req.research_id,
            statement="Memory pooling reduces peak heap allocations by 25%",
            hypothesis_type=HypothesisType.ALTERNATIVE,
        )
        exp = self.service.design_experiment(
            research_id=req.research_id,
            hypothesis_id=h.hypothesis_id,
            title="Heap Allocation Test",
            objective="Measure peak heap memory in MB",
            experiment_type=ExperimentType.BENCHMARK,
            independent_variables=["pooling_enabled"],
            dependent_variables=["heap_mb"],
            controlled_variables=["payload_size"],
            baseline_condition="pooling_enabled=False",
            treatment_condition="pooling_enabled=True",
            requires_approval=False,
        )

        # Run experiment
        exec_res = self.service.execute_experiment(
            experiment_id=exp.experiment_id,
            custom_runner=lambda ctx: {
                "baseline_metric": 500.0,
                "treatment_metric": 350.0,
                "effect_size": -150.0,
                "measurements": [{"trial": 1, "delta": -150}],
            }
        )
        self.assertTrue(exec_res.get("success"))

        # Evaluate and conclude
        conclude_res = self.service.evaluate_hypotheses_and_conclude(
            research_id=req.research_id,
            test_evaluations=[{
                "hypothesis_id": h.hypothesis_id,
                "baseline": [500.0, 510.0, 495.0, 505.0, 502.0],
                "treatment": [350.0, 360.0, 345.0, 355.0, 352.0],
                "direction": "DECREASE"
            }],
            direct_observations=["Peak heap decreased from ~502MB to ~352MB under sustained 5000 QPS load."]
        )
        self.assertTrue(conclude_res["success"])
        self.assertIsNotNone(conclude_res["manifest"]["dataset_digest_sha256"])

        # Generate markdown report
        report_md = self.service.generate_report(req.research_id)
        self.assertIn("# Scientific Research Report:", report_md)
        self.assertIn("## 1. Research Question & Scope", report_md)
        self.assertIn("## 2. Hypotheses Evaluated", report_md)
        self.assertIn("## 3. Experimental Protocol & Controls", report_md)
        self.assertIn("## 6. Reproducibility Manifest", report_md)


if __name__ == "__main__":
    unittest.main()
