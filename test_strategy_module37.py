"""
Unit tests for Omnia Module 37: Decision Support, Strategic Options & Trade-off Analysis Engine.
"""

import os
import unittest
import tempfile
import shutil

from strategy.models import (
    DecisionLifecycleState,
    CriterionDirection,
    RecommendationOutcome,
    InformationAction,
)
from strategy.persistence import StrategyRepository
from strategy.cases import DecisionCaseManager
from strategy.options import StrategicOptionsGenerator
from strategy.mcda import MultiCriteriaDecisionEngine
from strategy.risk import RiskTradeoffAnalyzer
from strategy.sensitivity import SensitivityAnalysisEngine
from strategy.voi import ValueInformationAnalyzer
from strategy.recommendation import StrategicRecommendationGenerator
from strategy.monitoring import DecisionMonitoringService
from strategy.service import DecisionSupportOrchestrator


class TestStrategyModule37(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_strategy.db")
        self.repo = StrategyRepository(self.db_path)
        self.cases = DecisionCaseManager(self.repo)
        self.options = StrategicOptionsGenerator(self.repo)
        self.mcda = MultiCriteriaDecisionEngine(self.repo)
        self.risk = RiskTradeoffAnalyzer(self.repo)
        self.sensitivity = SensitivityAnalysisEngine()
        self.voi = ValueInformationAnalyzer()
        self.recommendations = StrategicRecommendationGenerator(self.repo)
        self.monitoring = DecisionMonitoringService(self.repo)
        self.service = DecisionSupportOrchestrator(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_decision_case_lifecycle(self):
        case = self.cases.create_case(
            title="Database Migration Architecture",
            description="Evaluate switching primary relational DB engine",
            owner_id="lead_architect",
            risk_tolerance="MEDIUM",
        )
        self.assertEqual(case.state, DecisionLifecycleState.DRAFT)
        self.assertEqual(case.version, 1)

        # Transition to options ready
        case = self.cases.transition_state(case.case_id, DecisionLifecycleState.OPTIONS_READY)
        self.assertEqual(case.state, DecisionLifecycleState.OPTIONS_READY)

        # Version bump on material reassessment
        case = self.cases.bump_version(case.case_id, "New cloud pricing announced")
        self.assertEqual(case.version, 2)
        self.assertEqual(case.state, DecisionLifecycleState.REOPENED)

    def test_options_generator_and_baseline_enforcement(self):
        case = self.cases.create_case(
            title="Cache Engine Selection",
            description="Evaluate caching layers",
            owner_id="arch_1",
        )

        # Register proposal
        opt1 = self.options.register_option(
            case_id=case.case_id,
            title="Adopt Distributed Redis Cluster",
            description="Deploy 3-node Redis cluster",
            is_baseline=False,
            expected_outcome="P99 latency drops below 20ms",
            estimated_cost=15000.0,
            implementation_complexity="MEDIUM",
            reversibility_score=0.9,
        )
        self.assertFalse(opt1.is_baseline)

        # Ensure baseline
        baseline = self.options.ensure_baseline_option(case.case_id)
        self.assertTrue(baseline.is_baseline)
        self.assertEqual(baseline.title, "Status Quo (No Action)")

        all_opts = self.repo.list_options_for_case(case.case_id)
        self.assertEqual(len(all_opts), 2)

    def test_mcda_evaluation_and_pareto_dominance(self):
        case = self.cases.create_case(title="Compute Tier", description="Compute sizing", owner_id="ops")
        
        opt_a = self.options.register_option(case.case_id, "Option A (High Perf)", "High compute", False, "Fast", 5000.0)
        opt_b = self.options.register_option(case.case_id, "Option B (Low Cost)", "Cheap compute", False, "Slow", 1000.0)
        opt_c = self.options.register_option(case.case_id, "Option C (Dominated)", "Worse in all", False, "Slow & Expensive", 8000.0)

        crit_cost = self.service.register_decision_criterion(case.case_id, "Cost", 0.4, CriterionDirection.MINIMIZE)
        crit_tps = self.service.register_decision_criterion(case.case_id, "Throughput", 0.6, CriterionDirection.MAXIMIZE)

        metrics = {
            opt_a.option_id: {crit_cost.criterion_id: 5000.0, crit_tps.criterion_id: 10000.0},
            opt_b.option_id: {crit_cost.criterion_id: 1000.0, crit_tps.criterion_id: 3000.0},
            opt_c.option_id: {crit_cost.criterion_id: 8000.0, crit_tps.criterion_id: 2000.0},  # Dominated by opt_b
        }

        assessments = self.mcda.evaluate_options(case.case_id, [opt_a, opt_b, opt_c], [crit_cost, crit_tps], metrics)
        self.assertEqual(len(assessments), 3)

        ass_c = next(a for a in assessments if a.option_id == opt_c.option_id)
        self.assertTrue(ass_c.is_pareto_dominated)

    def test_risk_tradeoff_assessment_and_reversibility(self):
        case = self.cases.create_case(title="Cloud Exit", description="Data repatriate", owner_id="cto")
        opt = self.options.register_option(
            case.case_id, "Physical Hardware Colocation", "Buy bare metal", False, "No cloud fees", 100000.0,
            reversibility_score=0.2  # Highly irreversible
        )

        risk = self.risk.evaluate_risk(
            case_id=case.case_id,
            option=opt,
            probability_of_failure=0.3,
            severity_of_failure=0.8,
            financial_exposure=80000.0,
            operational_disruption="MAJOR",
            mitigation_strategy="Redundant dual-switch topology",
        )
        self.assertGreater(risk.residual_risk_score, 0.4)
        self.assertEqual(risk.operational_disruption, "MAJOR")

    def test_recommendation_abstention_on_disputed_evidence(self):
        case = self.service.create_decision_case("Storage Tier", "SAN vs NVMe", "admin")
        opt = self.service.register_strategic_option(case.case_id, "SAN Option", "Storage array", False, "Fast", 50000.0)
        crit = self.service.register_decision_criterion(case.case_id, "Cost", 1.0, CriterionDirection.MINIMIZE)

        # Active contradiction across evidence
        analysis = self.service.run_strategic_analysis(
            case_id=case.case_id,
            raw_metrics_matrix={opt.option_id: {crit.criterion_id: 50000.0}},
            risk_inputs_matrix={opt.option_id: {"prob": 0.2, "sev": 0.3}},
            has_active_contradictions=True,  # Disputed evidence
        )

        rec = analysis["recommendation"]
        self.assertEqual(rec["outcome"], RecommendationOutcome.DISPUTED_EVIDENCE.value)
        self.assertIsNone(rec["recommended_option_id"])
        self.assertIn("Abstained", rec["primary_justification"])

    def test_human_authority_gate_and_outcome_monitoring(self):
        case = self.service.create_decision_case(
            title="Core Production Switch",
            description="Replace core gateway",
            owner_id="net_lead",
            risk_tolerance="HIGH",  # Requires Module 20 token
        )
        opt = self.service.register_strategic_option(case.case_id, "Gateway X", "Next gen", False, "Zero drop", 40000.0)

        # 1. Unapproved decision on high-risk case is blocked
        with self.assertRaises(PermissionError):
            self.service.record_human_decision(
                case_id=case.case_id,
                selected_option_id=opt.option_id,
                decided_by="operator_john",
                approval_token=None,  # Missing token
            )

        # 2. Approved decision succeeds
        token = "approval-token-gov-999"
        decided_case = self.service.record_human_decision(
            case_id=case.case_id,
            selected_option_id=opt.option_id,
            decided_by="operator_john",
            approval_token=token,
        )
        self.assertEqual(decided_case.state, DecisionLifecycleState.DECIDED)

        # 3. Outcome monitoring triggers reassessment when cost variance > 30%
        mon = self.service.record_outcome_monitoring(
            case_id=case.case_id,
            actual_cost=60000.0,
            expected_cost=40000.0,  # 50% variance
            assumptions_status={"Hardware delivery on schedule": False},
        )
        self.assertTrue(mon.reassessment_triggered)
        self.assertIn("50.0%", mon.reassessment_reason)

        reloaded = self.repo.get_case(case.case_id)
        self.assertEqual(reloaded.state, DecisionLifecycleState.REOPENED)
        self.assertEqual(reloaded.version, 2)


if __name__ == "__main__":
    unittest.main()
