"""OMNIA Video Studio — Module 44 Tests: Render Pipeline Orchestration & Fault Recovery.

Comprehensive test suite verifying:
1. Render job creation, stable revision snapshot capture, and temp path setup.
2. Validated state transitions across the full lifecycle (CREATED -> VALIDATING -> QUEUED -> SCHEDULED -> PREPARING -> RENDERING -> FINALIZING -> VERIFYING -> COMPLETED).
3. Rejection of illegal state transitions (e.g. jumping from CREATED to COMPLETED directly).
4. Preflight validation enforcing online conform requirements when targeting ORIGINAL media.
5. Worker capability matching and priority queue scheduling.
6. Concurrency limits: worker load tracking and bounded dispatch.
7. Output artifact verification: validates size, readability, and content SHA-256 fingerprint.
8. Atomic publication: moves verified output safely to destination path.
9. Transient versus permanent failure classification.
10. Retry behavior: re-queueing transient failures and rejecting permanent ones.
11. User-requested cancellation and clean temporary file deletion.
12. Capability registration in VideoStudioCapabilityRegistry under RENDERING and EXPORT categories.
"""

import os
import tempfile
import unittest
from typing import Any
from video_studio.conform_models import MediaRepresentationMode
from video_studio.conform_service import ConformService
from video_studio.export_engine import ExportEngine
from video_studio.export_models import ExportConfig, ExportValidationReport
from video_studio.media_library import ProjectMediaLibrary, MediaAsset, AssetMediaType
from video_studio.orchestration_engine import OrchestrationEngine
from video_studio.orchestration_models import (
    FailureClassification,
    OrchestratedRenderState,
    RenderOrchestrationJob,
    RenderWorkerDescriptor,
)
from video_studio.orchestration_service import RenderOrchestrationService
from video_studio.registry import VideoStudioCapabilityRegistry
from video_studio.registry_models import ImplementationState, VideoStudioCategory
from video_studio.timeline_models import (
    SequenceSettings,
    TimelineItemModel,
    TimelineRange,
    TimelineTrackModel,
    TimelineTrackType,
    VideoSequence,
)
from video_studio.timeline_service import TimelineService
from video_studio.versioning_service import VersionControlService


class FakeExportEngine:
    def __init__(self, succeed: bool = True, error_msg: str = ""):
        self.succeed = succeed
        self.error_msg = error_msg

    def render_sequence_to_file(self, job: Any, sequence: VideoSequence) -> ExportValidationReport:
        if not self.succeed:
            return ExportValidationReport(is_valid=False, file_path=job.output_path, error_message=self.error_msg)
        
        # Write dummy output bytes to output_path
        with open(job.output_path, "wb") as f:
            f.write(b"RENDERED_FINAL_OUTPUT_STREAM_BYTES_VALID_VIDEO_1080P")

        return ExportValidationReport(
            is_valid=True,
            file_path=job.output_path,
            file_size_bytes=os.path.getsize(job.output_path),
            duration_seconds=5.0,
            detected_width=1920,
            detected_height=1080,
            detected_fps=24.0,
            has_video_stream=True,
        )


class FakeMediaLibraryRegistry:
    def __init__(self):
        self._libs = {}

    def get_or_create(self, project_id: str):
        if project_id not in self._libs:
            self._libs[project_id] = ProjectMediaLibrary(project_id)
        return self._libs[project_id]


