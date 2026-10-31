"""
OMNIA Module 35: Autonomous Research Engine Master Service & Event Integration
Coordinates the entire research loop:
Question -> Plan -> Gap Analysis -> Hypotheses -> Experiment -> Execution -> Testing -> Conclusion -> Reproducible Report.
"""

import time
import uuid
import logging
from typing import Dict, Any, List, Optional, Callable
from research.models import (
    ResearchRequest,
    ResearchState,
    HypothesisRecord,
    HypothesisType,
    HypothesisState,
    ExperimentDefinition,
    ExperimentType,
    ResearchConclusion,
    ReproducibilityManifest,
)
from research.persistence import ResearchRepository
from research.planner import ResearchPlanner
from research.hypotheses import HypothesisEngine
from research.experiments import ExperimentDesigner
from research.execution import InvestigationExecutor
from research.testing import HypothesisTestingEngine
from research.reproducibility import ReproducibilityManager

logger = logging.getLogger("Omnia.Research.Service")


class ResearchOrchestrator:
    """Master facade for autonomous research, hypothesis testing, and scientific discovery."""

    def __init__(self, db_path: str = "omnia.db", event_bus: Optional[Any] = None):
        self.repo = ResearchRepository(db_path=db_path)
        self.planner = ResearchPlanner(self.repo)
        self.hypotheses = HypothesisEngine(self.repo)
        self.designer = ExperimentDesigner(self.repo)
        self.executor = InvestigationExecutor(self.repo)
        self.tester = HypothesisTestingEngine(self.repo)
        self.reproducibility = ReproducibilityManager(self.repo)
        self.event_bus = event_bus

    def _emit_event(self, topic: str, payload: Dict[str, Any]) -> None:
        """Publishes research events to the Omnia Event Fabric."""
        if self.event_bus and hasattr(self.event_bus, "publish"):
            try:
                from events.models import EventEnvelope
                envelope = EventEnvelope(
                    topic=topic,
                    payload=payload,
                    source="research.orchestrator",
                )
                self.event_bus.publish(envelope)
            except Exception as e:
                logger.debug(f"Event bus emit skipped or failed: {e}")

    # Core Investigative Operations
    def create_investigation(
        self,
        question: str,
        domain: str = "SYSTEMS_PERFORMANCE",
        scope: str = "INTERNAL_SERVICES",
        risk_level: str = "LOW",
        requires_approval: bool = False,
    ) -> ResearchRequest:
        """Starts a new research inquiry."""
        req = self.planner.initialize_investigation(
            question=question,
            domain=domain,
            scope=scope,
            risk_level=risk_level,
            requires_approval=requires_approval,
        )
        self._emit_event("research.request.created", req.to_dict())
        return req

    def identify_knowledge_gaps(
        self,
        research_id: str,
        known_evidence: List[str],
        required_signals: List[str],
    ) -> List[Dict[str, Any]]:
        """Identifies and persists missing evidence gaps."""
        gaps = self.planner.identify_knowledge_gaps(
            research_id=research_id,
            known_evidence=known_evidence,
            required_signals=required_signals,
        )
        for g in gaps:
            self._emit_event("research.gap.identified", g.to_dict())
        return [g.to_dict() for g in gaps]

    def register_hypothesis(
        self,
        research_id: str,
        statement: str,
        hypothesis_type: HypothesisType = HypothesisType.ALTERNATIVE,
        scope: str = "GLOBAL",
        assumptions: Optional[List[str]] = None,
        expected_observations: Optional[List[str]] = None,
        falsification_conditions: Optional[List[str]] = None,
    ) -> HypothesisRecord:
        """Registers a testable hypothesis."""
        hypo = self.hypotheses.register_hypothesis(
            research_id=research_id,
            statement=statement,
            hypothesis_type=hypothesis_type,
            scope=scope,
            assumptions=assumptions,
            expected_observations=expected_observations,
            falsification_conditions=falsification_conditions,
        )
        self._emit_event("research.hypothesis.proposed", hypo.to_dict())
        return hypo

    def design_experiment(
        self,
        research_id: str,
        hypothesis_id: str,
        title: str,
        objective: str,
        experiment_type: ExperimentType,
        independent_variables: List[str],
        dependent_variables: List[str],
        controlled_variables: List[str],
        baseline_condition: str,
        treatment_condition: str,
        sample_size: int = 30,
        requires_approval: bool = False,
        isolation_environment: str = "SIMULATION",
    ) -> ExperimentDefinition:
        """Designs a controlled experiment."""
        exp = self.designer.design_experiment(
            research_id=research_id,
            hypothesis_id=hypothesis_id,
            title=title,
            objective=objective,
            experiment_type=experiment_type,
            independent_variables=independent_variables,
            dependent_variables=dependent_variables,
            controlled_variables=controlled_variables,
            baseline_condition=baseline_condition,
            treatment_condition=treatment_condition,
            sample_size=sample_size,
            requires_approval=requires_approval,
            isolation_environment=isolation_environment,
        )
        self._emit_event("research.experiment.designed", exp.to_dict())
        return exp

    def authorize_experiment(self, experiment_id: str, approval_token: str) -> bool:
        """Authorizes an approval-gated experiment."""
        ok = self.designer.authorize_experiment(experiment_id, approval_token)
        if ok:
            self._emit_event("research.experiment.approval_granted", {"experiment_id": experiment_id, "token": approval_token[:8]})
        return ok

    def execute_experiment(
        self,
        experiment_id: str,
        custom_runner: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Runs the experiment and collects empirical trial measurements."""
        res = self.executor.execute_experiment(experiment_id=experiment_id, custom_runner=custom_runner)
        if res.get("success", False):
            self._emit_event("research.experiment.completed", res["execution_result"])
        return res

    def evaluate_hypotheses_and_conclude(
        self,
        research_id: str,
        test_evaluations: List[Dict[str, Any]],  # List of {"hypothesis_id": ..., "baseline": [...], "treatment": [...], "direction": ...}
        direct_observations: List[str],
    ) -> Dict[str, Any]:
        """Evaluates all competing hypotheses, synthesizes a conclusion, and outputs a manifest."""
        test_results = []
        for te in test_evaluations:
            tr = self.tester.evaluate_hypothesis(
                hypothesis_id=te["hypothesis_id"],
                baseline_values=te["baseline"],
                treatment_values=te["treatment"],
                expected_effect_direction=te.get("direction", "DECREASE"),
            )
            test_results.append(tr.to_dict())
            self._emit_event("research.hypothesis.tested", tr.to_dict())

        # Fetch hypotheses
        all_hypos = self.repo.list_hypotheses(research_id)
        conclusion = self.tester.synthesize_conclusion(
            research_id=research_id,
            hypotheses=all_hypos,
            direct_observations=direct_observations,
        )
        self._emit_event("research.conclusion.updated", conclusion.to_dict())

        # Generate reproducibility manifest
        dataset_sample = [{"test": t} for t in test_results]
        manifest = self.reproducibility.generate_manifest(research_id=research_id, dataset=dataset_sample)

        # Update request state
        req = self.repo.get_request(research_id)
        if req:
            req.transition_to(ResearchState.CONCLUDED)
            self.repo.save_request(req)

        return {
            "success": True,
            "research_id": research_id,
            "conclusion": conclusion.to_dict(),
            "test_results": test_results,
            "manifest": manifest.to_dict(),
        }

    def generate_report(self, research_id: str) -> str:
        """Produces a complete markdown research report."""
        conclusion = self.repo.get_conclusion(research_id)
        if not conclusion:
            return f"Error: No conclusion found for research '{research_id}'"

        hypos = self.repo.list_hypotheses(research_id)
        # Fetch experiments for this research
        all_exps = []
        for h in hypos:
            with self.repo._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT experiment_id FROM research_experiments WHERE hypothesis_id = ?", (h.hypothesis_id,))
                for row in cur.fetchall():
                    exp = self.repo.get_experiment(row["experiment_id"])
                    if exp:
                        all_exps.append(exp)

        report = self.reproducibility.generate_report(
            research_id=research_id,
            conclusion=conclusion,
            hypotheses=hypos,
            experiments=all_exps,
        )
        self._emit_event("research.report.generated", {"research_id": research_id, "size_chars": len(report)})
        return report


# Global singleton
research_service = ResearchOrchestrator()
