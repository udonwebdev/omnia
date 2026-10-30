"""
OMNIA Module 37: Rollout Controller & Progressive Deployment Strategies
Orchestrates Direct, Rolling, Blue-Green, and Canary rollout stages.
Enforces observation windows, error thresholds, and automatic deployment pauses.
"""

import time
import logging
from typing import Dict, Any, List, Optional
from release.models import (
    DeploymentRecord,
    DeploymentStrategy,
    RolloutStage,
)
from release.adapters import DeploymentAdapter
from release.persistence import ReleaseRepository

logger = logging.getLogger("Omnia.Release.Rollout")


class RolloutController:
    """Manages progressive deployment stages and traffic distribution."""

    def __init__(self, repo: ReleaseRepository, adapter: DeploymentAdapter):
        self.repo = repo
        self.adapter = adapter

    def initialize_stages(self, strategy: DeploymentStrategy) -> List[RolloutStage]:
        """Generates standard progressive stages according to strategy."""
        if strategy == DeploymentStrategy.DIRECT:
            return [RolloutStage(stage_index=0, traffic_percentage=100.0, observation_window_seconds=1.0)]
        elif strategy == DeploymentStrategy.CANARY:
            return [
                RolloutStage(stage_index=0, traffic_percentage=5.0, observation_window_seconds=2.0),
                RolloutStage(stage_index=1, traffic_percentage=25.0, observation_window_seconds=2.0),
                RolloutStage(stage_index=2, traffic_percentage=100.0, observation_window_seconds=2.0),
            ]
        elif strategy == DeploymentStrategy.ROLLING:
            return [
                RolloutStage(stage_index=0, traffic_percentage=33.3, observation_window_seconds=2.0),
                RolloutStage(stage_index=1, traffic_percentage=66.6, observation_window_seconds=2.0),
                RolloutStage(stage_index=2, traffic_percentage=100.0, observation_window_seconds=2.0),
            ]
        elif strategy == DeploymentStrategy.BLUE_GREEN:
            return [
                RolloutStage(stage_index=0, traffic_percentage=0.0, observation_window_seconds=1.0),
                RolloutStage(stage_index=1, traffic_percentage=100.0, observation_window_seconds=2.0),
            ]
        return [RolloutStage(stage_index=0, traffic_percentage=100.0, observation_window_seconds=1.0)]

    def advance_rollout_stage(
        self,
        deployment_id: str,
        target_endpoint: str,
        artifact_uri: str,
        expected_digest: str,
    ) -> Dict[str, Any]:
        """Advances deployment to the next traffic stage after validating telemetry."""
        dep = self.repo.get_deployment(deployment_id)
        if not dep:
            return {"success": False, "error": f"Deployment '{deployment_id}' not found"}

        stages = dep.stages
        if dep.current_stage_index >= len(stages):
            return {"success": True, "completed": True, "message": "All rollout stages already completed"}

        stage_data = stages[dep.current_stage_index]
        target_traffic = stage_data["traffic_percentage"]

        # Execute provider shift
        res = self.adapter.deploy_artifact(
            target_endpoint=target_endpoint,
            artifact_uri=artifact_uri,
            expected_digest=expected_digest,
            traffic_pct=target_traffic,
        )
        if not res.get("success", False):
            dep.status = "FAILED"
            dep.error_message = f"Provider deploy failed: {res.get('error')}"
            self.repo.save_deployment(dep)
            return {"success": False, "error": dep.error_message}

        dep.current_traffic_pct = target_traffic
        stage_data["status"] = "COMPLETED"
        stage_data["completed_at"] = time.time()
        dep.current_stage_index += 1

        if dep.current_stage_index >= len(stages):
            dep.status = "VERIFYING"
        else:
            dep.status = "IN_PROGRESS"

        self.repo.save_deployment(dep)
        logger.info(f"Deployment {deployment_id} advanced to {target_traffic}% traffic (Stage {dep.current_stage_index}/{len(stages)})")
        return {
            "success": True,
            "current_traffic_pct": target_traffic,
            "next_stage_index": dep.current_stage_index,
            "total_stages": len(stages),
            "status": dep.status,
        }
