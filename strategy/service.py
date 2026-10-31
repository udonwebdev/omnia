"""
OMNIA Module 37: Decision Support & Strategic Options Master Service
Coordinates the end-to-end strategic decision support loop:
Case Initialization -> Baseline & Options Generation -> Multi-Criteria Decision Analysis ->
Risk Evaluation -> Sensitivity & VOI Analysis -> Explainable Recommendations ->
Human Approval Gating -> Post-Decision Outcome Monitoring.
"""

import time
import logging
from typing import Dict, Any, List, Optional
from strategy.models import (
    DecisionCaseRecord,
    DecisionLifecycleState,
    StrategicOptionRecord,
    DecisionCriterion,
    CriterionDirection,
    OptionAssessment,
    RiskTradeoffAssessment,
    SensitivityResult,
    ValueInformationAssessment,
    StrategicRecommendation,
    DecisionOutcomeMonitoring,
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

logger = logging.getLogger("Omnia.Strategy.Service")


class DecisionSupportOrchestrator:
    """Master facade for OMNIA Module 37 Strategic Decision Support."""

    def __init__(self, db_path: str = "omnia.db", event_bus: Optional[Any] = None):
        self.repo = StrategyRepository(db_path=db_path)
        self.cases = DecisionCaseManager(self.repo)
        self.options = StrategicOptionsGenerator(self.repo)
        self.mcda = MultiCriteriaDecisionEngine(self.repo)
        self.risk = RiskTradeoffAnalyzer(self.repo)
        self.sensitivity = SensitivityAnalysisEngine()
        self.voi = ValueInformationAnalyzer()
        self.recommendations = StrategicRecommendationGenerator(self.repo)
        self.monitoring = DecisionMonitoringService(self.repo)
        self.event_bus = event_bus

    def _emit_event(self, topic: str, payload: Dict[str, Any]) -> None:
        """Publishes decision events to the Omnia Event Fabric."""
        if self.event_bus and hasattr(self.event_bus, "publish"):
            try:
                from events.models import EventEnvelope
                envelope = EventEnvelope(
                    topic=topic,
                    payload=payload,
                    source="strategy.orchestrator",
                )
                self.event_bus.publish(envelope)
            except Exception as e:
                logger.debug(f"Event bus emit skipped: {e}")

    # Case Operations
    def create_decision_case(
        self,
        title: str,
        description: str,
        owner_id: str,
        category: str = "INFRASTRUCTURE_ARCHITECTURE",
        deadline_ts: Optional[float] = None,
        context: Optional[Dict[str, Any]] = None,
        desired_outcomes: Optional[List[str]] = None,
        constraints: Optional[List[str]] = None,
        available_resources: Optional[Dict[str, Any]] = None,
        stakeholders: Optional[List[str]] = None,
        risk_tolerance: str = "MEDIUM",
    ) -> DecisionCaseRecord:
        """Creates a versioned strategic decision case."""
        case = self.cases.create_case(
            title=title,
            description=description,
            owner_id=owner_id,
            category=category,
            deadline_ts=deadline_ts,
            context=context,
            desired_outcomes=desired_outcomes,
            constraints=constraints,
            available_resources=available_resources,
            stakeholders=stakeholders,
            risk_tolerance=risk_tolerance,
        )
        self._emit_event("decision.case.created", case.to_dict())
        return case

    # Options & Criteria Registration
    def register_strategic_option(
        self,
        case_id: str,
        title: str,
        description: str,
        is_baseline: bool,
        expected_outcome: str,
        estimated_cost: float,
        implementation_complexity: str = "MEDIUM",
        reversibility_score: float = 0.8,
        time_horizon_days: int = 30,
        dependencies: Optional[List[str]] = None,
        benefits: Optional[List[str]] = None,
        disadvantages: Optional[List[str]] = None,
        critical_assumptions: Optional[List[str]] = None,
        known_limitations: Optional[List[str]] = None,
        origin: str = "HUMAN_PROPOSAL",
    ) -> StrategicOptionRecord:
        """Adds a candidate option to a decision case."""
        opt = self.options.register_option(
            case_id=case_id,
            title=title,
            description=description,
            is_baseline=is_baseline,
            expected_outcome=expected_outcome,
            estimated_cost=estimated_cost,
            implementation_complexity=implementation_complexity,
            reversibility_score=reversibility_score,
            time_horizon_days=time_horizon_days,
            dependencies=dependencies,
            benefits=benefits,
            disadvantages=disadvantages,
            critical_assumptions=critical_assumptions,
            known_limitations=known_limitations,
            origin=origin,
        )
        self._emit_event("decision.option.registered", opt.to_dict())
        return opt

    def register_decision_criterion(
        self,
        case_id: str,
        name: str,
        weight: float,
        direction: CriterionDirection = CriterionDirection.MAXIMIZE,
        is_mandatory: bool = False,
        minimum_threshold: Optional[float] = None,
        acceptable_range: Optional[List[float]] = None,
        description: str = "",
    ) -> DecisionCriterion:
        """Adds an evaluation criterion to a decision case."""
        import uuid
        crit = DecisionCriterion(
            criterion_id=f"crit-{uuid.uuid4().hex[:8]}",
            case_id=case_id,
            name=name,
            weight=weight,
            direction=direction,
            is_mandatory=is_mandatory,
            minimum_threshold=minimum_threshold,
            acceptable_range=acceptable_range,
            description=description,
        )
        self.repo.save_criterion(crit)
        return crit

    # Comprehensive Strategic Analysis Pipeline
    def run_strategic_analysis(
        self,
        case_id: str,
        raw_metrics_matrix: Dict[str, Dict[str, float]],
        risk_inputs_matrix: Dict[str, Dict[str, Any]],
        known_information_gaps: Optional[List[str]] = None,
        has_active_contradictions: bool = False,
    ) -> Dict[str, Any]:
        """
        Executes MCDA evaluation, risk matrices, sensitivity checks, VOI, and synthesizes recommendation.
        """
        case = self.repo.get_case(case_id)
        if not case:
            raise ValueError(f"Decision case '{case_id}' not found")

        self.cases.transition_state(case_id, DecisionLifecycleState.ANALYSIS)
        self._emit_event("decision.analysis.started", {"case_id": case_id})

        # Ensure baseline status-quo option exists
        self.options.ensure_baseline_option(case_id)
        options = self.repo.list_options_for_case(case_id)
        criteria = self.repo.list_criteria_for_case(case_id)

        # 1. Multi-Criteria Evaluation
        assessments = self.mcda.evaluate_options(
            case_id=case_id,
            options=options,
            criteria=criteria,
            raw_metrics_matrix=raw_metrics_matrix,
        )

        # 2. Risk & Trade-off Assessments
        risk_map: Dict[str, RiskTradeoffAssessment] = {}
        for opt in options:
            r_input = risk_inputs_matrix.get(opt.option_id, {})
            risk_ass = self.risk.evaluate_risk(
                case_id=case_id,
                option=opt,
                probability_of_failure=float(r_input.get("prob", 0.2)),
                severity_of_failure=float(r_input.get("sev", 0.4)),
                financial_exposure=float(r_input.get("exposure", opt.estimated_cost * 0.5)),
                operational_disruption=r_input.get("disruption", "MINOR"),
                security_risk=r_input.get("sec_risk", "LOW"),
                mitigation_strategy=r_input.get("mitigation", ""),
            )
            risk_map[opt.option_id] = risk_ass

        # 3. Sensitivity Analysis
        viable_ass = [a for a in assessments if not a.is_pareto_dominated and not a.violates_mandatory_constraint]
        top_opt_id = max(viable_ass, key=lambda x: x.normalized_score).option_id if viable_ass else options[0].option_id
        sensitivity = self.sensitivity.evaluate_sensitivity(
            case_id=case_id,
            options=options,
            criteria=criteria,
            assessments=assessments,
            dominant_option_id=top_opt_id,
        )

        # 4. Value of Information (VOI)
        voi = self.voi.evaluate_voi(
            case_id=case_id,
            sensitivity=sensitivity,
            known_information_gaps=known_information_gaps or [],
            has_active_contradictions=has_active_contradictions,
        )

        # 5. Recommendation Generation
        recommendation = self.recommendations.generate_recommendation(
            case_id=case_id,
            options=options,
            assessments=assessments,
            risk_assessments=risk_map,
            sensitivity=sensitivity,
            voi=voi,
        )

        self.cases.transition_state(case_id, DecisionLifecycleState.REVIEW_REQUIRED)
        self._emit_event("decision.recommendation.generated", recommendation.to_dict())

        return {
            "success": True,
            "case_id": case_id,
            "recommendation": recommendation.to_dict(),
            "sensitivity": sensitivity.to_dict(),
            "value_of_information": voi.to_dict(),
            "assessments": [a.to_dict() for a in assessments],
        }

    # Human Authority & Final Decision Gate
    def record_human_decision(
        self,
        case_id: str,
        selected_option_id: str,
        decided_by: str,
        approval_token: Optional[str] = None,
        review_horizon_days: int = 90,
    ) -> DecisionCaseRecord:
        """
        Records the authoritative human decision:
        Enforces Module 20 human approval token for high-risk / production categories.
        """
        case = self.repo.get_case(case_id)
        if not case:
            raise ValueError(f"Decision case '{case_id}' not found")

        # Approval Gate: If case is high risk tolerance or production category, require approval token
        if case.risk_tolerance == "HIGH" and not approval_token:
            logger.warning(f"Human decision blocked for case '{case_id}': Missing mandatory approval token")
            raise PermissionError("Human authority gate: High-risk decisions strictly require a Module 20 approval token")

        case.selected_option_id = selected_option_id
        case.decided_by = decided_by
        case.approval_token = approval_token
        case.state = DecisionLifecycleState.DECIDED
        case.review_date_ts = time.time() + (review_horizon_days * 86400)
        case.updated_at = time.time()
        self.repo.save_case(case)

        self._emit_event("decision.finalized", {
            "case_id": case_id,
            "selected_option_id": selected_option_id,
            "decided_by": decided_by,
        })
        logger.info(f"Recorded human decision for case '{case_id}': Option '{selected_option_id}' by '{decided_by}'")
        return case

    # Post-Decision Monitoring
    def record_outcome_monitoring(
        self,
        case_id: str,
        actual_cost: Optional[float] = None,
        expected_cost: Optional[float] = None,
        assumptions_status: Optional[Dict[str, bool]] = None,
        critical_drift_detected: bool = False,
    ) -> DecisionOutcomeMonitoring:
        """Records actual observed outcomes and schedules reassessment if variance > 30%."""
        case = self.repo.get_case(case_id)
        if not case or not case.selected_option_id:
            raise ValueError(f"Decision case '{case_id}' has not been finalized with a selected option")

        mon = self.monitoring.record_outcome(
            case_id=case_id,
            selected_option_id=case.selected_option_id,
            actual_cost=actual_cost,
            expected_cost=expected_cost,
            assumptions_status=assumptions_status,
            critical_drift_detected=critical_drift_detected,
        )
        if mon.reassessment_triggered:
            self._emit_event("decision.reassessment.required", mon.to_dict())
        return mon


# Global singleton
decision_support_service = DecisionSupportOrchestrator()
