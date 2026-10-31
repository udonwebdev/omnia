"""
Omnia Module 38: Autonomous Goal Management, Outcome Tracking & Strategic Execution Intelligence.
Goal Execution Intelligence Orchestrator: Unified Facade and Event Fabric Integration.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from events import Event, EventFabric, EventPriority, EventSeverity, event_fabric
from goals.alignment import StrategicAlignmentEvaluator
from goals.audit import GoalAuditService
from goals.corrective import CorrectiveActionAdvisor
from goals.decomposition import GoalDecompositionEngine
from goals.forecasting import GoalForecastAdapter
from goals.health import GoalHealthMonitor
from goals.models import (
    CorrectiveActionProposal,
    GoalDefinition,
    GoalHealthRecord,
    GoalPriority,
    GoalProgressAssessment,
    GoalType,
    InitiativeRecord,
    KeyResultDefinition,
    MetricType,
    MilestoneRecord,
    OutcomeEvidenceRecord,
    VerificationTier,
)
from goals.outcomes import OutcomeDefinitionEngine
from goals.persistence import GoalRepository
from goals.progress import ProgressMeasurementEngine
from goals.registry import GoalRegistry
from goals.reporting import StrategicOutcomeReporter
from goals.verification import OutcomeVerificationService

logger = logging.getLogger("Omnia.Goals.Service")


class GoalExecutionIntelligenceOrchestrator:
    """
    Central orchestration service for Module 38.
    Integrates all goal, outcome, decomposition, verification, and alignment capabilities
    with Omnia's Event Fabric and Module 20 human approval boundary.
    """

    def __init__(
        self,
        repository: Optional[GoalRepository] = None,
        bus: Optional[EventFabric] = None,
    ):
        self.repo = repository or GoalRepository()
        self.bus = bus or event_fabric

        self.registry = GoalRegistry(self.repo)
        self.outcomes = OutcomeDefinitionEngine(self.repo)
        self.verification = OutcomeVerificationService(self.repo, self.outcomes)
        self.decomposition = GoalDecompositionEngine(self.repo)
        self.progress = ProgressMeasurementEngine(self.repo, self.outcomes)
        self.alignment = StrategicAlignmentEvaluator(self.repo)
        self.health = GoalHealthMonitor(self.repo, self.progress)
        self.forecasting = GoalForecastAdapter(self.repo)
        self.corrective = CorrectiveActionAdvisor(self.repo)
        self.audit = GoalAuditService(self.repo)
        self.reporting = StrategicOutcomeReporter(self.repo, self.progress)

    def _publish_event(self, topic: str, payload: Dict[str, Any]) -> None:
        if self.bus and hasattr(self.bus, "publish"):
            try:
                from events.models import EventEnvelope
                envelope = EventEnvelope(
                    event_type=topic,
                    source="module38.goals",
                    payload=payload,
                )
                self.bus.publish(envelope)
            except Exception as e:
                logger.debug(f"Event bus emit skipped: {e}")

    # Facade methods
    def create_goal(
        self,
        title: str,
        description: str,
        purpose: str,
        owner: str,
        goal_type: GoalType = GoalType.STRATEGIC,
        priority: GoalPriority = GoalPriority.HIGH,
        parent_goal_id: Optional[str] = None,
        target_date: Optional[str] = None,
        success_criteria: Optional[List[str]] = None,
        constraints: Optional[List[str]] = None,
        dependencies: Optional[List[str]] = None,
    ) -> GoalDefinition:
        goal = self.registry.register_goal(
            title=title,
            description=description,
            purpose=purpose,
            owner=owner,
            goal_type=goal_type,
            priority=priority,
            parent_goal_id=parent_goal_id,
            target_date=target_date,
            success_criteria=success_criteria,
            constraints=constraints,
            dependencies=dependencies,
        )
        self._publish_event("goal.created", {"goal_id": goal.goal_id, "title": goal.title, "owner": goal.owner})
        return goal

    def activate_goal(self, goal_id: str, operator_id: str) -> GoalDefinition:
        goal = self.registry.activate_goal(goal_id, operator_id)
        self._publish_event("goal.activated", {"goal_id": goal.goal_id, "operator_id": operator_id})
        return goal

    def define_key_result(
        self,
        goal_id: str,
        metric_name: str,
        description: str,
        unit: str,
        metric_type: MetricType,
        baseline_value: float,
        target_value: float,
        required_verification_tier: VerificationTier = VerificationTier.SYSTEM_OBSERVED,
    ) -> KeyResultDefinition:
        kr = self.outcomes.register_key_result(
            goal_id=goal_id,
            metric_name=metric_name,
            description=description,
            unit=unit,
            metric_type=metric_type,
            baseline_value=baseline_value,
            target_value=target_value,
            required_verification_tier=required_verification_tier,
        )
        self._publish_event("goal.key_result.defined", {"goal_id": goal_id, "key_result_id": kr.key_result_id})
        return kr

    def record_reported_progress(self, key_result_id: str, reported_value: float, reporter: str) -> KeyResultDefinition:
        kr = self.verification.record_reported_metric(key_result_id, reported_value, reporter)
        self._publish_event("goal.metric.reported", {"key_result_id": key_result_id, "reported_value": reported_value})
        return kr

    def verify_outcome_metric(
        self,
        key_result_id: str,
        observed_value: float,
        verification_tier: VerificationTier,
        data_source: str,
        evidence_summary: str,
        evidence_payload: Dict[str, Any],
        verified_by: str,
        approval_token: Optional[str] = None,
    ) -> OutcomeEvidenceRecord:
        ev = self.verification.submit_and_verify_evidence(
            key_result_id=key_result_id,
            observed_value=observed_value,
            verification_tier=verification_tier,
            data_source=data_source,
            evidence_summary=evidence_summary,
            evidence_payload=evidence_payload,
            verified_by=verified_by,
            approval_token=approval_token,
        )
        self._publish_event("goal.outcome.verified", {
            "key_result_id": key_result_id,
            "observed_value": observed_value,
            "tier": verification_tier.value,
            "is_valid": ev.is_valid,
        })
        return ev

    def decompose_initiative(
        self,
        goal_id: str,
        title: str,
        scope: str,
        expected_outcome: str,
        owner: str,
        required_capabilities: Optional[List[str]] = None,
        task_graph_id: Optional[str] = None,
    ) -> InitiativeRecord:
        init = self.decomposition.create_initiative(
            goal_id=goal_id,
            title=title,
            scope=scope,
            expected_outcome=expected_outcome,
            owner=owner,
            required_capabilities=required_capabilities,
            task_graph_id=task_graph_id,
        )
        self._publish_event("goal.decomposed", {"goal_id": goal_id, "initiative_id": init.initiative_id})
        return init

    def register_milestone(
        self,
        initiative_id: str,
        title: str,
        description: str,
        target_date: str,
    ) -> MilestoneRecord:
        ms = self.decomposition.create_milestone(initiative_id, title, description, target_date)
        return ms

    def complete_milestone(self, milestone_id: str, evidence_id: Optional[str] = None) -> MilestoneRecord:
        ms = self.decomposition.complete_milestone(milestone_id, evidence_id)
        self._publish_event("goal.milestone.completed", {"milestone_id": milestone_id, "initiative_id": ms.initiative_id})
        return ms

    def evaluate_health(self, goal_id: str) -> GoalHealthRecord:
        rec = self.health.evaluate_goal_health(goal_id)
        self._publish_event("goal.health.changed", {"goal_id": goal_id, "health_state": rec.health_state.value})
        return rec

    def assess_progress(
        self,
        goal_id: str,
        schedule_variance_days: float = 0.0,
        budget_variance_ratio: float = 0.0,
    ) -> GoalProgressAssessment:
        ass = self.progress.assess_progress(
            goal_id,
            schedule_variance_days=schedule_variance_days,
            budget_variance_ratio=budget_variance_ratio,
        )
        self._publish_event("goal.progress.updated", {
            "goal_id": goal_id,
            "reported": ass.reported_task_progress,
            "verified": ass.verified_outcome_progress,
        })
        return ass

    def generate_corrective_proposals(self, goal_id: str) -> List[CorrectiveActionProposal]:
        props = self.corrective.generate_corrective_proposals(goal_id)
        for p in props:
            self._publish_event("goal.corrective_action.proposed", {"goal_id": goal_id, "proposal_id": p.proposal_id})
        return props

    def approve_corrective_action(self, proposal_id: str, approver: str, token: str) -> CorrectiveActionProposal:
        act = self.corrective.approve_corrective_action(proposal_id, approver, token)
        self._publish_event("goal.corrective_action.approved", {"proposal_id": proposal_id, "approved_by": approver})
        return act


# Global singleton instance
goal_intelligence_service = GoalExecutionIntelligenceOrchestrator()
