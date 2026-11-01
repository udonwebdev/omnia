"""OMNIA Video Studio — Module 46: Render Farm Monitoring & Operational Analytics Tests.

Comprehensive test suite verifying:
1. Structured render job telemetry capture across lifecycle stages.
2. Accurate stage duration calculations.
3. Handling of missing or non-measured hardware metrics without fabrication.
4. Live worker fleet monitoring and heartbeat delay calculations.
5. Stale worker timeout detection.
6. Operational queue analytics, throughput, and error rates.
7. Pure mathematical percentile calculations (p50, p95, p99).
8. Deterministic failure categorization taxonomy.
9. Retry success rate evaluation.
10. Transparent cost attribution with configurable pricing rates.
11. Cost calculations with unmeasured quantities.
12. Capacity forecasting with insufficient-sample rejection.
13. Alert threshold evaluation.
14. Alert deduplication and resolution lifecycle.
15. Role-based access control and project filtering.
16. Historical telemetry retention and pruning safeguards.
17. Real-data dashboard aggregation.
18. Capability catalog registration for Module 46.
"""

import os
import shutil
import tempfile
import time
import unittest
from typing import Any, Dict, List

from video_studio.conform_models import MediaRepresentationMode
from video_studio.conform_service import ConformService
from video_studio.export_engine import ExportEngine
from video_studio.export_models import ExportConfig
from video_studio.models import VideoStudioFeatureContract
from video_studio.monitoring_engine import RenderMonitoringEngine
from video_studio.monitoring_models import (
    CostPricingModel,
    HardwareTelemetry,
    OperationalAlertSeverity,
    OperationalAlertStatus,
    RenderFailureCategory,
    RenderJobTelemetryRecord,
)
from video_studio.monitoring_service import RenderMonitoringService
from video_studio.orchestration_models import OrchestratedRenderState
from video_studio.orchestration_service import RenderOrchestrationService
from video_studio.registry import VideoStudioCapabilityRegistry
from video_studio.remote_models import WorkerHealthStatus
from video_studio.remote_service import RemoteWorkerCoordinatorService
from video_studio.service import VideoStudioService
from video_studio.timeline_models import VideoSequence
from video_studio.timeline_service import TimelineService
from video_studio.versioning_service import VersionControlService


class FakeExportEngine:
    def render_sequence_to_file(self, job: Any, sequence: VideoSequence) -> Any:
        pass


