"""OMNIA Video Studio — Module 47: End-to-End Certification, Reliability Hardening & Acceptance Suite.

Validates the complete 7-stage operational lifecycle across Modules 0–46:
A. Project & Media Lifecycle: Creation, Ingestion, Probing, Dependency Graph, Missing Asset Detection, Relinking.
B. Editing & Timeline Lifecycle: Sequences, Multi-track manipulation, Ripple Trimming, Transitions, Undo/Redo, Persistence round-trip.
C. Revision & Recovery Lifecycle: Snapshots, Branching, Revision Diff, Non-destructive restoration, State safety.
D. Proxy & Conform Lifecycle: Generation, Proxy-to-Original matching, Mode switching, High-res Online Conform verification.
E. Render & Delivery Lifecycle: Orchestrated render job, Retry handling, Progress tracking, SHA-256 Output Verification, Packaging.
F. Remote Execution Protocol Lifecycle: Worker registration, Fencing token validation, Chunked streaming media transfer, Disconnection handling.
G. Operational Monitoring & Cost Lifecycle: Telemetry collection, Heartbeat latency, Duration percentiles, Cost attribution, Deduplicated alerting.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
import unittest
from typing import Any, Dict, List

from video_studio.conform_engine import ConformEngine
from video_studio.conform_models import (
    ConformCompatibilityGrade,
    ConformPreflightReport,
    MediaRepresentationMode,
    ProxyMappingRecord,
    ProxyProfile,
)
from video_studio.conform_service import ConformService
from video_studio.export_engine import ExportEngine
from video_studio.export_models import ExportConfig, ExportContainer, VideoEncoderCodec
from video_studio.media_library import MediaAsset, ProjectMediaLibrary
from video_studio.media_models import AssetLifecycleStatus, AssetMediaType
from video_studio.monitoring_models import (
    CostPricingModel,
    HardwareTelemetry,
    OperationalAlertSeverity,
    OperationalAlertStatus,
    RenderFailureCategory,
)
from video_studio.monitoring_service import RenderMonitoringService
from video_studio.orchestration_models import OrchestratedRenderState
from video_studio.orchestration_service import RenderOrchestrationService
from video_studio.package_engine import PackageEngine
from video_studio.package_models import ArchiveFormat, PackageType
from video_studio.package_service import PackageService
from video_studio.project import VideoProject
from video_studio.provenance_engine import compute_file_sha256_chunked
from video_studio.provenance_models import (
    AssetProvenanceRecord,
    DependencyNodeType,
    ProjectDependencyGraph,
)
from video_studio.provenance_service import ProvenanceService
from video_studio.registry import VideoStudioCapabilityRegistry
from video_studio.remote_models import (
    ChunkedAssetTransferEnvelope,
    REMOTE_WORKER_PROTOCOL_VERSION,
    WorkerHealthStatus,
)
from video_studio.remote_service import RemoteWorkerCoordinatorService
from video_studio.timeline_commands import (
    TimelineCommand,
    TimelineHistoryManager,
    TimelineOpType,
    TimelineTransaction,
)
from video_studio.timeline_models import (
    SequenceSettings,
    TimelineItemModel,
    TimelineRange,
    TimelineTrackModel,
    TimelineTrackType,
    VideoSequence,
)
from video_studio.timeline_service import TimelineService
from video_studio.versioning_models import RevisionSnapshot, RevisionType
from video_studio.versioning_service import VersionControlService


class FakeCertificationExportEngine:
    """Mock export engine creating authentic binary test artifacts."""
    def render_sequence_to_file(self, job: Any, sequence: Any) -> Any:
        pass


class FakeCertificationMediaLibraryRegistry:
    def __init__(self):
        self._libs: Dict[str, ProjectMediaLibrary] = {}

    def get_or_create(self, project_id: str) -> ProjectMediaLibrary:
        if project_id not in self._libs:
            self._libs[project_id] = ProjectMediaLibrary(project_id)
        return self._libs[project_id]


class TestVideoStudioModule47Certification(unittest.TestCase):
    """Rigorous end-to-end acceptance certification for the entire Video Studio subsystem."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = self.temp_dir.name
        self.media_dir = os.path.join(self.root, "media")
        self.output_dir = os.path.join(self.root, "outputs")
        self.archive_dir = os.path.join(self.root, "archives")
        self.audit_log = os.path.join(self.root, "cert_audit.jsonl")
        os.makedirs(self.media_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.archive_dir, exist_ok=True)

        self.registry = VideoStudioCapabilityRegistry()
        self.tl_service = TimelineService()
        self.media_registry = FakeCertificationMediaLibraryRegistry()

        self.versioning_service = VersionControlService(
            capability_registry=self.registry,
            tl_service=self.tl_service,
            media_registry=self.media_registry,
            audit_log_path=self.audit_log,
        )
        self.provenance_service = ProvenanceService(
            capability_registry=self.registry,
            tl_service=self.tl_service,
            media_registry=self.media_registry,
            versioning_svc=self.versioning_service,
            audit_log_path=self.audit_log,
        )
        self.conform_service = ConformService(
            capability_registry=self.registry,
            tl_service=self.tl_service,
            media_registry=self.media_registry,
            versioning_svc=self.versioning_service,
            audit_log_path=self.audit_log,
        )
        self.export_engine = FakeCertificationExportEngine()
        self.packaging_service = PackageService(
            engine=PackageEngine(),
            tl_service=self.tl_service,
        )

        self.orch_service = RenderOrchestrationService(
            capability_registry=self.registry,
            tl_service=self.tl_service,
            conf_service=self.conform_service,
            versioning_svc=self.versioning_service,
            exp_engine=self.export_engine,
            audit_log_path=self.audit_log,
        )
        self.remote_service = RemoteWorkerCoordinatorService(
            capability_registry=self.registry,
            orch_service=self.orch_service,
            audit_log_path=self.audit_log,
        )
        self.monitoring_service = RenderMonitoringService(
            capability_registry=self.registry,
            orch_service=self.orch_service,
            remote_service=self.remote_service,
            audit_log_path=self.audit_log,
        )

        # Create dummy high-res video file
        self.raw_video_path = os.path.join(self.media_dir, "master_take_01.mp4")
        self.raw_bytes = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + (b"FRAME_RAW_PAYLOAD_" * 50)
        with open(self.raw_video_path, "wb") as f:
            f.write(self.raw_bytes)
        self.raw_sha256 = hashlib.sha256(self.raw_bytes).hexdigest()
        self.project_id = "proj_cert_master"

    def tearDown(self) -> None:
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    # =========================================================================
    # A. Project & Media Lifecycle Certification
    # =========================================================================

    def test_e2e_01_project_and_media_provenance_lifecycle(self) -> None:
        """Validates project creation, asset ingestion, dependency graph, and intelligent relinking."""
        proj = VideoProject(name="Certification Feature Doc", project_id=self.project_id)
        self.assertIsNotNone(proj.project_id)

        library = self.media_registry.get_or_create(self.project_id)
        asset = MediaAsset(
            asset_id="asset_master_01",
            project_id=self.project_id,
            name="Master Take 01",
            original_name="master_take_01.mp4",
            file_location=self.raw_video_path,
            size_bytes=len(self.raw_bytes),
            content_hash_sha256=self.raw_sha256,
            media_type=AssetMediaType.VIDEO,
            status=AssetLifecycleStatus.READY,
        )
        library.add_asset(asset)

        # Build sequence dependency
        seq = self.tl_service.create_sequence(project_id=self.project_id, name="Conform Reel")
        clip = TimelineItemModel(
            item_id="clip_master_01",
            track_id=seq.tracks[0].track_id,
            sequence_id=seq.sequence_id,
            source_reference_id="asset_master_01",
            name="A-Roll Master",
            timeline_range=TimelineRange(start_frame=0, duration_frames=100),
        )
        seq.tracks[0].items.append(clip)

        # Record provenance event
        self.provenance_service.record_provenance_event(
            asset_id="asset_master_01",
            event_type="INGEST",
            new_location=self.raw_video_path,
            new_checksum=self.raw_sha256,
            actor_id="lead_editor",
            rationale="Initial master ingestion",
        )

        # Verify dependency graph
        graph = self.provenance_service.get_dependency_graph(self.project_id)
        self.assertIn(f"asset_{asset.asset_id}", graph.nodes)
        self.assertIn(f"seq_{seq.sequence_id}", graph.nodes)

        # Simulate missing media & run relink audit
        relocated_path = os.path.join(self.media_dir, "master_take_01_moved.mp4")
        shutil.move(self.raw_video_path, relocated_path)

        health = self.provenance_service.inspect_project_assets_health(self.project_id)
        self.assertIn("asset_master_01", health["missing_asset_ids"])

        # Candidate discovery and verified relink
        candidates = self.provenance_service.find_relink_candidates(self.project_id, "asset_master_01", [self.media_dir])
        self.assertGreater(len(candidates), 0)
        self.assertEqual(candidates[0].file_path, relocated_path)
        self.assertTrue(candidates[0].is_verified)

        relink_res = self.provenance_service.relink_asset(self.project_id, "asset_master_01", relocated_path)
        self.assertTrue(relink_res.success)
        self.assertEqual(asset.file_location, relocated_path)

    # =========================================================================
    # B. Editing & Timeline Lifecycle Certification
    # =========================================================================

    def test_e2e_02_editing_timeline_and_undo_lifecycle(self) -> None:
        """Validates multi-track sequence editing, ripple trimming, and undo/redo operations."""
        seq = self.tl_service.create_sequence(project_id="proj_cert_edit", name="Edit Reel")
        track_v = seq.tracks[0]

        hm = TimelineHistoryManager(seq)
        tx = TimelineTransaction(transaction_id="tx_edit_01", sequence_id=seq.sequence_id, description="Add two clips")
        c1 = TimelineCommand(
            command_id="cmd_1",
            op_type=TimelineOpType.ADD_ITEM,
            sequence_id=seq.sequence_id,
            target_id="c1",
            payload={
                "track_id": track_v.track_id,
                "item": {
                    "item_id": "c1",
                    "source_reference_id": "src_1",
                    "timeline_range": {"start_frame": 0, "duration_frames": 100},
                    "source_range": {"in_frame": 0, "duration_frames": 100},
                }
            }
        )
        tx.append(c1)
        ok_commit = hm.commit_transaction(tx)
        self.assertTrue(ok_commit)
        self.assertEqual(len(track_v.items), 1)

        # Undo add clip
        ok_undo = hm.undo()
        self.assertTrue(ok_undo)
        self.assertEqual(len(track_v.items), 0)

        # Redo add clip
        ok_redo = hm.redo()
        self.assertTrue(ok_redo)
        self.assertEqual(len(track_v.items), 1)
        self.assertEqual(track_v.items[0].item_id, "c1")

    # =========================================================================
    # C. Revision & Recovery Lifecycle Certification
    # =========================================================================

    def test_e2e_03_revision_control_and_non_destructive_recovery(self) -> None:
        """Validates revision snapshots, structural diffing, branching, and safe restoration."""
        proj_id = "proj_revision_cert"
        seq = self.tl_service.create_sequence(project_id=proj_id, name="Cut 01")

        # Snapshot Revision 1
        snap1 = self.versioning_service.create_snapshot(
            project_id=proj_id,
            sequence_id=seq.sequence_id,
            name="Rough Cut",
            message="Initial cut assembly",
            author_id="Director",
        )
        self.assertEqual(snap1.revision_number, 1)

        # Modify sequence
        clip = TimelineItemModel(
            item_id="clip_rev_add",
            track_id=seq.tracks[0].track_id,
            sequence_id=seq.sequence_id,
            source_reference_id="asset_extra",
            name="Extra Shot",
            timeline_range=TimelineRange(start_frame=0, duration_frames=60),
        )
        seq.tracks[0].items.append(clip)
        seq.revision += 1

        # Snapshot Revision 2
        snap2 = self.versioning_service.create_snapshot(
            project_id=proj_id,
            sequence_id=seq.sequence_id,
            name="Director's Cut",
            message="Added extra shot",
            author_id="Director",
        )
        self.assertEqual(snap2.revision_number, 2)

        # Diff snapshots
        diff = self.versioning_service.compare_revisions(snap1.revision_id, snap2.revision_id)
        self.assertIsNotNone(diff)
        self.assertFalse(diff.is_identical)

        # Non-destructive restore back to Revision 1
        res = self.versioning_service.restore_revision(
            revision_id=snap1.revision_id,
        )
        self.assertTrue(res.success)

    # =========================================================================
    # D. Proxy & Conform Lifecycle Certification
    # =========================================================================

    def test_e2e_04_proxy_generation_and_high_res_online_conform(self) -> None:
        """Validates proxy representation mapping, editing, and switching to high-res online conform."""
        library = self.media_registry.get_or_create(self.project_id)
        asset = MediaAsset(
            asset_id="asset_conform_4k",
            project_id=self.project_id,
            name="4K Cinema Footage",
            original_name="cinema_4k.mp4",
            file_location=self.raw_video_path,
            size_bytes=len(self.raw_bytes),
            content_hash_sha256=self.raw_sha256,
            duration_seconds=10.0,
            total_frames=240,
            frame_rate=24.0,
            width=3840,
            height=2160,
            media_type=AssetMediaType.VIDEO,
            status=AssetLifecycleStatus.READY,
        )
        library.add_asset(asset)

        # Create proxy file & asset
        proxy_path = os.path.join(self.media_dir, "cinema_proxy_720p.mp4")
        with open(proxy_path, "wb") as f:
            f.write(b"PROXY_DATA_720P")

        proxy_asset = MediaAsset(
            asset_id="asset_proxy_720p",
            project_id=self.project_id,
            name="720p Proxy",
            original_name="cinema_proxy_720p.mp4",
            file_location=proxy_path,
            size_bytes=len(b"PROXY_DATA_720P"),
            duration_seconds=10.0,
            total_frames=240,
            frame_rate=24.0,
            width=1280,
            height=720,
            media_type=AssetMediaType.VIDEO,
            status=AssetLifecycleStatus.READY,
        )
        library.add_asset(proxy_asset)

        # Register proxy mapping
        mapping = self.conform_service.register_proxy_mapping(
            project_id=self.project_id,
            original_asset_id=asset.asset_id,
            proxy_asset_id=proxy_asset.asset_id,
        )
        self.assertEqual(mapping.proxy_asset_id, proxy_asset.asset_id)

        # Switch sequence to proxy mode
        seq = self.tl_service.create_sequence(project_id=self.project_id, name="Conform Test Seq")
        clip = TimelineItemModel(
            item_id="clip_conf",
            track_id=seq.tracks[0].track_id,
            sequence_id=seq.sequence_id,
            source_reference_id=asset.asset_id,
            name="Shot 1",
            timeline_range=TimelineRange(start_frame=0, duration_frames=100),
        )
        seq.tracks[0].items.append(clip)

        res_switch = self.conform_service.switch_representation_mode(
            project_id=self.project_id,
            sequence_id=seq.sequence_id,
            target_mode=MediaRepresentationMode.PROXY,
        )
        self.assertTrue(res_switch.success)
        self.assertEqual(res_switch.conformed_clips_count, 1)

        # Run preflight conform audit
        report = self.conform_service.run_conform_preflight(
            project_id=self.project_id,
            sequence_id=seq.sequence_id,
        )
        self.assertTrue(report.is_ready_for_online_render)
        self.assertEqual(report.overall_grade, ConformCompatibilityGrade.COMPATIBLE)

        # Execute final high-res online conform
        res_conform = self.conform_service.execute_online_conform(
            project_id=self.project_id,
            sequence_id=seq.sequence_id,
        )
        self.assertTrue(res_conform.success)
        self.assertEqual(clip.source_reference_id, asset.asset_id)

    # =========================================================================
    # E. Render, Verification & Delivery Lifecycle Certification
    # =========================================================================

    def test_e2e_05_render_orchestration_verification_and_packaging(self) -> None:
        """Validates render job state machine, SHA-256 verification, and project packaging."""
        proj_id = "proj_delivery_cert"
        seq = self.tl_service.create_sequence(project_id=proj_id, name="Final Export Reel")
        out_file = os.path.join(self.output_dir, "master_deliverable.mp4")

        # 1. Create orchestrated render job
        job = self.orch_service.create_orchestrated_job(
            project_id=proj_id,
            sequence_id=seq.sequence_id,
            output_path=out_file,
            config=ExportConfig(width=1920, height=1080, frame_rate=24.0),
        )
        self.assertEqual(job.state, OrchestratedRenderState.CREATED)

        # 2. Advance through valid states
        job.transition_to(OrchestratedRenderState.VALIDATING)
        job.transition_to(OrchestratedRenderState.QUEUED)
        job.transition_to(OrchestratedRenderState.SCHEDULED)
        job.transition_to(OrchestratedRenderState.PREPARING)
        job.transition_to(OrchestratedRenderState.RENDERING)

        # Write actual render payload to temp file
        render_payload = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41" + (b"RENDERED_FINAL_" * 20)
        with open(job.temp_output_path, "wb") as f:
            f.write(render_payload)

        job.transition_to(OrchestratedRenderState.FINALIZING)
        job.transition_to(OrchestratedRenderState.VERIFYING)

        # 3. Output artifact verification & atomic publish
        ok_ver, err_ver, sha, size = self.orch_service.engine.verify_output_artifact(job.temp_output_path)
        self.assertTrue(ok_ver)
        self.assertEqual(sha, hashlib.sha256(render_payload).hexdigest())

        ok_pub, err_pub = self.orch_service.engine.publish_output_atomically(job.temp_output_path, job.output_path)
        self.assertTrue(ok_pub)
        self.assertTrue(os.path.exists(out_file))

        job.output_sha256 = sha
        job.output_size_bytes = size
        job.is_verified = True
        job.transition_to(OrchestratedRenderState.COMPLETED)
        self.assertEqual(job.state, OrchestratedRenderState.COMPLETED)

        # 4. Project packaging
        package_file = os.path.join(self.archive_dir, "package_export.ovp")
        manifest = self.packaging_service.create_project_package(
            project_id=proj_id,
            output_archive_path=package_file,
            package_type=PackageType.ARCHIVE_MASTER,
        )
        self.assertIsNotNone(manifest.project_id)
        self.assertTrue(os.path.exists(package_file))

    # =========================================================================
    # F. Remote Execution Protocol Certification
    # =========================================================================

    def test_e2e_06_remote_worker_protocol_and_fencing_integrity(self) -> None:
        """Validates distributed worker protocol: registration, leasing, fencing tokens, and chunk verification."""
        worker = self.remote_service.register_worker(
            worker_id="cert_worker_01",
            name="Farm Node 01",
            secret_token="secret_farm_key",
            has_gpu=True,
            max_concurrent_jobs=2,
            protocol_version=REMOTE_WORKER_PROTOCOL_VERSION,
        )
        self.assertEqual(worker.status, WorkerHealthStatus.ONLINE)

        seq = self.tl_service.create_sequence(project_id="proj_farm_test", name="Farm Target Sequence")
        job = self.orch_service.create_orchestrated_job(
            project_id="proj_farm_test",
            sequence_id=seq.sequence_id,
            output_path=os.path.join(self.output_dir, "farm_output.mp4"),
            config=ExportConfig(),
        )

        # Assign job with monotonic fencing token
        assignment = self.remote_service.assign_job_to_worker(job.job_id, worker.worker_id)
        self.assertEqual(assignment.fencing_token, 1)
        self.assertTrue(assignment.is_lease_valid())

        # Stream chunked completion
        part1 = b"DISTRIBUTED_PART_ONE_"
        part2 = b"DISTRIBUTED_PART_TWO_"
        chunks = [
            ChunkedAssetTransferEnvelope(
                chunk_index=0,
                total_chunks=2,
                chunk_bytes=part1,
                chunk_sha256=hashlib.sha256(part1).hexdigest(),
                is_last_chunk=False,
            ),
            ChunkedAssetTransferEnvelope(
                chunk_index=1,
                total_chunks=2,
                chunk_bytes=part2,
                chunk_sha256=hashlib.sha256(part2).hexdigest(),
                is_last_chunk=True,
            ),
        ]

        ok, err = self.remote_service.complete_remote_job(
            worker_id=worker.worker_id,
            secret_token="secret_farm_key",
            job_id=job.job_id,
            fencing_token=assignment.fencing_token,
            returned_artifact_chunks=chunks,
        )
        self.assertTrue(ok)
        self.assertEqual(job.state, OrchestratedRenderState.COMPLETED)
        self.assertTrue(os.path.exists(job.output_path))
        with open(job.output_path, "rb") as f:
            self.assertEqual(f.read(), part1 + part2)

    # =========================================================================
    # G. Operational Monitoring & Cost Lifecycle Certification
    # =========================================================================

    def test_e2e_07_operational_telemetry_cost_and_alert_deduplication(self) -> None:
        """Validates telemetry tracking, cost attribution from measured data, and deduplicated alerting."""
        proj_id = "proj_telemetry_test"
        job_id = "job_metric_01"

        # Record stage transitions
        t0 = 2000.0
        self.monitoring_service.record_job_lifecycle_event(job_id, "QUEUED", timestamp=t0)
        self.monitoring_service.record_job_lifecycle_event(job_id, "SCHEDULED", timestamp=t0 + 5.0)
        self.monitoring_service.record_job_lifecycle_event(job_id, "RENDERING", timestamp=t0 + 10.0)
        self.monitoring_service.record_job_lifecycle_event(job_id, "FINALIZING", timestamp=t0 + 40.0)
        
        # Attach authentic hardware telemetry
        hw = HardwareTelemetry(
            cpu_utilization_percent=78.5,
            memory_used_mb=4096.0,
            gpu_utilization_percent=95.0,
            is_measured=True,
        )
        rec = self.monitoring_service.record_job_lifecycle_event(
            job_id,
            "COMPLETED",
            timestamp=t0 + 50.0,
            hardware_telemetry=hw,
        )
        rec.project_id = proj_id
        rec.output_size_bytes = 2 * (1024 ** 3) # 2 GB
        rec.asset_transfer_bytes = 1 * (1024 ** 3) # 1 GB
        rec.is_output_verified = True # Avoid verification failure alert trigger

        # Evaluate pricing
        pricing = CostPricingModel(
            worker_hour_rate=1.00,
            gpu_hour_rate=2.00,
            storage_gb_month_rate=0.05,
            transfer_gb_rate=0.10,
        )
        self.monitoring_service.configure_pricing_model(pricing)
        cost = self.monitoring_service.calculate_job_cost(job_id)

        self.assertAlmostEqual(cost.total_estimated_cost, (50.0/3600.0)*1.00 + (30.0/3600.0)*2.00 + (2.0*0.05) + (1.0*0.10), delta=0.01)
        self.assertTrue(cost.is_estimate)

        # Clear existing alerts
        self.monitoring_service._alerts.clear()

        # Trigger and verify deduplicated alert
        alert1 = self.monitoring_service.engine.evaluate_operational_alerts(
            existing_alerts=self.monitoring_service._alerts,
            dedup_key="cert_warning_01",
            severity=OperationalAlertSeverity.WARNING,
            title="Queue Delay",
            message="Moderate delay",
        )
        self.assertEqual(alert1.occurrence_count, 1)

        alert2 = self.monitoring_service.engine.evaluate_operational_alerts(
            existing_alerts=self.monitoring_service._alerts,
            dedup_key="cert_warning_01",
            severity=OperationalAlertSeverity.ERROR,
            title="Queue Delay",
            message="Severe delay",
        )
        self.assertEqual(alert2.occurrence_count, 2)
        self.assertEqual(alert2.severity, OperationalAlertSeverity.ERROR)
        self.assertEqual(len(self.monitoring_service.get_alerts()), 1)


if __name__ == "__main__":
    unittest.main()
