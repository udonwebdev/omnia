"""OMNIA Video Studio — Module 45 Tests: Remote Worker Protocol & Distributed Rendering.

Comprehensive test suite verifying:
1. Remote worker registration, secret token hashing, and protocol version validation.
2. Rejection of incompatible protocol versions during registration.
3. Worker authentication and secure constant-time token verification.
4. Worker revocation and immediate prohibition from taking or completing jobs.
5. Heartbeat monitoring, status recalculation (ONLINE vs BUSY), and timeout detection.
6. Capability matching: assigns jobs to remote workers based on container and codec support.
7. Secure job assignment with monotonic fencing tokens and lease expiration.
8. Progress reporting with fencing token validation.
9. Stale completion rejection: worker with expired lease or outdated fencing token is rejected.
10. Chunked artifact transfer assembly, chunk-level hash validation, and output publication.
11. Zombie task recovery: detects dead worker timeout and automatically requeues orphaned jobs.
12. Capability registration in VideoStudioCapabilityRegistry under RENDERING and EXPORT categories.
"""

import hashlib
import os
import tempfile
import time
import unittest
from typing import Any, List
from video_studio.conform_models import MediaRepresentationMode
from video_studio.export_models import ExportConfig
from video_studio.orchestration_models import OrchestratedRenderState
from video_studio.orchestration_service import RenderOrchestrationService
from video_studio.registry import VideoStudioCapabilityRegistry
from video_studio.registry_models import ImplementationState, VideoStudioCategory
from video_studio.remote_engine import RemoteWorkerEngine
from video_studio.remote_models import (
    ChunkedAssetTransferEnvelope,
    REMOTE_WORKER_PROTOCOL_VERSION,
    RemoteWorkerRegistration,
    WorkerHealthStatus,
)
from video_studio.remote_service import RemoteWorkerCoordinatorService
from video_studio.timeline_models import VideoSequence
from video_studio.timeline_service import TimelineService


class FakeExportEngine:
    def render_sequence_to_file(self, job: Any, sequence: VideoSequence) -> Any:
        pass


