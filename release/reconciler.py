"""
OMNIA Module 37: Release Reconciliation Engine
Detects unapproved deployment drift between desired releases and actual running state.
Classifies deviations and applies policy-controlled responses.
"""

import time
import logging
from typing import Dict, Any, List, Optional
from release.adapters import DeploymentAdapter
from release.persistence import ReleaseRepository

logger = logging.getLogger("Omnia.Release.Reconciler")


class ReleaseReconciler:
    """Detects and reports environment drift without destructive unapproved overwrites."""

    def __init__(self, repo: ReleaseRepository, adapter: DeploymentAdapter):
        self.repo = repo
        self.adapter = adapter

    def reconcile_environment(self, environment_id: str) -> Dict[str, Any]:
        """Compares desired release state against actual provider state."""
        env = self.repo.get_environment(environment_id)
        if not env:
            return {"drift_detected": False, "error": f"Environment '{environment_id}' not found"}

        actual_state = self.adapter.inspect_actual_state(env.target_endpoint)
        if not actual_state.get("active", False):
            return {
                "environment_id": environment_id,
                "drift_detected": True,
                "drift_type": "TARGET_UNREACHABLE",
                "details": "Target endpoint did not respond or has no active release",
            }

        actual_digest = actual_state.get("digest_sha256")
        expected_digest = env.current_artifact_digest

        if expected_digest and actual_digest != expected_digest:
            logger.warning(f"DEPLOYMENT DRIFT DETECTED on environment '{environment_id}'! Expected digest {expected_digest[:16]}, found {actual_digest[:16] if actual_digest else 'None'}")
            return {
                "environment_id": environment_id,
                "drift_detected": True,
                "drift_type": "ARTIFACT_DIGEST_MISMATCH",
                "expected_digest": expected_digest,
                "actual_digest": actual_digest,
                "recommendation": "Investigate unapproved manual deployment or restore approved release.",
            }

        return {
            "environment_id": environment_id,
            "drift_detected": False,
            "status": "IN_SYNC",
            "current_release_id": env.current_release_id,
            "digest_sha256": actual_digest,
        }