class TestVideoStudioModule44Orchestration(unittest.TestCase):
    """Test suite for Module 44 Render Pipeline Orchestration & Fault Recovery."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.audit_log = os.path.join(self.temp_dir.name, "test_orch_audit.jsonl")
        self.registry = VideoStudioCapabilityRegistry()
        self.tl_service = TimelineService()
        self.media_registry = FakeMediaLibraryRegistry()
        self.fake_export_engine = FakeExportEngine(succeed=True)

        self.versioning_svc = VersionControlService(
            capability_registry=self.registry,
            tl_service=self.tl_service,
            media_registry=self.media_registry,
            audit_log_path=self.audit_log,
        )

        self.conform_svc = ConformService(
            capability_registry=self.registry,
            tl_service=self.tl_service,
            media_registry=self.media_registry,
            versioning_svc=self.versioning_svc,
            audit_log_path=self.audit_log,
        )

        self.service = RenderOrchestrationService(
            capability_registry=self.registry,
            tl_service=self.tl_service,
            conf_service=self.conform_svc,
            versioning_svc=self.versioning_svc,
            exp_engine=self.fake_export_engine,
            audit_log_path=self.audit_log,
            max_concurrent_jobs=1,
        )

        self.project_id = "prj_render_orch"
        self.seq = self.tl_service.create_sequence(
            project_id=self.project_id,
            name="Orchestration Sequence",
        )
        self.seq.duration_frames = 120

        self.dest_file = os.path.join(self.temp_dir.name, "final_master_render.mp4")

    def tearDown(self) -> None:
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_01_job_creation_and_snapshot_pinning(self) -> None:
        """Verifies job creation pins a stable revision snapshot and temporary output file."""
        job = self.service.create_orchestrated_job(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            output_path=self.dest_file,
            config=ExportConfig(),
        )
        self.assertIsNotNone(job.job_id)
        self.assertEqual(job.state, OrchestratedRenderState.CREATED)
        self.assertIsNotNone(job.revision_id)
        self.assertTrue(os.path.exists(job.temp_output_path))

    def test_02_illegal_state_transition_rejection(self) -> None:
        """Verifies state machine rejects illegal state jumps."""
        job = self.service.create_orchestrated_job(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            output_path=self.dest_file,
            config=ExportConfig(),
        )
        # Cannot jump from CREATED directly to COMPLETED
        with self.assertRaises(ValueError):
            job.transition_to(OrchestratedRenderState.COMPLETED)

        # Valid transition: CREATED -> VALIDATING
        job.transition_to(OrchestratedRenderState.VALIDATING)
        self.assertEqual(job.state, OrchestratedRenderState.VALIDATING)

    def test_03_preflight_validation_and_queueing(self) -> None:
        """Verifies preflight validation marks job QUEUED on success."""
        job = self.service.create_orchestrated_job(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            output_path=self.dest_file,
            config=ExportConfig(),
        )
        ok, errs = self.service.validate_job(job.job_id)
        self.assertTrue(ok)
        self.assertEqual(job.state, OrchestratedRenderState.QUEUED)

    def test_04_preflight_blocks_on_conform_issues(self) -> None:
        """Verifies preflight validation blocks export if sequence is in PROXY mode."""
        # Set sequence to PROXY mode in conform service
        self.conform_svc._sequence_modes[self.seq.sequence_id] = MediaRepresentationMode.PROXY

        job = self.service.create_orchestrated_job(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            output_path=self.dest_file,
            config=ExportConfig(),
            representation_mode=MediaRepresentationMode.ORIGINAL,
        )
        ok, errs = self.service.validate_job(job.job_id)
        self.assertFalse(ok)
        self.assertEqual(job.state, OrchestratedRenderState.FAILED)
        self.assertEqual(job.failure_type, FailureClassification.PERMANENT)

    def test_05_worker_capability_and_scheduling(self) -> None:
        """Verifies scheduling selects available worker and advances state to SCHEDULED."""
        job = self.service.create_orchestrated_job(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            output_path=self.dest_file,
            config=ExportConfig(),
        )
        self.service.validate_job(job.job_id)

        scheduled = self.service.schedule_next_job()
        self.assertIsNotNone(scheduled)
        self.assertEqual(scheduled.job_id, job.job_id)
        self.assertEqual(scheduled.state, OrchestratedRenderState.SCHEDULED)
        self.assertEqual(scheduled.assigned_worker_id, "worker_local_primary")

    def test_06_concurrency_limit_enforcement(self) -> None:
        """Verifies when worker reaches max concurrency, subsequent jobs remain QUEUED."""
        job1 = self.service.create_orchestrated_job(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            output_path=os.path.join(self.temp_dir.name, "out1.mp4"),
            config=ExportConfig(),
            priority=80,
        )
        job2 = self.service.create_orchestrated_job(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            output_path=os.path.join(self.temp_dir.name, "out2.mp4"),
            config=ExportConfig(),
            priority=50,
        )
        self.service.validate_job(job1.job_id)
        self.service.validate_job(job2.job_id)

        # Worker max concurrency is 1 in setUp
        first = self.service.schedule_next_job()
        self.assertEqual(first.job_id, job1.job_id)

        # Second schedule attempt must return None because worker is busy
        second = self.service.schedule_next_job()
        self.assertIsNone(second)
        self.assertEqual(job2.state, OrchestratedRenderState.QUEUED)

    def test_07_full_execution_lifecycle_and_atomic_publish(self) -> None:
        """Verifies complete execution through verification and atomic move to target output."""
        job = self.service.create_orchestrated_job(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            output_path=self.dest_file,
            config=ExportConfig(),
        )
        self.service.validate_job(job.job_id)
        self.service.schedule_next_job()

        ok = self.service.execute_scheduled_job(job.job_id)
        self.assertTrue(ok)
        self.assertEqual(job.state, OrchestratedRenderState.COMPLETED)
        self.assertTrue(job.is_verified)
        self.assertIsNotNone(job.output_sha256)
        self.assertGreater(job.output_size_bytes, 0)

        # Destination file must exist and temp file must be gone
        self.assertTrue(os.path.exists(self.dest_file))
        self.assertFalse(os.path.exists(job.temp_output_path))

    def test_08_cancellation_and_temp_cleanup(self) -> None:
        """Verifies cancelling an active job cleans up temp output and releases worker."""
        job = self.service.create_orchestrated_job(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            output_path=self.dest_file,
            config=ExportConfig(),
        )
        self.service.validate_job(job.job_id)
        self.service.schedule_next_job()

        worker = self.service._workers["worker_local_primary"]
        self.assertEqual(worker.current_active_jobs, 1)

        ok = self.service.cancel_job(job.job_id)
        self.assertTrue(ok)
        self.assertEqual(job.state, OrchestratedRenderState.CANCELLED)
        self.assertEqual(worker.current_active_jobs, 0)
        self.assertFalse(os.path.exists(job.temp_output_path))

    def test_09_failure_classification_transient_vs_permanent(self) -> None:
        """Verifies classifying error strings into TRANSIENT (retryable) vs PERMANENT."""
        t_type = OrchestrationEngine.classify_failure("Connection timed out waiting for worker")
        self.assertEqual(t_type, FailureClassification.TRANSIENT)

        p_type = OrchestrationEngine.classify_failure("File not found at source_raw.mp4")
        self.assertEqual(p_type, FailureClassification.PERMANENT)

    def test_10_retry_transient_failure(self) -> None:
        """Verifies retry resets transiently failed job back to QUEUED."""
        job = self.service.create_orchestrated_job(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            output_path=self.dest_file,
            config=ExportConfig(),
        )
        job.transition_to(OrchestratedRenderState.VALIDATING)
        job.transition_to(OrchestratedRenderState.FAILED)
        job.failure_type = FailureClassification.TRANSIENT
        job.attempt_count = 1

        requeued = self.service.retry_job(job.job_id)
        self.assertTrue(requeued)
        self.assertEqual(job.state, OrchestratedRenderState.QUEUED)

        # Permanent failure cannot retry
        job.transition_to(OrchestratedRenderState.SCHEDULED)
        job.transition_to(OrchestratedRenderState.PREPARING)
        job.transition_to(OrchestratedRenderState.FAILED)
        job.failure_type = FailureClassification.PERMANENT
        self.assertFalse(self.service.retry_job(job.job_id))

    def test_11_output_verification_rejection(self) -> None:
        """Verifies verification rejects missing or empty output files."""
        ghost_path = os.path.join(self.temp_dir.name, "ghost.mp4")
        ok, err, sha, sz = OrchestrationEngine.verify_output_artifact(ghost_path)
        self.assertFalse(ok)
        self.assertIn("missing", err.lower())

        # Empty file
        empty_path = os.path.join(self.temp_dir.name, "empty.mp4")
        with open(empty_path, "wb") as f:
            f.write(b"")
        ok2, err2, sha2, sz2 = OrchestrationEngine.verify_output_artifact(empty_path)
        self.assertFalse(ok2)
        self.assertIn("too small", err2.lower())

    def test_12_registry_capabilities(self) -> None:
        """Verifies all Module 44 capabilities are registered with IMPLEMENTED state."""
        expected = [
            ("video.render.orchestration_lifecycle", VideoStudioCategory.RENDERING),
            ("video.render.worker_scheduling", VideoStudioCategory.RENDERING),
            ("video.render.fault_recovery_and_retry", VideoStudioCategory.RENDERING),
            ("video.render.output_verification_and_publish", VideoStudioCategory.EXPORT),
        ]
        for cap_id, expected_cat in expected:
            cap = self.registry.get(cap_id)
            self.assertIsNotNone(cap, f"Capability '{cap_id}' missing from registry.")
            self.assertEqual(cap.category, expected_cat)
            self.assertEqual(cap.implementation_state, ImplementationState.IMPLEMENTED)


if __name__ == "__main__":
    unittest.main()
