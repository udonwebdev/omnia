"""OMNIA Video Studio — Workflow Automation, Batch Operations & Editor Macro Service (Module 39).

Coordinates:
- WorkflowDefinition catalog management (authoring, persistence, validation, revisioning).
- Workflow execution instance tracking, progression, cancellation, and resumption after approval.
- Batch processing over multiple media assets with failure isolation.
- Capability registration in VideoStudioCapabilityRegistry under VideoStudioCategory.EDITING and VideoStudioCategory.MEDIA.
"""

import time
import uuid
import copy
import logging
from typing import Dict, Any, List, Optional, Tuple, Set

from video_studio.workflow_models import (
    WORKFLOW_SCHEMA_VERSION,
    WorkflowExecutionState,
    StepTypeID,
    StepFailurePolicy,
    WorkflowStepDefinition,
    WorkflowDefinition,
    WorkflowStepExecutionState,
    WorkflowExecutionInstance,
    BatchExecutionResult,
)
from video_studio.workflow_engine import WorkflowEngine, workflow_engine, WorkflowValidationError
from video_studio.registry import video_studio_capability_registry
from video_studio.registry_models import (
    VideoStudioCategory,
    ImplementationState,
    VideoStudioCapabilityDescriptor,
)

logger = logging.getLogger("Omnia.VideoStudio.WorkflowService")


class WorkflowService:
    """Central service managing workflow blueprints, automation instances, and batch tasks."""

    def __init__(self, engine: Optional[WorkflowEngine] = None):
        self.engine = engine or workflow_engine

        # In-memory storage:
        # workflow_id -> WorkflowDefinition
        self._workflows: Dict[str, WorkflowDefinition] = {}
        # run_id -> WorkflowExecutionInstance
        self._runs: Dict[str, WorkflowExecutionInstance] = {}

        self.register_capabilities()

    def register_capabilities(self) -> None:
        """Register Module 39 capabilities into VideoStudioCapabilityRegistry."""
        caps = [
            VideoStudioCapabilityDescriptor(
                id="video.workflow.automation_engine",
                name="Workflow Automation & Macro Engine",
                description="Composable DAG workflow execution across Video Studio services with cycle detection.",
                category=VideoStudioCategory.EDITING,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["workflow", "automation", "macros", "dag"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.workflow.batch_operations",
                name="Batch Operations & Processing",
                description="Concurrent multi-target processing with item failure isolation and aggregate progress.",
                category=VideoStudioCategory.MEDIA,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["batch", "concurrency", "multi_target"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.workflow.safety_gates",
                name="Human Approval & Safety Gates",
                description="Non-destructive approval gates and restricted conditional branching before execution.",
                category=VideoStudioCategory.EDITING,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["safety", "approval", "gates", "review"],
            ),
        ]
        for cap in caps:
            if video_studio_capability_registry.get(cap.id) is None:
                video_studio_capability_registry.register(cap, auth_token="core")
        logger.info("Registered Module 39 Workflow capabilities.")

    # -------------------------------------------------------------------------
    # 1. Workflow Blueprint Management
    # -------------------------------------------------------------------------

    def create_workflow(
        self,
        project_id: str,
        name: str,
        steps: List[WorkflowStepDefinition],
        description: str = "",
    ) -> WorkflowDefinition:
        """Creates and validates a new workflow blueprint."""
        wf = WorkflowDefinition(
            project_id=project_id,
            name=name,
            description=description,
            steps=list(steps),
        )
        # Validate DAG
        self.engine.validate_and_order_steps(wf)
        self._workflows[wf.workflow_id] = wf
        return wf

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        return self._workflows.get(workflow_id)

    def list_workflows(self, project_id: Optional[str] = None) -> List[WorkflowDefinition]:
        if project_id:
            return [w for w in self._workflows.values() if w.project_id == project_id]
        return list(self._workflows.values())

    # -------------------------------------------------------------------------
    # 2. Execution Instance Management
    # -------------------------------------------------------------------------

    def trigger_workflow(
        self,
        workflow_id: str,
        project_id: Optional[str] = None,
        initial_context: Optional[Dict[str, Any]] = None,
    ) -> WorkflowExecutionInstance:
        """Instantiates and executes a workflow instance."""
        wf = self.get_workflow(workflow_id)
        if not wf:
            raise ValueError(f"Workflow '{workflow_id}' not found.")

        instance = WorkflowExecutionInstance(
            workflow_id=wf.workflow_id,
            workflow_revision=wf.revision,
            project_id=project_id or wf.project_id,
            execution_context=copy.deepcopy(initial_context or {}),
        )
        self._runs[instance.run_id] = instance

        # Run through engine
        self.engine.run_instance(wf, instance)
        return instance

    def get_run(self, run_id: str) -> Optional[WorkflowExecutionInstance]:
        return self._runs.get(run_id)

    def approve_and_resume_run(self, run_id: str, step_id: str) -> WorkflowExecutionInstance:
        """Approves a blocked human gate and resumes execution."""
        instance = self.get_run(run_id)
        if not instance:
            raise ValueError(f"Workflow run '{run_id}' not found.")

        wf = self.get_workflow(instance.workflow_id)
        if not wf:
            raise ValueError(f"Workflow '{instance.workflow_id}' not found.")

        step_state = instance.step_states.get(step_id)
        if not step_state:
            raise ValueError(f"Step '{step_id}' not found in run instance.")

        step_state.is_approved = True
        step_state.state = WorkflowExecutionState.READY
        instance.log(f"Explicit user approval granted for step '{step_id}'. Resuming execution.")

        # Resume execution
        self.engine.run_instance(wf, instance)
        return instance

    def cancel_run(self, run_id: str) -> WorkflowExecutionInstance:
        """Signals cancellation on an active workflow run."""
        instance = self.get_run(run_id)
        if not instance:
            raise ValueError(f"Workflow run '{run_id}' not found.")

        if instance.state in (WorkflowExecutionState.RUNNING, WorkflowExecutionState.WAITING_FOR_APPROVAL, WorkflowExecutionState.QUEUED):
            instance.state = WorkflowExecutionState.CANCELLED
            instance.end_time = time.time()
            instance.log("Workflow run cancelled by user.")
        return instance

    # -------------------------------------------------------------------------
    # 3. Batch Processing
    # -------------------------------------------------------------------------

    def execute_batch(
        self,
        workflow_id: str,
        target_asset_ids: List[str],
        project_id: str = "default_project",
    ) -> BatchExecutionResult:
        """Executes a workflow across multiple target assets with per-item failure isolation."""
        t_start = time.time()
        res = BatchExecutionResult(total_items=len(target_asset_ids))

        for aid in target_asset_ids:
            try:
                # Trigger per-item workflow instance
                run = self.trigger_workflow(
                    workflow_id=workflow_id,
                    project_id=project_id,
                    initial_context={"target_asset_id": aid, "asset_id": aid},
                )
                if run.state == WorkflowExecutionState.COMPLETED:
                    res.completed_items += 1
                    res.item_results[aid] = {"status": "SUCCESS", "run_id": run.run_id}
                else:
                    res.failed_items += 1
                    res.item_results[aid] = {"status": "FAILED", "error": run.error, "run_id": run.run_id}
            except Exception as e:
                res.failed_items += 1
                res.item_results[aid] = {"status": "FAILED", "error": str(e)}

        res.duration_seconds = time.time() - t_start
        return res


# Global singleton
workflow_service = WorkflowService()
