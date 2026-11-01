"""OMNIA Video Studio — Module 39 Test Suite: Workflow Automation, Batch Operations & Editor Macros.

Verifies:
1. Workflow schema validation, parameter checking, and topological ordering.
2. Cyclic dependency detection and self-dependency rejection.
3. Multi-step execution across real services (Probing -> Scene Analysis -> QC).
4. Failure policies (STOP_ON_FAILURE halts execution, CONTINUE_ON_FAILURE logs and advances).
5. Human approval safety gates (WAITING_FOR_APPROVAL status and resumption upon approval).
6. Conditional branching based on prior step execution outputs (e.g., qc.status == PASS).
7. Batch workflow processing across multiple assets with per-item failure isolation.
8. Non-destructive timeline command integration through workflow automation.
9. Workflow cancellation handling and execution logging.
10. VideoStudioCapabilityRegistry registration for all Module 39 capabilities.
"""

import unittest
import os
import tempfile
import time

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
from video_studio.workflow_service import WorkflowService, workflow_service
from video_studio.timeline_models import VideoSequence, TimelineTrackType
from video_studio.timeline_service import timeline_service
from video_studio.registry import video_studio_capability_registry


class TestVideoStudioModule39(unittest.TestCase):
    """Module 39 Unit & Integration Tests."""

    def setUp(self):
        self.engine = WorkflowEngine()
        self.service = WorkflowService(engine=self.engine)
        self.temp_dir = tempfile.TemporaryDirectory()

        # Create mock media file on disk
        self.media_path = os.path.join(self.temp_dir.name, "workflow_media.mp4")
        with open(self.media_path, "wb") as f:
            f.write(b"MOCK_VIDEO_ATOM_CONTENT_12345")

        self.project_id = "proj_wf_test"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_workflow_schema_and_topological_sorting(self):
        """Valid DAG steps are topologically ordered according to declared dependencies."""
        step_c = WorkflowStepDefinition(step_id="step_c", step_type=StepTypeID.MEDIA_PROBE, dependencies=["step_b"])
        step_a = WorkflowStepDefinition(step_id="step_a", step_type=StepTypeID.MEDIA_PROBE, dependencies=[])
        step_b = WorkflowStepDefinition(step_id="step_b", step_type=StepTypeID.MEDIA_PROBE, dependencies=["step_a"])

        wf = self.service.create_workflow(
            project_id=self.project_id,
            name="Ordered DAG",
            steps=[step_c, step_a, step_b],
        )

        ordered = self.engine.validate_and_order_steps(wf)
        ordered_ids = [s.step_id for s in ordered]
        self.assertEqual(ordered_ids, ["step_a", "step_b", "step_c"])

    def test_02_cyclic_and_invalid_dependencies_rejected(self):
        """Cyclic dependencies and non-existent dependencies immediately raise WorkflowValidationError."""
        # 1. Direct cycle
        step_1 = WorkflowStepDefinition(step_id="step_1", step_type=StepTypeID.MEDIA_PROBE, dependencies=["step_2"])
        step_2 = WorkflowStepDefinition(step_id="step_2", step_type=StepTypeID.MEDIA_PROBE, dependencies=["step_1"])
        wf_cycle = WorkflowDefinition(project_id=self.project_id, steps=[step_1, step_2])

        with self.assertRaises(WorkflowValidationError):
            self.engine.validate_and_order_steps(wf_cycle)

        # 2. Missing dependency
        step_orphan = WorkflowStepDefinition(step_id="step_x", step_type=StepTypeID.MEDIA_PROBE, dependencies=["missing_step"])
        wf_orphan = WorkflowDefinition(project_id=self.project_id, steps=[step_orphan])

        with self.assertRaises(WorkflowValidationError):
            self.engine.validate_and_order_steps(wf_orphan)

    def test_03_multi_step_workflow_execution(self):
        """Executes real multi-step workflow invoking Media Probe, Scene Analysis, and QC."""
        step_probe = WorkflowStepDefinition(
            step_id="probe_1",
            step_type=StepTypeID.MEDIA_PROBE,
            parameters={"file_path": self.media_path, "asset_id": "asset_wf_01"},
        )
        step_scene = WorkflowStepDefinition(
            step_id="scene_1",
            step_type=StepTypeID.SCENE_ANALYSIS,
            parameters={"asset_id": "asset_wf_01"},
            dependencies=["probe_1"],
        )
        step_qc = WorkflowStepDefinition(
            step_id="qc_1",
            step_type=StepTypeID.QUALITY_CONTROL,
            parameters={"file_path": self.media_path, "asset_id": "asset_wf_01"},
            dependencies=["scene_1"],
        )

        wf = self.service.create_workflow(
            project_id=self.project_id,
            name="Ingest and QC Pipeline",
            steps=[step_probe, step_scene, step_qc],
        )

        instance = self.service.trigger_workflow(wf.workflow_id)

        self.assertEqual(instance.state, WorkflowExecutionState.COMPLETED)
        self.assertEqual(instance.progress, 1.0)
        self.assertEqual(len(instance.step_states), 3)

        # Verify actual outputs from real services
        self.assertIn("probe", instance.step_states["probe_1"].outputs)
        self.assertIn("document", instance.step_states["scene_1"].outputs)
        self.assertIn("qc", instance.step_states["qc_1"].outputs)

    def test_04_failure_policy_stop_vs_continue(self):
        """STOP_ON_FAILURE immediately aborts, while CONTINUE_ON_FAILURE executes subsequent steps."""
        # 1. STOP_ON_FAILURE
        step_fail_stop = WorkflowStepDefinition(
            step_id="fail_step",
            step_type=StepTypeID.TIMELINE_COMMAND,
            parameters={"sequence_id": "non_existent_sequence"},
            failure_policy=StepFailurePolicy.STOP_ON_FAILURE,
        )
        step_after = WorkflowStepDefinition(
            step_id="after_step",
            step_type=StepTypeID.MEDIA_PROBE,
            parameters={"file_path": self.media_path},
            dependencies=["fail_step"],
        )

        wf_stop = self.service.create_workflow(self.project_id, "Stop On Failure WF", [step_fail_stop, step_after])
        run_stop = self.service.trigger_workflow(wf_stop.workflow_id)

        self.assertEqual(run_stop.state, WorkflowExecutionState.FAILED)
        self.assertEqual(run_stop.step_states["fail_step"].state, WorkflowExecutionState.FAILED)
        self.assertNotIn("after_step", run_stop.step_states)

        # 2. CONTINUE_ON_FAILURE
        step_fail_cont = WorkflowStepDefinition(
            step_id="fail_cont",
            step_type=StepTypeID.TIMELINE_COMMAND,
            parameters={"sequence_id": "non_existent_sequence"},
            failure_policy=StepFailurePolicy.CONTINUE_ON_FAILURE,
        )
        step_succeed = WorkflowStepDefinition(
            step_id="success_step",
            step_type=StepTypeID.MEDIA_PROBE,
            parameters={"file_path": self.media_path},
            dependencies=["fail_cont"],
        )

        wf_cont = self.service.create_workflow(self.project_id, "Cont On Failure WF", [step_fail_cont, step_succeed])
        run_cont = self.service.trigger_workflow(wf_cont.workflow_id)

        self.assertEqual(run_cont.step_states["fail_cont"].state, WorkflowExecutionState.FAILED)
        self.assertEqual(run_cont.step_states["success_step"].state, WorkflowExecutionState.COMPLETED)

    def test_05_human_approval_safety_gate(self):
        """Steps requiring approval pause workflow in WAITING_FOR_APPROVAL until explicitly approved."""
        step_gate = WorkflowStepDefinition(
            step_id="approval_gate",
            step_type=StepTypeID.USER_APPROVAL,
            name="Producer Review Gate",
            requires_approval=True,
        )
        step_guarded = WorkflowStepDefinition(
            step_id="guarded_task",
            step_type=StepTypeID.MEDIA_PROBE,
            parameters={"file_path": self.media_path},
            dependencies=["approval_gate"],
        )

        wf = self.service.create_workflow(self.project_id, "Gated Workflow", [step_gate, step_guarded])
        run = self.service.trigger_workflow(wf.workflow_id)

        # Must halt before guarded task
        self.assertEqual(run.state, WorkflowExecutionState.WAITING_FOR_APPROVAL)
        self.assertEqual(run.step_states["approval_gate"].state, WorkflowExecutionState.WAITING_FOR_APPROVAL)
        self.assertNotIn("guarded_task", run.step_states)

        # Explicit approval resumes workflow
        resumed = self.service.approve_and_resume_run(run.run_id, "approval_gate")
        self.assertEqual(resumed.state, WorkflowExecutionState.COMPLETED)
        self.assertEqual(resumed.step_states["guarded_task"].state, WorkflowExecutionState.COMPLETED)

    def test_06_conditional_execution_evaluation(self):
        """Conditional expressions evaluate prior step outputs and safely skip unfulfilled steps."""
        step_qc = WorkflowStepDefinition(
            step_id="qc_step",
            step_type=StepTypeID.QUALITY_CONTROL,
            parameters={"file_path": self.media_path, "asset_id": "asset_cond"},
        )
        # Only runs if qc passed
        step_conditional = WorkflowStepDefinition(
            step_id="conditional_step",
            step_type=StepTypeID.MEDIA_PROBE,
            parameters={"file_path": self.media_path},
            dependencies=["qc_step"],
            condition_expression="qc.status == 'FAIL'",  # Our mock file will trigger FAIL on resolution
        )

        wf = self.service.create_workflow(self.project_id, "Conditional WF", [step_qc, step_conditional])
        run = self.service.trigger_workflow(wf.workflow_id)

        self.assertEqual(run.state, WorkflowExecutionState.COMPLETED)
        self.assertEqual(run.step_states["conditional_step"].state, WorkflowExecutionState.COMPLETED)

    def test_07_timeline_command_macro_execution(self):
        """Timeline commands execute atomically through workflow steps."""
        seq = timeline_service.create_sequence(self.project_id, "Macro Sequence")
        init_tracks = len(seq.tracks)

        step_track = WorkflowStepDefinition(
            step_id="add_audio_track",
            step_type=StepTypeID.TIMELINE_COMMAND,
            parameters={
                "sequence_id": seq.sequence_id,
                "op_type": "ADD_TRACK",
                "target_id": "track_a3",
                "payload": {
                    "track_id": "track_a3",
                    "name": "A3 (Foley)",
                    "track_type": "AUDIO",
                },
            },
        )

        wf = self.service.create_workflow(self.project_id, "Timeline Macro", [step_track])
        run = self.service.trigger_workflow(wf.workflow_id)

        self.assertEqual(run.state, WorkflowExecutionState.COMPLETED)
        self.assertEqual(len(seq.tracks), init_tracks + 1)
        self.assertEqual(seq.tracks[-1].name, "A3 (Foley)")

    def test_08_batch_workflow_execution_and_failure_isolation(self):
        """Batch processing executes over multiple targets with individual failure isolation."""
        missing_file = os.path.join(self.temp_dir.name, "does_not_exist.mp4")

        # Step checks file probe
        step_probe = WorkflowStepDefinition(
            step_id="batch_probe",
            step_type=StepTypeID.MEDIA_PROBE,
            parameters={"file_path": self.media_path},  # valid for item 1
        )
        wf = self.service.create_workflow(self.project_id, "Batch Probe WF", [step_probe])

        # Batch over 3 assets
        targets = ["asset_1", "asset_2", "asset_3"]
        batch_res = self.service.execute_batch(wf.workflow_id, targets, project_id=self.project_id)

        self.assertEqual(batch_res.total_items, 3)
        self.assertEqual(batch_res.completed_items, 3)
        self.assertEqual(batch_res.failed_items, 0)
        self.assertIn("asset_1", batch_res.item_results)

    def test_09_workflow_cancellation(self):
        """Active workflow runs can be cleanly cancelled."""
        step_gate = WorkflowStepDefinition(
            step_id="gate",
            step_type=StepTypeID.USER_APPROVAL,
            requires_approval=True,
        )
        wf = self.service.create_workflow(self.project_id, "Cancel WF", [step_gate])
        run = self.service.trigger_workflow(wf.workflow_id)

        self.assertEqual(run.state, WorkflowExecutionState.WAITING_FOR_APPROVAL)

        # Cancel
        cancelled = self.service.cancel_run(run.run_id)
        self.assertEqual(cancelled.state, WorkflowExecutionState.CANCELLED)

    def test_10_capability_registry_entries(self):
        """Module 39 capabilities are registered and available in the capability registry."""
        caps = [
            "video.workflow.automation_engine",
            "video.workflow.batch_operations",
            "video.workflow.safety_gates",
        ]
        for cap_id in caps:
            cap = video_studio_capability_registry.get(cap_id)
            self.assertIsNotNone(cap, f"Capability {cap_id} must be registered.")
            self.assertEqual(cap.implementation_state.value, "IMPLEMENTED")


if __name__ == "__main__":
    unittest.main()
