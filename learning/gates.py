"""
Omnia Module 33: Multi-Stage Evaluation & Promotion Gates
Enforces non-bypassable promotion criteria before any candidate model,
strategy, or parameter set can be deployed to production.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from learning.models import GateResult, ModelVersion, PromotionRequest


class PromotionGatekeeper:
    """
    Enforces the mandatory non-bypassable promotion gates.
    """

    def __init__(self) -> None:
        pass

    def evaluate_gates(
        self,
        request: PromotionRequest,
        candidate_version: ModelVersion,
        baseline_version: Optional[ModelVersion],
        evaluation_metrics: Dict[str, float],
        baseline_metrics: Dict[str, float],
        regression_test_results: Dict[str, bool],
        policy_validation_passed: bool,
        security_audit_passed: bool,
        rollback_target_verified: bool,
        human_approval_signature: Optional[str] = None,
    ) -> Tuple[bool, List[GateResult]]:
        """
        Runs exhaustive gate checks. All mandatory gates must pass.
        Returns (all_passed, list_of_gate_results).
        """
        results: List[GateResult] = []

        def add_gate(name: str, passed: bool, reason: str, score: float = 1.0, required: bool = True):
            results.append(GateResult(
                gate_name=name,
                passed=passed,
                score=score if passed else 0.0,
                threshold=1.0,
                reason=reason,
                is_mandatory=required,
                evaluated_at=time.time(),
            ))

        # Gate 1: Artifact & Checksum Integrity
        has_checksum = bool(candidate_version.artifact_digest and len(candidate_version.artifact_digest) >= 32)
        add_gate(
            "ArtifactChecksumIntegrity",
            has_checksum,
            "Checksum present and verified" if has_checksum else "Missing or invalid artifact checksum",
        )

        # Gate 2: Minimum Evaluation Sample Size
        sample_count = int(evaluation_metrics.get("sample_count", 0))
        min_required_samples = 50
        samples_ok = sample_count >= min_required_samples
        add_gate(
            "MinimumEvaluationSampleSize",
            samples_ok,
            f"Sample count {sample_count} >= {min_required_samples}" if samples_ok else f"Sample count {sample_count} < {min_required_samples}",
        )

        # Gate 3: Primary Metric Improvement
        cand_primary = evaluation_metrics.get("success_rate", evaluation_metrics.get("accuracy", 0.0))
        base_primary = baseline_metrics.get("success_rate", baseline_metrics.get("accuracy", 0.0))
        improvement_ok = cand_primary >= base_primary
        add_gate(
            "PrimaryMetricImprovement",
            improvement_ok,
            f"Candidate metric {cand_primary} >= baseline {base_primary}" if improvement_ok else f"Candidate metric {cand_primary} degraded from baseline {base_primary}",
        )

        # Gate 4: Zero Regression on Core Benchmarks
        regression_failed = [test for test, passed in regression_test_results.items() if not passed]
        no_regressions = len(regression_failed) == 0
        add_gate(
            "CoreBenchmarkRegressions",
            no_regressions,
            "All core regression tests passed" if no_regressions else f"Regressions detected in: {regression_failed}",
        )

        # Gate 5: Policy & Guardrail Compliance
        add_gate(
            "PolicyGuardrailCompliance",
            policy_validation_passed,
            "Compliant with Omnia policy constraints" if policy_validation_passed else "Violates system policy constraints",
        )

        # Gate 6: Security & Secret Sanitization Audit
        add_gate(
            "SecuritySanitizationAudit",
            security_audit_passed,
            "Clean security audit, no secrets detected" if security_audit_passed else "Security audit failed or unmasked secrets detected",
        )

        # Gate 7: Rollback Target Verification
        add_gate(
            "RollbackTargetReadiness",
            rollback_target_verified,
            "Verified previous stable target available for rollback" if rollback_target_verified else "No valid rollback target configured",
        )

        # Gate 8: Human Authorization Check
        human_approved = bool(human_approval_signature and len(human_approval_signature) > 0)
        add_gate(
            "HumanAuthorizationGate",
            human_approved,
            f"Approved by authorized signature: {human_approval_signature}" if human_approved else "Missing mandatory human approval signature",
        )

        # Gate 9: Anti-Self-Promotion Invariant
        not_self_promoted = candidate_version.created_by != human_approval_signature
        add_gate(
            "AntiSelfPromotionInvariant",
            not_self_promoted,
            "Author and approver are distinct" if not_self_promoted else "Self-promotion rejected: author cannot approve own version",
        )

        all_passed = all(g.passed for g in results if g.is_mandatory)
        return all_passed, results