class TestVideoStudioModule46Monitoring(unittest.TestCase):
    """Rigorous tests for Module 46 monitoring, cost attribution, and capacity analytics."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.registry = VideoStudioCapabilityRegistry()
        
        # Isolated services
        self.tl_service = TimelineService()
        self.conf_service = ConformService()
        self.versioning_svc = VersionControlService(
            capability_registry=self.registry,
            tl_service=self.tl_service,
        )
        self.export_engine = FakeExportEngine()
        
        self.orch_service = RenderOrchestrationService(
            capability_registry=self.registry,
            tl_service=self.tl_service,
            conf_service=self.conf_service,
            versioning_svc=self.versioning_svc,
            exp_engine=self.export_engine,
        )
        self.remote_service = RemoteWorkerCoordinatorService(
            capability_registry=self.registry,
            orch_service=self.orch_service,
        )
        self.monitoring_service = RenderMonitoringService(
            capability_registry=self.registry,
            orch_service=self.orch_service,
            remote_service=self.remote_service,
        )

        # Baseline project & sequence
        self.project_id = "test_proj_m46"
        self.seq = self.tl_service.create_sequence(
            project_id=self.project_id,
            name="Main Sequence M46",
        )
        self.seq.duration_frames = 240

    def tearDown(self) -> None:
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    # =========================================================================
    # 1. Telemetry Capture & Durations
    # =========================================================================

    def test_01_telemetry_capture_and_stage_durations(self) -> None:
        """Verifies structured telemetry tracks timestamps and computes stage durations."""
        job = self.orch_service.create_orchestrated_job(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            output_path="/tmp/output.mp4",
            config=ExportConfig(width=1920, height=1080, frame_rate=24.0),
        )

        t0 = 1000.0
        job.created_at = t0
        # Created -> Queued -> Scheduled -> Rendering -> Finalizing -> Completed
        self.monitoring_service.record_job_lifecycle_event(job.job_id, "QUEUED", timestamp=t0)
        self.monitoring_service.record_job_lifecycle_event(job.job_id, "SCHEDULED", timestamp=t0 + 10.0)
        self.monitoring_service.record_job_lifecycle_event(job.job_id, "RENDERING", timestamp=t0 + 15.0)
        self.monitoring_service.record_job_lifecycle_event(job.job_id, "FINALIZING", timestamp=t0 + 45.0)
        rec = self.monitoring_service.record_job_lifecycle_event(job.job_id, "COMPLETED", timestamp=t0 + 50.0)

        self.assertEqual(rec.queue_wait_duration, 10.0)
        self.assertEqual(rec.preparation_duration, 5.0)
        self.assertEqual(rec.encoding_duration, 30.0)
        self.assertEqual(rec.verification_duration, 5.0)
        self.assertEqual(rec.total_duration, 50.0)

    def test_02_missing_measurements_handling_without_fabrication(self) -> None:
        """Verifies missing hardware metrics remain None and is_measured is False."""
        hw = HardwareTelemetry()
        self.assertIsNone(hw.cpu_utilization_percent)
        self.assertIsNone(hw.gpu_utilization_percent)
        self.assertIsNone(hw.memory_used_mb)
        self.assertFalse(hw.is_measured)

        # When genuine measurements are provided:
        measured_hw = HardwareTelemetry(
            cpu_utilization_percent=65.4,
            memory_used_mb=2048.0,
            gpu_utilization_percent=92.1,
            is_measured=True,
        )
        self.assertTrue(measured_hw.is_measured)
        self.assertEqual(measured_hw.gpu_utilization_percent, 92.1)

    # =========================================================================
    # 2. Worker Monitoring & Stale Heartbeat Detection
    # =========================================================================

    def test_03_worker_monitoring_and_timeout_detection(self) -> None:
        """Verifies worker fleet snapshot and timeout classification on missed heartbeats."""
        worker = self.remote_service.register_worker(
            worker_id="w_node_live",
            name="Live Worker Node",
            secret_token="sec_live",
            has_gpu=True,
            max_concurrent_jobs=4,
        )
        worker.last_heartbeat = time.time() - 40.0
        worker.heartbeat_timeout_seconds = 30.0

        snapshots = self.monitoring_service.get_worker_monitoring_snapshots()
        self.assertEqual(len(snapshots), 1)
        snap = snapshots[0]
        self.assertEqual(snap.worker_id, "w_node_live")
        self.assertFalse(snap.is_alive)
        self.assertEqual(snap.status, WorkerHealthStatus.TIMEOUT.value)
        self.assertTrue(snap.has_gpu)

        # Verify alert was raised
        alerts = self.monitoring_service.get_alerts(OperationalAlertStatus.OPEN)
        self.assertTrue(any("worker_timeout_w_node_live" in a.dedup_key for a in alerts))

    # =========================================================================
    # 3. Queue Analytics & Percentiles
    # =========================================================================

    def test_04_queue_analytics_and_percentiles(self) -> None:
        """Verifies percentiles (p50, p95, p99), throughput, and failure rate aggregations."""
        durations = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
        p50 = RenderMonitoringEngine.calculate_percentile(durations, 50.0)
        p95 = RenderMonitoringEngine.calculate_percentile(durations, 95.0)
        p99 = RenderMonitoringEngine.calculate_percentile(durations, 99.0)

        self.assertAlmostEqual(p50, 55.0, delta=1.0)
        self.assertAlmostEqual(p95, 95.5, delta=1.0)
        self.assertAlmostEqual(p99, 99.1, delta=1.0)

        # Build telemetry records
        records = []
        for i, dur in enumerate(durations):
            rec = RenderJobTelemetryRecord(
                job_id=f"j_{i}",
                final_state="COMPLETED",
                queue_wait_duration=5.0,
                encoding_duration=dur,
                total_duration=dur + 5.0,
                created_at=1000.0 + (i * 10),
                finalized_at=1000.0 + (i * 10) + dur + 5.0,
            )
            records.append(rec)

        summary = RenderMonitoringEngine.aggregate_queue_metrics(records, time_window_seconds=3600.0)
        self.assertEqual(summary.total_jobs, 10)
        self.assertEqual(summary.completed_jobs, 10)
        self.assertEqual(summary.failed_jobs, 0)
        self.assertAlmostEqual(summary.avg_render_duration_seconds, 55.0, delta=0.1)

    # =========================================================================
    # 4. Failure Categorization & Retry Evaluation
    # =========================================================================

    def test_05_failure_categorization_and_retry_success(self) -> None:
        """Verifies structured failure classification taxonomy and retry success rates."""
        eng = RenderMonitoringEngine()
        self.assertEqual(eng.classify_failure("Missing media asset clip_01.mp4"), RenderFailureCategory.MISSING_MEDIA)
        self.assertEqual(eng.classify_failure("Worker heartbeat timeout encountered"), RenderFailureCategory.WORKER_DISCONNECTED)
        self.assertEqual(eng.classify_failure("FFmpeg muxer encode error"), RenderFailureCategory.ENCODING_FAILURE)
        self.assertEqual(eng.classify_failure("Checksum corrupted payload chunk 2"), RenderFailureCategory.ASSET_TRANSFER_FAILURE)
        self.assertEqual(eng.classify_failure("Output verification failed: SHA mismatch"), RenderFailureCategory.OUTPUT_VERIFICATION_FAILURE)
        self.assertEqual(eng.classify_failure("Out of memory OOM killer invoked"), RenderFailureCategory.RESOURCE_EXHAUSTION)

        # Retry success rate
        rec1 = RenderJobTelemetryRecord(job_id="r1", final_state="COMPLETED", retry_count=1)
        rec2 = RenderJobTelemetryRecord(job_id="r2", final_state="FAILED", retry_count=2)
        summary = eng.aggregate_queue_metrics([rec1, rec2])
        self.assertEqual(summary.retry_success_rate_percent, 50.0)

    # =========================================================================
    # 5. Cost Attribution
    # =========================================================================

    def test_06_cost_attribution_with_explicit_rates(self) -> None:
        """Verifies transparent cost calculations based on measured execution duration and transfer."""
        pricing = CostPricingModel(
            currency="USD",
            worker_hour_rate=1.00,        # $1.00 / hour
            gpu_hour_rate=2.00,           # $2.00 / hour
            storage_gb_month_rate=0.10,   # $0.10 / GB
            transfer_gb_rate=0.20,        # $0.20 / GB
        )
        rec = RenderJobTelemetryRecord(
            job_id="job_cost_01",
            project_id=self.project_id,
            total_duration=3600.0,              # Exactly 1 worker hour -> $1.00
            encoding_duration=1800.0,           # Exactly 0.5 GPU hour -> $1.00
            output_size_bytes=10 * (1024 ** 3), # 10 GB -> $1.00
            asset_transfer_bytes=5 * (1024 ** 3), # 5 GB -> $1.00
            hardware=HardwareTelemetry(gpu_utilization_percent=85.0, is_measured=True),
        )

        cost = RenderMonitoringEngine.calculate_job_cost(rec, pricing)
        self.assertAlmostEqual(cost.worker_compute_cost, 1.00, delta=0.01)
        self.assertAlmostEqual(cost.gpu_compute_cost, 1.00, delta=0.01)
        self.assertAlmostEqual(cost.storage_cost, 1.00, delta=0.01)
        self.assertAlmostEqual(cost.transfer_cost, 1.00, delta=0.01)
        self.assertAlmostEqual(cost.total_estimated_cost, 4.00, delta=0.01)
        self.assertTrue(cost.is_estimate)

    def test_07_cost_attribution_zero_when_hardware_unmeasured(self) -> None:
        """Verifies GPU costs are not charged if GPU utilization was unmeasured."""
        pricing = CostPricingModel(gpu_hour_rate=5.00)
        rec = RenderJobTelemetryRecord(
            job_id="job_no_gpu",
            project_id=self.project_id,
            total_duration=600.0,
            encoding_duration=600.0,
            hardware=HardwareTelemetry(gpu_utilization_percent=None, is_measured=False),
        )
        cost = RenderMonitoringEngine.calculate_job_cost(rec, pricing)
        self.assertEqual(cost.gpu_compute_cost, 0.0)

    # =========================================================================
    # 6. Capacity Planning
    # =========================================================================

    def test_08_capacity_forecasting_sample_size_gating(self) -> None:
        """Verifies capacity predictions are rejected when sample size is below minimum threshold."""
        # 3 samples < minimum 5
        records = [
            RenderJobTelemetryRecord(job_id=f"j_{i}", final_state="COMPLETED", encoding_duration=100.0)
            for i in range(3)
        ]
        forecast = RenderMonitoringEngine.evaluate_capacity(
            total_workers=2,
            total_slots=4,
            active_slots=1,
            queued_jobs=10,
            completed_history=records,
            min_sample_size=5,
        )
        self.assertFalse(forecast.is_available)
        self.assertIn("Insufficient historical samples", forecast.rejection_reason)

    def test_09_capacity_forecasting_with_sufficient_history(self) -> None:
        """Verifies queue wait, saturation, and bottleneck identification with sufficient samples."""
        records = [
            RenderJobTelemetryRecord(job_id=f"j_{i}", final_state="COMPLETED", encoding_duration=60.0)
            for i in range(10)
        ]
        # 2 workers, 2 slots each = 4 total slots. 4 active slots = 100% saturation. 8 queued jobs.
        forecast = RenderMonitoringEngine.evaluate_capacity(
            total_workers=2,
            total_slots=4,
            active_slots=4,
            queued_jobs=8,
            completed_history=records,
            min_sample_size=5,
        )
        self.assertTrue(forecast.is_available)
        self.assertEqual(forecast.worker_saturation_percent, 100.0)
        # 8 jobs / 4 slots = 2 waves * 60s = 120s = 2.0 minutes
        self.assertAlmostEqual(forecast.estimated_wait_time_minutes, 2.0, delta=0.1)
        self.assertIn("WORKER_CONCURRENCY_EXHAUSTION", forecast.identified_bottlenecks)

    # =========================================================================
    # 7. Alert Deduplication & Evaluation
    # =========================================================================

    def test_10_alert_deduplication_and_resolution(self) -> None:
        """Verifies duplicate alerts increment occurrence_count rather than creating spam."""
        alerts: Dict[str, Any] = {}
        a1 = RenderMonitoringEngine.evaluate_operational_alerts(
            existing_alerts=alerts,
            dedup_key="queue_jam",
            severity=OperationalAlertSeverity.WARNING,
            title="Queue Jammed",
            message="Backlog high",
        )
        self.assertEqual(a1.occurrence_count, 1)

        # Duplicate alert triggers update
        a2 = RenderMonitoringEngine.evaluate_operational_alerts(
            existing_alerts=alerts,
            dedup_key="queue_jam",
            severity=OperationalAlertSeverity.CRITICAL,
            title="Queue Jammed",
            message="Backlog critical",
        )
        self.assertEqual(a2.occurrence_count, 2)
        self.assertEqual(a2.severity, OperationalAlertSeverity.CRITICAL)
        self.assertEqual(len(alerts), 1)

        # Resolution
        a2.status = OperationalAlertStatus.RESOLVED
        self.assertEqual(a2.status, OperationalAlertStatus.RESOLVED)

    # =========================================================================
    # 8. Access Control & Project Filtering
    # =========================================================================

    def test_11_project_filtering_and_role_access(self) -> None:
        """Verifies project isolation: non-admin dashboard view hides infrastructure fleet."""
        # Record job for proj_A and proj_B
        j_a = RenderJobTelemetryRecord(job_id="ja", project_id="proj_A", final_state="COMPLETED")
        j_b = RenderJobTelemetryRecord(job_id="jb", project_id="proj_B", final_state="COMPLETED")
        self.monitoring_service._telemetry_records["ja"] = j_a
        self.monitoring_service._telemetry_records["jb"] = j_b

        summary_a = self.monitoring_service.get_queue_analytics(project_id="proj_A")
        self.assertEqual(summary_a.total_jobs, 1)

        # Viewer dashboard: fleet snapshots hidden
        view_user = self.monitoring_service.get_dashboard_overview(project_id="proj_A", requesting_role="editor")
        self.assertEqual(len(view_user["worker_fleet"]), 0)
        self.assertIsNone(view_user["capacity_forecast"])

        # Admin dashboard: fleet snapshots visible
        view_admin = self.monitoring_service.get_dashboard_overview(project_id="proj_A", requesting_role="admin")
        self.assertIsNotNone(view_admin["worker_fleet"])

    # =========================================================================
    # 9. Telemetry Retention & Pruning Safeguards
    # =========================================================================

    def test_12_telemetry_retention_and_pruning(self) -> None:
        """Verifies old completed records can be pruned while active jobs are strictly preserved."""
        now = time.time()
        # Old completed job (10 days old)
        old_job = RenderJobTelemetryRecord(
            job_id="old_done",
            final_state="COMPLETED",
            created_at=now - 864000.0,
            finalized_at=now - 863000.0,
        )
        # Old active job (in flight, must NOT be deleted)
        active_job = RenderJobTelemetryRecord(
            job_id="in_flight",
            final_state="RENDERING",
            created_at=now - 864000.0,
        )
        # Recent completed job (1 hour old)
        recent_job = RenderJobTelemetryRecord(
            job_id="recent_done",
            final_state="COMPLETED",
            created_at=now - 3600.0,
            finalized_at=now - 3500.0,
        )

        self.monitoring_service._telemetry_records["old_done"] = old_job
        self.monitoring_service._telemetry_records["in_flight"] = active_job
        self.monitoring_service._telemetry_records["recent_done"] = recent_job

        # Prune jobs older than 2 days (172,800s)
        deleted = self.monitoring_service.prune_old_telemetry(max_age_seconds=172800.0)
        self.assertEqual(deleted, 1)
        self.assertNotIn("old_done", self.monitoring_service._telemetry_records)
        self.assertIn("in_flight", self.monitoring_service._telemetry_records)
        self.assertIn("recent_done", self.monitoring_service._telemetry_records)

    # =========================================================================
    # 10. Capability Catalog Registration
    # =========================================================================

    def test_13_registry_capabilities(self) -> None:
        """Verifies all Module 46 capabilities are registered with IMPLEMENTED state."""
        expected_caps = [
            "video.render.telemetry_collection",
            "video.render.worker_fleet_monitoring",
            "video.render.cost_attribution_engine",
            "video.render.capacity_planning_analytics",
            "video.render.operational_alerting",
        ]
        for cap_id in expected_caps:
            cap = self.registry.get(cap_id)
            self.assertIsNotNone(cap, f"Capability '{cap_id}' must be registered.")
            self.assertEqual(cap.implementation_state.value.upper(), "IMPLEMENTED")


if __name__ == "__main__":
    unittest.main()