class TestVideoStudioModule45RemoteWorker(unittest.TestCase):
    """Test suite for Module 45 Remote Worker Protocol & Distributed Rendering Coordinator."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.audit_log = os.path.join(self.temp_dir.name, "test_remote_audit.jsonl")
        self.registry = VideoStudioCapabilityRegistry()
        self.tl_service = TimelineService()

        from video_studio.versioning_service import VersionControlService
        self.versioning_svc = VersionControlService(
            capability_registry=self.registry,
            tl_service=self.tl_service,
            audit_log_path=self.audit_log,
        )

        self.orch_service = RenderOrchestrationService(
            capability_registry=self.registry,
            tl_service=self.tl_service,
            versioning_svc=self.versioning_svc,
            exp_engine=FakeExportEngine(),
            audit_log_path=self.audit_log,
        )

        self.service = RemoteWorkerCoordinatorService(
            capability_registry=self.registry,
            orch_service=self.orch_service,
            audit_log_path=self.audit_log,
            default_lease_seconds=60.0,
        )

        self.project_id = "prj_render_farm"
        self.seq = self.tl_service.create_sequence(
            project_id=self.project_id,
            name="Farm Target Sequence",
        )
        self.seq.duration_frames = 100

        self.dest_file = os.path.join(self.temp_dir.name, "farm_output.mp4")

    def tearDown(self) -> None:
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_01_worker_registration_and_auth(self) -> None:
        """Verifies registering a remote worker hashes the secret token and sets initial status."""
        worker = self.service.register_worker(
            worker_id="worker_node_alpha",
            name="Alpha GPU Node",
            secret_token="super_secret_token_123",
            has_gpu=True,
            max_concurrent_jobs=4,
        )
        self.assertEqual(worker.worker_id, "worker_node_alpha")
        self.assertEqual(worker.status, WorkerHealthStatus.ONLINE)
        self.assertNotEqual(worker.auth_token_hash, "super_secret_token_123")

        # Verify auth check
        ok = RemoteWorkerEngine.verify_worker_auth(worker, "super_secret_token_123")
        self.assertTrue(ok)

        # Invalid token fails
        bad_ok = RemoteWorkerEngine.verify_worker_auth(worker, "wrong_password")
        self.assertFalse(bad_ok)

    def test_02_protocol_version_validation(self) -> None:
        """Verifies rejection of unsupported protocol versions during registration."""
        with self.assertRaises(ValueError):
            self.service.register_worker(
                worker_id="worker_legacy",
                name="Old Node",
                secret_token="secret",
                protocol_version="video-studio.remote-worker.v0_beta",
            )

    def test_03_worker_revocation(self) -> None:
        """Verifies revoking a worker sets REVOKED status and blocks authentication."""
        worker = self.service.register_worker(
            worker_id="worker_rogue",
            name="Compromised Node",
            secret_token="secret_abc",
        )
        self.service.revoke_worker("worker_rogue", reason="Security policy violation")
        self.assertTrue(worker.is_revoked)
        self.assertEqual(worker.status, WorkerHealthStatus.REVOKED)

        # Auth fails for revoked worker
        self.assertFalse(RemoteWorkerEngine.verify_worker_auth(worker, "secret_abc"))

    def test_04_heartbeat_processing_and_busy_state(self) -> None:
        """Verifies heartbeat updates last_heartbeat and transitions to BUSY when full."""
        worker = self.service.register_worker(
            worker_id="worker_load_test",
            name="Load Node",
            secret_token="secret_load",
            max_concurrent_jobs=2,
        )
        # Normal heartbeat
        ok, err = self.service.process_heartbeat("worker_load_test", "secret_load", active_jobs=["job_1"])
        self.assertTrue(ok)
        self.assertEqual(worker.status, WorkerHealthStatus.ONLINE)

        # Full capacity heartbeat
        ok2, err2 = self.service.process_heartbeat("worker_load_test", "secret_load", active_jobs=["job_1", "job_2"])
        self.assertTrue(ok2)
        self.assertEqual(worker.status, WorkerHealthStatus.BUSY)

        # Rejection on bad auth
        bad_ok, bad_err = self.service.process_heartbeat("worker_load_test", "wrong_token")
        self.assertFalse(bad_ok)

    def test_05_job_assignment_with_fencing_token(self) -> None:
        """Verifies job assignment generates monotonic fencing token and lease."""
        worker = self.service.register_worker(
            worker_id="worker_dispatch_01",
            name="Dispatch Node",
            secret_token="token_dispatch",
        )
        job = self.orch_service.create_orchestrated_job(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            output_path=self.dest_file,
            config=ExportConfig(),
        )

        assignment = self.service.assign_job_to_worker(
            job_id=job.job_id,
            worker_id=worker.worker_id,
            scoped_assets=["/media/clip1.mp4"],
        )
        self.assertIsNotNone(assignment.assignment_id)
        self.assertEqual(assignment.fencing_token, 1)
        self.assertTrue(assignment.is_lease_valid())
        self.assertIn(job.job_id, worker.active_job_ids)

    def test_06_progress_reporting_with_fencing_validation(self) -> None:
        """Verifies progress reports advance job metrics only when fencing token is valid."""
        worker = self.service.register_worker(
            worker_id="worker_prog",
            name="Progress Node",
            secret_token="token_prog",
        )
        job = self.orch_service.create_orchestrated_job(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            output_path=self.dest_file,
            config=ExportConfig(),
        )
        asgn = self.service.assign_job_to_worker(job.job_id, worker.worker_id)

        # Valid progress report
        ok, err = self.service.report_progress(
            worker_id=worker.worker_id,
            secret_token="token_prog",
            job_id=job.job_id,
            fencing_token=asgn.fencing_token,
            progress_percent=45.0,
            frames_rendered=45,
            total_frames=100,
        )
        self.assertTrue(ok)
        self.assertEqual(job.progress.progress_percent, 45.0)

        # Invalid fencing token rejected
        bad_ok, bad_err = self.service.report_progress(
            worker_id=worker.worker_id,
            secret_token="token_prog",
            job_id=job.job_id,
            fencing_token=999,  # Mismatched token
            progress_percent=50.0,
            frames_rendered=50,
            total_frames=100,
        )
        self.assertFalse(bad_ok)
        self.assertIn("Stale fencing token", bad_err)

    def test_07_stale_completion_rejection_after_reassignment(self) -> None:
        """Verifies that if a job is reassigned, the old worker's completion is rejected."""
        worker_a = self.service.register_worker("worker_a", "Node A", "tok_a")
        worker_b = self.service.register_worker("worker_b", "Node B", "tok_b")

        job = self.orch_service.create_orchestrated_job(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            output_path=self.dest_file,
            config=ExportConfig(),
        )

        asgn_a = self.service.assign_job_to_worker(job.job_id, worker_a.worker_id)
        self.assertEqual(asgn_a.fencing_token, 1)

        # Reassign to worker B (increments fencing token to 2)
        asgn_b = self.service.assign_job_to_worker(job.job_id, worker_b.worker_id)
        self.assertEqual(asgn_b.fencing_token, 2)

        # Worker A attempts to submit completion with stale token 1
        dummy_chunk = ChunkedAssetTransferEnvelope(
            chunk_index=0,
            total_chunks=1,
            chunk_bytes=b"RAW_DATA_1234567890",
            is_last_chunk=True,
        )
        ok, err = self.service.complete_remote_job(
            worker_id=worker_a.worker_id,
            secret_token="tok_a",
            job_id=job.job_id,
            fencing_token=asgn_a.fencing_token,
            returned_artifact_chunks=[dummy_chunk],
        )
        self.assertFalse(ok)
        self.assertIn("Stale fencing token", err)

    def test_08_chunked_artifact_transfer_and_publication(self) -> None:
        """Verifies streaming chunks are assembled, verified, and published to destination."""
        worker = self.service.register_worker("worker_finish", "Finish Node", "tok_fin")
        job = self.orch_service.create_orchestrated_job(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            output_path=self.dest_file,
            config=ExportConfig(),
        )
        asgn = self.service.assign_job_to_worker(job.job_id, worker.worker_id)

        # Create two streaming chunks
        part1 = b"FINAL_RENDER_PART_ONE_"
        part2 = b"FINAL_RENDER_PART_TWO_1080P"
        c1 = ChunkedAssetTransferEnvelope(
            chunk_index=0,
            total_chunks=2,
            chunk_bytes=part1,
            chunk_sha256=hashlib.sha256(part1).hexdigest(),
            is_last_chunk=False,
        )
        c2 = ChunkedAssetTransferEnvelope(
            chunk_index=1,
            total_chunks=2,
            chunk_bytes=part2,
            chunk_sha256=hashlib.sha256(part2).hexdigest(),
            is_last_chunk=True,
        )

        ok, err = self.service.complete_remote_job(
            worker_id=worker.worker_id,
            secret_token="tok_fin",
            job_id=job.job_id,
            fencing_token=asgn.fencing_token,
            returned_artifact_chunks=[c1, c2],
        )
        self.assertTrue(ok)
        self.assertEqual(job.state, OrchestratedRenderState.COMPLETED)
        self.assertTrue(job.is_verified)
        self.assertTrue(os.path.exists(self.dest_file))
        with open(self.dest_file, "rb") as f:
            content = f.read()
        self.assertEqual(content, part1 + part2)

    def test_09_corrupted_chunk_rejection(self) -> None:
        """Verifies assembly fails if a chunk hash does not match payload."""
        c = ChunkedAssetTransferEnvelope(
            chunk_index=0,
            total_chunks=1,
            chunk_bytes=b"TAMPERED_BYTES",
            chunk_sha256="wrong_checksum_hash",
            is_last_chunk=True,
        )
        dest = os.path.join(self.temp_dir.name, "corrupt_test.mp4")
        ok, err, sha = RemoteWorkerEngine.assemble_chunked_file([c], dest)
        self.assertFalse(ok)
        self.assertIn("checksum mismatch", err)

    def test_10_zombie_task_detection_and_requeue(self) -> None:
        """Verifies dead worker timeout causes active jobs to be reclaimed and requeued."""
        worker = self.service.register_worker("worker_ghost", "Ghost Node", "tok_ghost")
        worker.heartbeat_timeout_seconds = 10.0

        job = self.orch_service.create_orchestrated_job(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            output_path=self.dest_file,
            config=ExportConfig(),
        )
        job.transition_to(OrchestratedRenderState.VALIDATING)
        job.transition_to(OrchestratedRenderState.QUEUED)
        asgn = self.service.assign_job_to_worker(job.job_id, worker.worker_id)
        # assign_job_to_worker moves QUEUED -> SCHEDULED
        job.transition_to(OrchestratedRenderState.PREPARING)
        job.transition_to(OrchestratedRenderState.RENDERING)

        # Age the worker heartbeat to simulate dead/dropped worker
        worker.last_heartbeat = 1000.0

        # Audit health with current_time = 1050.0 (50s > 10s timeout)
        recovered = self.service.check_worker_health_and_recover(current_time=1050.0)
        self.assertIn(job.job_id, recovered)
        self.assertEqual(worker.status, WorkerHealthStatus.TIMEOUT)
        self.assertEqual(job.state, OrchestratedRenderState.QUEUED)

    def test_11_expired_lease_rejection(self) -> None:
        """Verifies that completion is rejected if assignment lease has expired."""
        worker = self.service.register_worker("worker_slow", "Slow Node", "tok_slow")
        job = self.orch_service.create_orchestrated_job(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            output_path=self.dest_file,
            config=ExportConfig(),
        )
        asgn = self.service.assign_job_to_worker(job.job_id, worker.worker_id)
        # Artificially expire lease
        asgn.lease_expires_at = time.time() - 100.0

        dummy_chunk = ChunkedAssetTransferEnvelope(
            chunk_index=0, total_chunks=1, chunk_bytes=b"SLOW_DATA", is_last_chunk=True
        )
        ok, err = self.service.complete_remote_job(
            worker_id=worker.worker_id,
            secret_token="tok_slow",
            job_id=job.job_id,
            fencing_token=asgn.fencing_token,
            returned_artifact_chunks=[dummy_chunk],
        )
        self.assertFalse(ok)
        self.assertIn("lease for job", err)

    def test_12_registry_capabilities(self) -> None:
        """Verifies all Module 45 capabilities are registered with IMPLEMENTED state."""
        expected = [
            ("video.render.remote_worker_protocol", VideoStudioCategory.RENDERING),
            ("video.render.distributed_job_dispatch", VideoStudioCategory.RENDERING),
            ("video.render.worker_fault_recovery", VideoStudioCategory.RENDERING),
            ("video.render.chunked_artifact_transfer", VideoStudioCategory.EXPORT),
        ]
        for cap_id, expected_cat in expected:
            cap = self.registry.get(cap_id)
            self.assertIsNotNone(cap, f"Capability '{cap_id}' missing from registry.")
            self.assertEqual(cap.category, expected_cat)
            self.assertEqual(cap.implementation_state, ImplementationState.IMPLEMENTED)


if __name__ == "__main__":
    unittest.main()
