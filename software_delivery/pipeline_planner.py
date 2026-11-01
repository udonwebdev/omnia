"""
OMNIA Module 44: Autonomous Software Delivery, CI/CD Intelligence & Release Engineering
Delivery Pipeline Planner - pipeline_planner.py

Generates tailored execution plans based on changed components, language, and release target.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from software_delivery.models import (
    ChangeCategory,
    ChangeImpactReport,
    PipelineDefinition,
    PipelineStageType,
)
from software_delivery.persistence import SoftwareDeliveryRepository

logger = logging.getLogger("Omnia.SoftwareDelivery.PipelinePlanner")


class PipelinePlanner:
    """
    Constructs an execution stage plan matching project topology and detected modifications.
    """

    def __init__(self, repository: Optional[SoftwareDeliveryRepository] = None):
        self.repo = repository or SoftwareDeliveryRepository()

    def create_pipeline_plan(
        self,
        repository_id: str,
        name: str,
        impact_report: ChangeImpactReport,
        target_environment: str = "TESTING",
        pipeline_id: Optional[str] = None,
    ) -> PipelineDefinition:
        stages: List[PipelineStageType] = [
            PipelineStageType.SOURCE_VALIDATION,
            PipelineStageType.CHANGE_ANALYSIS,
        ]

        # Add dependency check if dependencies or configuration changed
        if (
            ChangeCategory.DEPENDENCY in impact_report.change_categories
            or ChangeCategory.CONFIGURATION in impact_report.change_categories
        ):
            stages.append(PipelineStageType.DEPENDENCY_CHECK)

        # Standard lint, build, and unit tests
        stages.extend([
            PipelineStageType.LINT_AND_FORMAT,
            PipelineStageType.BUILD_COMPILE,
            PipelineStageType.UNIT_TEST,
        ])

        # If migrations or security-sensitive components modified, add security & integration tests
        if impact_report.migration_detected or impact_report.security_sensitive or target_environment in ("STAGING", "PRODUCTION"):
            stages.append(PipelineStageType.SECURITY_SCAN)
            stages.append(PipelineStageType.INTEGRATION_TEST)

        # Quality Gate, Artifact Packaging, and Provenance Attestation
        stages.extend([
            PipelineStageType.QUALITY_GATE,
            PipelineStageType.ARTIFACT_PACKAGING,
            PipelineStageType.PROVENANCE_ATTESTATION,
        ])

        # If targeting STAGING or PRODUCTION, prepare deployment handoff
        if target_environment in ("STAGING", "PRODUCTION"):
            stages.append(PipelineStageType.DEPLOYMENT_HANDOFF)

        pid = pipeline_id or f"pipe-{uuid.uuid4().hex[:8]}"
        definition = PipelineDefinition(
            pipeline_id=pid,
            name=name,
            repository_id=repository_id,
            stages=stages,
            triggers=["ON_COMMIT", "MANUAL"],
            environment_variables={"OMNIA_DELIVERY_ENV": target_environment},
        )
        self.repo.save_pipeline_definition(definition)
        logger.info(f"Planned delivery pipeline '{pid}' ({name}) with {len(stages)} stages.")
        return definition
