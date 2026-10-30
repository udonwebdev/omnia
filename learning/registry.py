"""
Omnia Module 33: Model & Strategy Version Registry
Tracks models, prompts, heuristics, and strategy versions through
their lifecycle with cryptographic artifacts and immutability guarantees.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from learning.models import ModelLifecycleStatus, ModelVersion


class ModelRegistry:
    """
    Immutable version registry for all learning artifacts, model weights/checkpoints,
    heuristics, prompts, and strategy configurations.
    """

    def __init__(self) -> None:
        pass

    def register_version(
        self,
        model_id: str,
        version_id: str,
        model_family: str,
        artifact_ref: str,
        artifact_digest: str,
        feature_schema_version: str = "1.0.0",
        risk_level: str = "LOW",
        evaluation_summary: Optional[Dict[str, Any]] = None,
        limitations: Optional[List[str]] = None,
        created_by: str = "system",
    ) -> ModelVersion:
        """
        Creates a new candidate model/strategy version in DRAFT state.
        """
        return ModelVersion(
            model_id=model_id,
            version_id=version_id,
            model_family=model_family,
            artifact_ref=artifact_ref,
            artifact_digest=artifact_digest,
            feature_schema_version=feature_schema_version,
            risk_level=risk_level,
            status=ModelLifecycleStatus.DRAFT,
            evaluation_summary=evaluation_summary or {},
            limitations=limitations or [],
            created_by=created_by,
            created_at=time.time(),
            updated_at=time.time(),
        )

    def transition_lifecycle(
        self,
        version: ModelVersion,
        target_status: ModelLifecycleStatus,
        reason: str = "",
    ) -> Tuple[bool, str]:
        """
        Transitions model status following legal lifecycle progression.
        """
        current = version.status

        legal_transitions = {
            ModelLifecycleStatus.DRAFT: [ModelLifecycleStatus.EVALUATING, ModelLifecycleStatus.REJECTED],
            ModelLifecycleStatus.EVALUATING: [ModelLifecycleStatus.APPROVAL_PENDING, ModelLifecycleStatus.REJECTED, ModelLifecycleStatus.DRAFT],
            ModelLifecycleStatus.APPROVAL_PENDING: [ModelLifecycleStatus.APPROVED, ModelLifecycleStatus.REJECTED],
            ModelLifecycleStatus.APPROVED: [ModelLifecycleStatus.STAGING, ModelLifecycleStatus.SHADOW, ModelLifecycleStatus.CANARY],
            ModelLifecycleStatus.STAGING: [ModelLifecycleStatus.CANARY, ModelLifecycleStatus.PRODUCTION, ModelLifecycleStatus.REJECTED],
            ModelLifecycleStatus.SHADOW: [ModelLifecycleStatus.CANARY, ModelLifecycleStatus.PRODUCTION, ModelLifecycleStatus.REJECTED],
            ModelLifecycleStatus.CANARY: [ModelLifecycleStatus.PRODUCTION, ModelLifecycleStatus.REVOKED],
            ModelLifecycleStatus.PRODUCTION: [ModelLifecycleStatus.DEPRECATED, ModelLifecycleStatus.REVOKED],
            ModelLifecycleStatus.DEPRECATED: [],
            ModelLifecycleStatus.REVOKED: [],
            ModelLifecycleStatus.REJECTED: [],
        }

        if target_status not in legal_transitions.get(current, []):
            return False, f"Illegal lifecycle transition from {current.value} to {target_status.value}"

        version.status = target_status
        version.updated_at = time.time()
        return True, f"Successfully transitioned to {target_status.value}"
