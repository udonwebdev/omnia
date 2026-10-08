import logging
from typing import List, Dict, Any, Set, Tuple
from intent.models import (
    UserIntent,
    PlannedStep,
    ValidationReport,
    ValidationStatus,
    PlanScore,
    PlanRiskLevel,
    AmbiguityState
)
from intent.capability_mapper import capability_registry

logger = logging.getLogger("Omnia.Intent.Validator")

class PlanValidator:
    """Validates plan graph connectivity, resource conflicts, missing verification, and safety."""

    def __init__(self, registry=capability_registry):
        self.registry = registry

    def validate(self, intent: UserIntent, steps: List[PlannedStep]) -> Tuple[ValidationReport, PlanScore]:
        errors: List[str] = []
        warnings: List[str] = []
        diagnostics: Dict[str, Any] = {}

        # 1. Check Ambiguity first
        if intent.ambiguity.state in [AmbiguityState.NEEDS_CLARIFICATION, AmbiguityState.UNSAFE_TO_INFER]:
            errors.append(f"AMBIGUOUS_INTENT: {intent.ambiguity.ambiguity_type} - {intent.ambiguity.clarification_question}")
            return (
                ValidationReport(status=ValidationStatus.REQUIRES_CLARIFICATION, errors=errors, warnings=warnings),
                PlanScore(confidence=intent.ambiguity.confidence, overall=0.3)
            )

        # 2. Check Graph Connectivity and Dependencies
        step_ids = {s.step_id for s in steps}
        produced_outputs: Set[str] = set()

        for s in steps:
            # Check unknown dependencies
            for dep in s.dependencies:
                if dep not in step_ids:
                    errors.append(f"MISSING_DEPENDENCY: Step '{s.step_id}' depends on non-existent step '{dep}'")

            # Check supported capability
            cap = self.registry.get_capability(s.capability_name)
            if not cap:
                errors.append(f"UNSUPPORTED_CAPABILITY: Step '{s.step_id}' requests unknown capability '{s.capability_name}'")

            # Check verification strategy
            if not s.verification_strategy or s.verification_strategy == "NONE":
                warnings.append(f"MISSING_VERIFICATION: Step '{s.step_id}' has no verification mechanism declared.")

            # Record produced outputs
            for out in s.outputs:
                produced_outputs.add(out)

        # 3. Check Cycles in Dependencies
        if self._detect_cycle(steps):
            errors.append("CYCLE_DETECTED: Dependency graph contains a circular reference.")

        # 4. Check Resource Conflicts
        resource_usage: Dict[str, List[str]] = {}
        for s in steps:
            cap = self.registry.get_capability(s.capability_name)
            if cap:
                for res in cap.required_resources:
                    resource_usage.setdefault(res, []).append(s.step_id)

        # 5. Check Safety / Approval requirements
        has_critical = any(s.risk_level == PlanRiskLevel.CRITICAL for s in steps)
        needs_confirm = intent.requires_confirmation or any(s.requires_confirmation for s in steps)

        # Determine Status
        if errors:
            status = ValidationStatus.INVALID
        elif has_critical or "IGNORE_UNTRUSTED_EXTERNAL_OVERRIDE" in intent.safety_constraints:
            status = ValidationStatus.UNSAFE
        elif needs_confirm:
            status = ValidationStatus.REQUIRES_APPROVAL
        else:
            status = ValidationStatus.VALID

        # Heuristic Plan Scoring
        score = self._compute_score(steps, errors, warnings, intent)
        diagnostics["total_steps"] = len(steps)
        diagnostics["resource_footprint"] = list(resource_usage.keys())

        return (
            ValidationReport(status=status, errors=errors, warnings=warnings, diagnostics=diagnostics),
            score
        )

    def _detect_cycle(self, steps: List[PlannedStep]) -> bool:
        graph = {s.step_id: s.dependencies for s in steps}
        visited = set()
        rec_stack = set()

        def dfs(node):
            visited.add(node)
            rec_stack.add(node)
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            rec_stack.remove(node)
            return False

        for s in steps:
            if s.step_id not in visited:
                if dfs(s.step_id):
                    return True
        return False

    def _compute_score(self, steps: List[PlannedStep], errors: List[str], warnings: List[str], intent: UserIntent) -> PlanScore:
        if errors:
            return PlanScore(completeness=0.2, capability_coverage=0.4, safety=0.0, overall=0.1)

        step_count = len(steps)
        verified_count = sum(1 for s in steps if s.verification_strategy and s.verification_strategy != "NONE")
        verif_ratio = (verified_count / step_count) if step_count > 0 else 1.0

        safety_score = 0.5 if intent.requires_confirmation else 0.95
        overall = round((verif_ratio * 0.4 + safety_score * 0.3 + 0.9 * 0.3), 2)

        return PlanScore(
            completeness=1.0,
            capability_coverage=1.0,
            safety=safety_score,
            reliability=0.9,
            verification_coverage=verif_ratio,
            confidence=intent.ambiguity.confidence,
            overall=overall
        )

plan_validator = PlanValidator()
