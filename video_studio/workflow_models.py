"""OMNIA Video Studio — Workflow Automation, Batch Operations & Editor Macro Models (Module 39).

Defines authoritative domain models for:
- WorkflowExecutionState: Lifecycle of an automation instance:
  DRAFT, VALIDATING, READY, QUEUED, RUNNING, WAITING_FOR_APPROVAL, PAUSED, COMPLETED, FAILED, CANCELLING, CANCELLED
- StepTypeID: Typed catalog of supported automation steps:
  * MEDIA_PROBE: Deep metadata and structural analysis
  * SCENE_ANALYSIS: Shot detection and composition classification (Module 35)
  * TRANSCODE_MEDIA: Media conform and derivative transcode (Module 19)
  * QUALITY_CONTROL: Delivery compliance and technical QC checks (Module 37)
  * TIMELINE_EDIT: Atomic timeline command execution (Modules 4–5)
  * EXPORT_SEQUENCE: Render and export sequence to deliverable (Module 17)
  * PROJECT_PACKAGE: Portable project packaging and archiving (Module 38)
  * USER_APPROVAL: Explicit human gate blocking downstream steps until approved
- StepFailurePolicy: STOP_ON_FAILURE, CONTINUE_ON_FAILURE
- WorkflowStepDefinition: Schema describing a step's inputs, dependencies, timeouts, retries, and requirements
- WorkflowDefinition: Versioned, reusable workflow DAG blueprint with schemas and metadata
- WorkflowStepExecutionState: Runtime progress, inputs, outputs, errors, and retry counter for a step
- WorkflowExecutionInstance: Stateful run instance tracking overall execution progress, logs, and artifacts
- BatchJobDefinition: Batch execution over multiple target media assets or sequences
- BatchExecutionResult: Per-item outcome and failure isolation summary
"""

import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set


WORKFLOW_SCHEMA_VERSION = "video-studio.workflow.v1"


class WorkflowExecutionState(str, Enum):
    """Execution lifecycle state of a workflow instance."""
    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    READY = "READY"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"


class StepTypeID(str, Enum):
    """Registered, verified workflow step type identifiers."""
    MEDIA_PROBE = "media.probe"
    SCENE_ANALYSIS = "video.scene_analysis"
    TRANSCODE_MEDIA = "media.transcode"
    QUALITY_CONTROL = "media.quality_control"
    TIMELINE_COMMAND = "timeline.command"
    EXPORT_SEQUENCE = "video.export"
    PROJECT_PACKAGE = "project.package"
    USER_APPROVAL = "workflow.user_approval"


class StepFailurePolicy(str, Enum):
    """Behavior when an individual step fails."""
    STOP_ON_FAILURE = "STOP_ON_FAILURE"
    CONTINUE_ON_FAILURE = "CONTINUE_ON_FAILURE"


@dataclass
class WorkflowStepDefinition:
    """Configured step specification inside a workflow blueprint."""
    step_id: str
    step_type: StepTypeID
    name: str = "Workflow Step"
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)  # step_ids that must complete first
    failure_policy: StepFailurePolicy = StepFailurePolicy.STOP_ON_FAILURE
    timeout_seconds: float = 300.0
    max_retries: int = 0
    requires_approval: bool = False
    condition_expression: Optional[str] = None  # e.g., "qc.status == 'PASS'"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "step_type": self.step_type.value,
            "name": self.name,
            "description": self.description,
            "parameters": dict(self.parameters),
            "dependencies": list(self.dependencies),
            "failure_policy": self.failure_policy.value,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "requires_approval": self.requires_approval,
            "condition_expression": self.condition_expression,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowStepDefinition":
        return cls(
            step_id=data["step_id"],
            step_type=StepTypeID(data["step_type"]),
            name=data.get("name", "Workflow Step"),
            description=data.get("description", ""),
            parameters=dict(data.get("parameters", {})),
            dependencies=list(data.get("dependencies", [])),
            failure_policy=StepFailurePolicy(data.get("failure_policy", StepFailurePolicy.STOP_ON_FAILURE.value)),
            timeout_seconds=float(data.get("timeout_seconds", 300.0)),
            max_retries=int(data.get("max_retries", 0)),
            requires_approval=bool(data.get("requires_approval", False)),
            condition_expression=data.get("condition_expression"),
        )


@dataclass
class WorkflowDefinition:
    """Reusable, versioned workflow specification blueprint."""
    workflow_id: str = field(default_factory=lambda: f"wf_{uuid.uuid4().hex[:10]}")
    name: str = "Standard Workflow"
    description: str = ""
    revision: int = 1
    schema_version: str = WORKFLOW_SCHEMA_VERSION
    project_id: str = "default_project"
    steps: List[WorkflowStepDefinition] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "revision": self.revision,
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "step_count": len(self.steps),
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowDefinition":
        return cls(
            workflow_id=data.get("workflow_id", f"wf_{uuid.uuid4().hex[:10]}"),
            name=data.get("name", "Standard Workflow"),
            description=data.get("description", ""),
            revision=int(data.get("revision", 1)),
            schema_version=data.get("schema_version", WORKFLOW_SCHEMA_VERSION),
            project_id=data.get("project_id", "default_project"),
            steps=[WorkflowStepDefinition.from_dict(s) for s in data.get("steps", [])],
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
        )


@dataclass
class WorkflowStepExecutionState:
    """Runtime execution record for a single step within a workflow instance."""
    step_id: str
    step_type: StepTypeID
    state: WorkflowExecutionState = WorkflowExecutionState.READY
    retry_count: int = 0
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    is_approved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "step_type": self.step_type.value,
            "state": self.state.value,
            "retry_count": self.retry_count,
            "duration": round(float(self.end_time - self.start_time), 3) if self.start_time and self.end_time else None,
            "outputs": dict(self.outputs),
            "error": self.error,
            "is_approved": self.is_approved,
        }


@dataclass
class WorkflowExecutionInstance:
    """Active or historical run instance of a workflow."""
    run_id: str = field(default_factory=lambda: f"run_{uuid.uuid4().hex[:10]}")
    workflow_id: str = ""
    workflow_revision: int = 1
    project_id: str = "default_project"
    state: WorkflowExecutionState = WorkflowExecutionState.READY
    progress: float = 0.0  # 0.0 to 1.0
    step_states: Dict[str, WorkflowStepExecutionState] = field(default_factory=dict)
    execution_context: Dict[str, Any] = field(default_factory=dict)  # Shared data across steps
    logs: List[str] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    error: Optional[str] = None

    def log(self, message: str) -> None:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        self.logs.append(f"[{ts}] {message}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "workflow_revision": self.workflow_revision,
            "project_id": self.project_id,
            "state": self.state.value,
            "progress": round(float(self.progress), 3),
            "duration": round(float((self.end_time or time.time()) - self.start_time), 3),
            "step_states": {sid: s.to_dict() for sid, s in self.step_states.items()},
            "error": self.error,
            "log_count": len(self.logs),
        }


@dataclass
class BatchExecutionResult:
    """Summary of batch processing over multiple targets."""
    batch_id: str = field(default_factory=lambda: f"btc_{uuid.uuid4().hex[:10]}")
    total_items: int = 0
    completed_items: int = 0
    failed_items: int = 0
    item_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # target_id -> result
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "total_items": self.total_items,
            "completed_items": self.completed_items,
            "failed_items": self.failed_items,
            "duration_seconds": round(float(self.duration_seconds), 3),
            "item_results": dict(self.item_results),
        }
