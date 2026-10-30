"""
OMNIA Module 36: Recovery Verifier
Enforces the mandatory post-remediation verification window.
Invariant: Omnia must never confuse an attempted repair with a verified recovery.
"""

import time
import logging
from typing import Dict, Any, Optional
from observability.models import (
    InfrastructureRemediationAction,
    RecoveryVerificationStatus,
    ComponentHealthStatus,
    RemediationAutonomyLevel,
)
from observability.persistence import ObservabilityRepository
from observability.components import ComponentHealthRegistry
from observability.checks import HealthCheckManager

logger = logging.getLogger("Omnia.Observability.Verification")


class RecoveryVerifier:
    """Verifies that an infrastructure repair actually restored component and dependency health."""

    def __init__(
        self,
        repo: ObservabilityRepository,
        registry: ComponentHealthRegistry,
        checks: HealthCheckManager,
    ):
        self.repo = repo
        self.registry = registry
        self.checks = checks

    def execute_and_verify(
        self,
        action_id: str,
        custom_action_executor: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Executes a planned remediation action and enforces post-repair health verification.
        Refuses to run if Level 4 and approval_token is missing.
        """
        action = self.repo.get_remediation_action(action_id)
        if not action:
            return {"success": False, "error": f"Action ID '{action_id}' not found"}

        # Autonomy check: Level 4 mandates approval
        if int(action.autonomy_level) >= int(RemediationAutonomyLevel.LEVEL_4_APPROVAL_REQUIRED):
            if not action.approval_token:
                action.status = RecoveryVerificationStatus.FAILED
                action.error_message = "Execution blocked: Mandatory human approval token missing"
                self.repo.save_remediation_action(action)
                return {
                    "success": False,
                    "status": action.status.value,
                    "error": action.error_message,
                }

        # Check retry budget
        if action.retry_count >= action.retry_budget:
            action.status = RecoveryVerificationStatus.ESCALATION_REQUIRED
            action.error_message = f"Retry budget of {action.retry_budget} exceeded"
            self.repo.save_remediation_action(action)
            return {
                "success": False,
                "status": action.status.value,
                "error": action.error_message,
            }

        action.status = RecoveryVerificationStatus.IN_PROGRESS
        action.executed_at = time.time()
        action.retry_count += 1
        self.repo.save_remediation_action(action)

        # Step 1: Execute the repair action
        execution_success = True
        exec_err = None
        if custom_action_executor:
            try:
                res = custom_action_executor()
                execution_success = bool(res.get("success", True))
                exec_err = res.get("error")
            except Exception as e:
                execution_success = False
                exec_err = str(e)
        else:
            # Default mock handler for tests/simulation: assumes execution succeeded
            execution_success = True

        if not execution_success:
            action.status = RecoveryVerificationStatus.FAILED
            action.error_message = f"Remediation action execution failed: {exec_err}"
            self.repo.save_remediation_action(action)
            return {
                "success": False,
                "status": action.status.value,
                "error": action.error_message,
            }

        # Step 2: Transition to VERIFICATION_PENDING
        action.status = RecoveryVerificationStatus.VERIFICATION_PENDING
        self.repo.save_remediation_action(action)

        # Step 3: Run health checks to verify actual recovery
        check_results = self.checks.run_component_checks(action.target_component_id)
        all_passed = True
        failure_messages = []
        for cr in check_results:
            if not cr.get("passed", False):
                all_passed = False
                failure_messages.append(f"{cr.get('name')}: {cr.get('message')}")

        target_comp = self.registry.get_component(action.target_component_id)
        is_healthy = target_comp and target_comp.current_status == ComponentHealthStatus.HEALTHY

        if all_passed and is_healthy:
            action.status = RecoveryVerificationStatus.VERIFIED_RECOVERED
            action.verified_at = time.time()
            action.verification_evidence = (
                f"Component '{action.target_component_id}' health verified: "
                f"{len(check_results)} checks passed, status is HEALTHY."
            )
            self.repo.save_remediation_action(action)
            logger.info(f"Remediation {action_id} VERIFIED RECOVERED for '{action.target_component_id}'")
            return {
                "success": True,
                "status": action.status.value,
                "evidence": action.verification_evidence,
                "check_results": check_results,
            }
        else:
            action.status = RecoveryVerificationStatus.FAILED
            action.error_message = (
                f"Health checks failed post-remediation: {'; '.join(failure_messages) if failure_messages else 'Component status is not HEALTHY'}"
            )
            self.repo.save_remediation_action(action)
            logger.warning(f"Remediation {action_id} FAILED post-check verification")
            return {
                "success": False,
                "status": action.status.value,
                "error": action.error_message,
                "check_results": check_results,
            }
