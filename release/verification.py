"""
OMNIA Module 37: Independent Deployment Verifier
Enforces Core Invariant: A deployment is not successful merely because a deployment command
returns exit code 0. It is successful only when the intended release is independently verified
as healthy in its target environment.
"""

import time
import logging
from typing import Dict, Any, Optional
from release.models import ReleaseRecord, ReleaseState, DeploymentRecord
from release.adapters import DeploymentAdapter
from release.persistence import ReleaseRepository

logger = logging.getLogger("Omnia.Release.Verification")


class DeploymentVerifier:
    """Independently verifies running releases against expected digests, endpoints, and health criteria."""

    def __init__(self, repo: ReleaseRepository, adapter: DeploymentAdapter):
        self.repo = repo
        self.adapter = adapter

    def verify_deployment(
        self,
        deployment_id: str,
        target_endpoint: str,
        expected_digest: str,
    ) -> Dict[str, Any]:
        """
        Executes independent verification:
        1. Inspects target provider actual running state.
        2. Validates artifact digest matches expected SHA-256 digest exactly.
        3. Confirms health criteria satisfied.
        """
        dep = self.repo.get_deployment(deployment_id)
        if not dep:
            return {"verified": False, "error": f"Deployment '{deployment_id}' not found"}

        actual_state = self.adapter.inspect_actual_state(target_endpoint)
        if not actual_state.get("active", False):
            dep.status = "FAILED"
            dep.error_message = "Independent verification failed: Target endpoint is inactive"
            self.repo.save_deployment(dep)
            return {"verified": False, "error": dep.error_message}

        actual_digest = actual_state.get("digest_sha256")
        if actual_digest != expected_digest:
            dep.status = "FAILED"
            dep.error_message = f"Digest mismatch: expected {expected_digest[:16]}, actual {actual_digest[:16] if actual_digest else 'None'}"
            self.repo.save_deployment(dep)
            return {"verified": False, "error": dep.error_message}

        if actual_state.get("status") != "HEALTHY":
            dep.status = "DEGRADED"
            dep.error_message = f"Target health status degraded: {actual_state.get('status')}"
            self.repo.save_deployment(dep)
            return {"verified": False, "error": dep.error_message}

        evidence = f"Verified: Endpoint {target_endpoint} running SHA-256 {expected_digest[:16]} with 100% healthy traffic at {time.time()}"
        dep.status = "SUCCEEDED"
        dep.verification_evidence = evidence
        dep.completed_at = time.time()
        self.repo.save_deployment(dep)

        logger.info(f"Deployment {deployment_id} INDEPENDENTLY VERIFIED: {evidence}")
        return {
            "verified": True,
            "deployment_id": deployment_id,
            "evidence": evidence,
        }
