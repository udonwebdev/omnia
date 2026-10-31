"""End-to-End integration test for Omnia Module 35: Autonomous Research, Scientific Discovery & Hypothesis Testing Engine."""

import os
import unittest
import tempfile
import shutil
import hashlib

from research.models import (
    HypothesisType,
    HypothesisState,
    ExperimentType,
    ConclusionState,
)
from research.service import ResearchOrchestrator


class TestResearchModule35E2E(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_research_e2e.db")
        self.service = ResearchOrchestrator(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_complete_deterministic_scientific_investigation_loop(self):
        """
        Full scientific discovery loop:
        1. Formulate investigative research question
        2. Analyze knowledge gaps
        3. Propose two competing hypotheses (H1: Adaptive Caching vs H0: Standard LRU)
        4. Design controlled benchmark experiments
        5. Execute experiments under controlled parameters
        6. Apply rigorous Welch t-interval statistical hypothesis testing
        7. Synthesize definitive evidence-backed research conclusions
        8. Verify cryptographic reproducibility manifest and report
        """
        # Step 1: Initialize Investigation
        question = "Does adaptive TTL caching outperform static LRU caching in write-heavy workloads?"
        req = self.service.create_investigation(
            question=question,
            domain="DATABASE_PERFORMANCE",
            scope="STORAGE_ENGINE",
            risk_level="LOW",
            requires_approval=False,
        )
        self.assertIsNotNone(req.research_id)

        # Step 2: Identify Knowledge Gaps
        gaps = self.service.identify_knowledge_gaps(
            research_id=req.research_id,
            known_evidence=[
                "Static LRU suffers from cache pollution during scan or bulk update workloads.",
                "Adaptive TTL increases cache management CPU overhead slightly."
            ],
            required_signals=[
                "P99 latency distribution under write-heavy loads",
                "Hit rate variations under cache thrashing"
            ]
        )
        self.assertGreaterEqual(len(gaps), 1)

        # Step 3: Propose Competing Hypotheses
        # H1: Primary / Alternative Hypothesis
        h1 = self.service.register_hypothesis(
            research_id=req.research_id,
            statement="Adaptive TTL caching achieves lower P99 query latency compared to static LRU in write-heavy workloads",
            hypothesis_type=HypothesisType.ALTERNATIVE,
            scope="DATABASE_ENGINE",
            falsification_conditions=["P99 latency of Adaptive TTL is greater than or equal to static LRU"],
        )

        # H0: Competing Null Hypothesis
        h0 = self.service.register_hypothesis(
            research_id=req.research_id,
            statement="Adaptive TTL caching has no significant difference or worse P99 query latency compared to static LRU",
            hypothesis_type=HypothesisType.NULL,
            scope="DATABASE_ENGINE",
            falsification_conditions=["Adaptive TTL shows statistically significant lower P99 latency with > 15% improvement"],
        )

        # Step 4: Design Controlled Benchmark Experiment
        exp = self.service.design_experiment(
            research_id=req.research_id,
            hypothesis_id=h1.hypothesis_id,
            title="Adaptive TTL vs Static LRU P99 Latency Benchmark",
            objective="Measure P99 latency delta under 70:30 write-to-read ratio",
            experiment_type=ExperimentType.BENCHMARK,
            independent_variables=["caching_strategy"],
            dependent_variables=["p99_latency_ms", "hit_rate"],
            controlled_variables=["workload_ratio=70:30", "total_ops=10000", "concurrency=64"],
            baseline_condition="caching_strategy=STATIC_LRU",
            treatment_condition="caching_strategy=ADAPTIVE_TTL",
            sample_size=10,
            requires_approval=False,
            isolation_environment="SIMULATION",
        )
        self.assertFalse(exp.requires_approval)

        # Step 5: Execute Controlled Experiment with Empirical Measurements
        # Control observations (Static LRU latency in ms): mean ~ 84.8 ms
        control_p99 = [85.2, 84.6, 86.1, 83.9, 85.0, 84.1, 86.5, 83.8, 85.4, 84.4]
        # Treatment observations (Adaptive TTL latency in ms): mean ~ 52.3 ms
        treatment_p99 = [52.1, 51.8, 53.0, 52.5, 51.9, 52.7, 53.2, 51.6, 52.4, 52.8]

        exec_res = self.service.execute_experiment(
            experiment_id=exp.experiment_id,
            custom_runner=lambda ctx: {
                "baseline_metric": sum(control_p99) / len(control_p99),
                "treatment_metric": sum(treatment_p99) / len(treatment_p99),
                "effect_size": (sum(treatment_p99) / len(treatment_p99)) - (sum(control_p99) / len(control_p99)),
                "measurements": [{"trial": i, "ctrl": c, "treat": t} for i, (c, t) in enumerate(zip(control_p99, treatment_p99))],
            }
        )
        self.assertTrue(exec_res.get("success"))

        # Step 6: Rigorous Statistical Evaluation & Hypothesis Testing
        conclude_res = self.service.evaluate_hypotheses_and_conclude(
            research_id=req.research_id,
            test_evaluations=[
                {
                    "hypothesis_id": h1.hypothesis_id,
                    "baseline": control_p99,
                    "treatment": treatment_p99,
                    "direction": "DECREASE",
                },
                {
                    "hypothesis_id": h0.hypothesis_id,
                    "baseline": control_p99,
                    "treatment": treatment_p99,
                    "direction": "INCREASE",  # H0 expects no decrease or worse latency
                }
            ],
            direct_observations=[
                f"Adaptive TTL achieved empirical mean latency of {sum(treatment_p99)/len(treatment_p99):.2f}ms vs static LRU {sum(control_p99)/len(control_p99):.2f}ms.",
                "Reduction in cache churn reduced secondary storage read IOPS by 38%."
            ]
        )
        self.assertTrue(conclude_res["success"])
        test_results = conclude_res["test_results"]
        self.assertEqual(len(test_results), 2)

        # Find test results for H1 and H0
        res_h1 = next(r for r in test_results if r["hypothesis_id"] == h1.hypothesis_id)
        res_h0 = next(r for r in test_results if r["hypothesis_id"] == h0.hypothesis_id)

        # Verify H1 is supported
        self.assertEqual(res_h1["evaluated_state"], HypothesisState.SUPPORTED.value)
        self.assertLess(res_h1["effect_size"], 0.0)

        # Verify H0 is not supported
        self.assertEqual(res_h0["evaluated_state"], HypothesisState.NOT_SUPPORTED.value)

        # Step 7: Synthesize Conclusion & Generate Reproducible Report
        manifest = conclude_res["manifest"]
        self.assertIsNotNone(manifest["dataset_digest_sha256"])
        self.assertEqual(manifest["methodology_version"], "1.0.0-welch-interval")

        report_md = self.service.generate_report(req.research_id)

        # Verify Report Structure and Rigor
        self.assertIn("# Scientific Research Report", report_md)
        self.assertIn("Does adaptive TTL caching outperform static LRU caching", report_md)
        self.assertIn("Adaptive TTL caching achieves lower P99 query latency", report_md)
        self.assertIn("## 1. Research Question & Scope", report_md)
        self.assertIn("## 2. Hypotheses Evaluated", report_md)
        self.assertIn("## 3. Experimental Protocol & Controls", report_md)
        self.assertIn("## 4. Empirical Observations", report_md)
        self.assertIn("## 5. Traceable Conclusion & Limitations", report_md)
        self.assertIn("## 6. Reproducibility Manifest", report_md)
        self.assertIn(manifest["dataset_digest_sha256"], report_md)


if __name__ == "__main__":
    unittest.main()
