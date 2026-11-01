"""OMNIA Video Studio — Module 46: Render Farm Monitoring & Operational Analytics Service.

Coordinates:
1. Capture of structured render telemetry across all lifecycle stages.
2. Worker health auditing based on live Module 45 registry and heartbeats.
3. Queue performance, duration percentiles, and failure breakdown analytics.
4. Transparent cost attribution with configurable pricing rates.
5. Realistic capacity forecasting with minimum sample gating.
6. Operational alert evaluation, deduplication, and resolution.
7. Role-based authorization and retention cleanup.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from video_studio.monitoring_engine import RenderMonitoringEngine
from video_studio.monitoring_models import (
    CapacityForecast,
    CostPricingModel,
    HardwareTelemetry,
    JobCostAttribution,
    OperationalAlert,
    OperationalAlertSeverity,
    OperationalAlertStatus,
    QueueAnalyticsSummary,
    RenderFailureCategory,
    RenderJobTelemetryRecord,
    WorkerMonitoringSnapshot,
)
from video_studio.orchestration_models import RenderOrchestrationJob
from video_studio.orchestration_service import (
    RenderOrchestrationService,
    render_orchestration_service,
)
from video_studio.registry import (
    VideoStudioCapabilityRegistry,
    video_studio_capability_registry,
)
from video_studio.registry_models import (
    ImplementationState,
    VideoStudioCapabilityDescriptor,
    VideoStudioCategory,
)
from video_studio.remote_models import RemoteWorkerRegistration, WorkerHealthStatus
from video_studio.remote_service import (
    RemoteWorkerCoordinatorService,
    remote_worker_coordinator_service,
)


class RenderMonitoringService:
    """Enterprise Operational Monitoring, Cost Attribution & Capacity Planning Service."""

    def __init__(
        self,
        capability_registry: Optional[VideoStudioCapabilityRegistry] = None,
        orch_service: Optional[RenderOrchestrationService] = None,
        remote_service: Optional[RemoteWorkerCoordinatorService] = None,
        audit_log_path: str = "omnia_audit.jsonl",
        telemetry_store_path: Optional[str] = None,
    ) -> None:
        self.registry = capability_registry or video_studio_capability_registry
        self.orchestration_service = orch_service or render_orchestration_service
        self.remote_service = remote_service or remote_worker_coordinator_service
        self.audit_log_path = audit_log_path
        self.telemetry_store_path = telemetry_store_path
        self.engine = RenderMonitoringEngine()

        # Telemetry Store: job_id -> RenderJobTelemetryRecord
        self._telemetry_records: Dict[str, RenderJobTelemetryRecord] = {}
        # Operational Alerts: dedup_key -> OperationalAlert
        self._alerts: Dict[str, OperationalAlert] = {}
        # Administrator Cost Pricing Model
        self._pricing_model = CostPricingModel()
        
        # Alert Thresholds
        self.queue_backlog_warning_threshold: int = 10
        self.consecutive_failure_threshold: int = 3
        self.job_duration_warning_seconds: float = 3600.0 # 1 hour

        if self.registry:
            self.register_capabilities()

    def register_capabilities(self) -> None:
        """Registers Module 46 Monitoring capabilities into the central registry."""
        capabilities = [
            VideoStudioCapabilityDescriptor(
                id="video.render.telemetry_collection",
                name="Structured Render Job Telemetry Collection",
                description="End-to-end stage duration, frame throughput, resource metrics, and artifact verification profiling.",
                category=VideoStudioCategory.RENDERING,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["telemetry", "profiling", "timing", "frames"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.render.worker_fleet_monitoring",
                name="Render Farm Worker Fleet Monitoring",
                description="Live worker availability, heartbeat delay, job concurrency saturation, and hardware metrics.",
                category=VideoStudioCategory.RENDERING,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["monitoring", "workers", "fleet", "health"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.render.cost_attribution_engine",
                name="Render Compute Cost Attribution Engine",
                description="Transparent compute, worker time, storage, and transfer cost attribution based on measured metrics.",
                category=VideoStudioCategory.EXPORT,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["cost", "attribution", "pricing", "billing"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.render.capacity_planning_analytics",
                name="Render Capacity Planning & Predictive Analytics",
                description="Statistical queue pressure, bottleneck identification, and worker saturation forecasting.",
                category=VideoStudioCategory.RENDERING,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["capacity", "planning", "analytics", "forecasting"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.render.operational_alerting",
                name="Operational Incident Alerting & Deduplication",
                description="Real-time alert evaluation for worker timeouts, queue backlogs, and repeated verification failures.",
                category=VideoStudioCategory.RENDERING,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["alerting", "incidents", "deduplication", "health"],
            ),
        ]
        for cap in capabilities:
            if self.registry.get(cap.id) is None:
                self.registry.register(cap, auth_token="core")

    # =========================================================================
    # 1. Telemetry Capture & Lifecycle Recording
    # =========================================================================

    def record_job_lifecycle_event(
        self,
        job_id: str,
        stage: str,
        timestamp: Optional[float] = None,
        hardware_telemetry: Optional[HardwareTelemetry] = None,
        failure_reason: Optional[str] = None,
    ) -> RenderJobTelemetryRecord:
        """Captures structured stage transition timestamps and hardware measurements."""
        now = timestamp if timestamp is not None else time.time()
        job = self.orchestration_service.get_job(job_id)

        if job_id not in self._telemetry_records:
            rec = RenderJobTelemetryRecord(
                job_id=job_id,
                project_id=job.project_id if job else "",
                sequence_id=job.sequence_id if job else "",
                created_at=job.created_at if job else now,
            )
            if job and job.config:
                rec.container = job.config.container.value
                rec.video_codec = job.config.video_codec.value
                rec.resolution = f"{job.config.width}x{job.config.height}"
                rec.fps = getattr(job.config, "frame_rate", getattr(job.config, "fps", 24.0))
            self._telemetry_records[job_id] = rec
        else:
            rec = self._telemetry_records[job_id]

        if job:
            rec.worker_id = job.assigned_worker_id
            rec.final_state = job.state.value
            rec.is_output_verified = job.is_verified
            rec.output_size_bytes = job.output_size_bytes
            rec.retry_count = job.attempt_count
            if job.progress:
                rec.frames_processed = job.progress.frames_rendered
                rec.total_frames = job.progress.total_frames

        stage_up = stage.upper()
        if stage_up == "QUEUED":
            rec.queued_at = now
        elif stage_up == "SCHEDULED":
            rec.scheduled_at = now
        elif stage_up == "RENDERING" or stage_up == "PREPARING":
            if not rec.render_started_at:
                rec.render_started_at = now
        elif stage_up in ("FINALIZING", "VERIFYING"):
            if not rec.render_completed_at:
                rec.render_completed_at = now
        elif stage_up in ("COMPLETED", "FAILED", "CANCELLED"):
            rec.finalized_at = now
            if not rec.render_completed_at and rec.render_started_at:
                rec.render_completed_at = now

        if failure_reason:
            rec.failure_reason = failure_reason
            rec.failure_category = self.engine.classify_failure(failure_reason)

        if hardware_telemetry:
            rec.hardware = hardware_telemetry

        rec.calculate_durations()
        self._check_operational_alerts_for_job(rec)
        return rec

    def get_job_telemetry(self, job_id: str) -> Optional[RenderJobTelemetryRecord]:
        """Retrieves raw recorded telemetry for a given render job."""
        return self._telemetry_records.get(job_id)

    # =========================================================================
    # 2. Live Worker Fleet Monitoring
    # =========================================================================

    def get_worker_monitoring_snapshots(self) -> List[WorkerMonitoringSnapshot]:
        """Audits all registered workers from RemoteWorkerCoordinatorService."""
        snapshots = []
        now = time.time()
        for worker in self.remote_service.get_all_workers():
            delay = max(0.0, now - worker.last_heartbeat)
            is_alive = worker.is_alive(current_time=now)
            
            # Utilization
            active = len(worker.active_job_ids)
            max_c = max(1, worker.max_concurrent_jobs)
            util = min(100.0, (active / max_c) * 100.0)

            # Check status override if heartbeat timed out
            status_str = worker.status.value
            if not is_alive and worker.status != WorkerHealthStatus.REVOKED:
                status_str = WorkerHealthStatus.TIMEOUT.value

            snap = WorkerMonitoringSnapshot(
                worker_id=worker.worker_id,
                name=worker.name,
                status=status_str,
                is_alive=is_alive,
                last_heartbeat=worker.last_heartbeat,
                heartbeat_delay_seconds=delay,
                active_jobs_count=active,
                max_concurrent_jobs=max_c,
                utilization_percent=util,
                total_completed_jobs=worker.total_completed_jobs,
                total_failed_jobs=worker.total_failed_jobs,
                has_gpu=worker.has_gpu_acceleration,
                protocol_version=worker.protocol_version,
            )
            snapshots.append(snap)

            # Check for worker timeout alert
            if not is_alive and not worker.is_revoked:
                self.engine.evaluate_operational_alerts(
                    existing_alerts=self._alerts,
                    dedup_key=f"worker_timeout_{worker.worker_id}",
                    severity=OperationalAlertSeverity.ERROR,
                    title="Render Worker Heartbeat Timeout",
                    message=f"Worker '{worker.name}' ({worker.worker_id}) missed heartbeats for {delay:.1f}s.",
                    metadata={"worker_id": worker.worker_id, "delay_seconds": delay},
                )
            elif is_alive:
                # If healthy, resolve open timeout alert
                key = f"worker_timeout_{worker.worker_id}"
                if key in self._alerts and self._alerts[key].status == OperationalAlertStatus.OPEN:
                    self._alerts[key].status = OperationalAlertStatus.RESOLVED
                    self._alerts[key].resolved_at = now

        return snapshots

    # =========================================================================
    # 3. Queue Analytics & Metrics Aggregation
    # =========================================================================

    def get_queue_analytics(
        self,
        project_id: Optional[str] = None,
        time_window_seconds: Optional[float] = None,
        requesting_user_role: str = "admin",
    ) -> QueueAnalyticsSummary:
        """Aggregates queue metrics with project-level access control."""
        records = list(self._telemetry_records.values())

        # Filter by project if requested
        if project_id:
            records = [r for r in records if r.project_id == project_id]

        # Filter by time window if requested
        if time_window_seconds and time_window_seconds > 0:
            cutoff = time.time() - time_window_seconds
            records = [r for r in records if r.created_at >= cutoff]

        summary = self.engine.aggregate_queue_metrics(
            telemetry_records=records,
            time_window_seconds=time_window_seconds,
        )

        # Check queue backlog alerts
        if summary.queued_jobs > self.queue_backlog_warning_threshold:
            self.engine.evaluate_operational_alerts(
                existing_alerts=self._alerts,
                dedup_key="queue_backlog_high",
                severity=OperationalAlertSeverity.WARNING,
                title="Render Queue Backlog Exceeded Threshold",
                message=f"Queue backlog reached {summary.queued_jobs} jobs (threshold: {self.queue_backlog_warning_threshold}).",
                metadata={"queued_jobs": summary.queued_jobs},
            )
        else:
            if "queue_backlog_high" in self._alerts and self._alerts["queue_backlog_high"].status == OperationalAlertStatus.OPEN:
                self._alerts["queue_backlog_high"].status = OperationalAlertStatus.RESOLVED
                self._alerts["queue_backlog_high"].resolved_at = time.time()

        return summary

    # =========================================================================
    # 4. Cost Attribution
    # =========================================================================

    def configure_pricing_model(self, pricing: CostPricingModel) -> None:
        """Configures administrator rates for cost calculations."""
        self._pricing_model = pricing

    def get_pricing_model(self) -> CostPricingModel:
        return self._pricing_model

    def calculate_job_cost(self, job_id: str) -> JobCostAttribution:
        """Calculates cost attribution for a specific job."""
        rec = self._telemetry_records.get(job_id)
        if not rec:
            raise KeyError(f"No telemetry found for job '{job_id}'.")
        return self.engine.calculate_job_cost(rec, self._pricing_model)

    def calculate_project_costs(self, project_id: str) -> Dict[str, Any]:
        """Aggregates transparent estimated costs for a given project."""
        project_records = [r for r in self._telemetry_records.values() if r.project_id == project_id]
        attributions = [self.engine.calculate_job_cost(r, self._pricing_model) for r in project_records]

        total_est = sum(a.total_estimated_cost for a in attributions)
        total_worker_sec = sum(a.worker_seconds for a in attributions)
        total_gpu_sec = sum(a.gpu_seconds for a in attributions)
        total_bytes = sum(a.storage_bytes for a in attributions)

        return {
            "project_id": project_id,
            "currency": self._pricing_model.currency,
            "job_count": len(attributions),
            "total_estimated_cost": round(total_est, 4),
            "total_worker_seconds": round(total_worker_sec, 2),
            "total_gpu_seconds": round(total_gpu_sec, 2),
            "total_storage_bytes": total_bytes,
            "is_estimate": True,
            "rates_applied": self._pricing_model.to_dict(),
        }

    # =========================================================================
    # 5. Capacity Planning
    # =========================================================================

    def evaluate_farm_capacity(self, min_sample_size: int = 5) -> CapacityForecast:
        """Performs statistical capacity evaluation without synthetic guessing."""
        workers = self.remote_service.get_all_workers()
        total_workers = len(workers)
        total_slots = sum(w.max_concurrent_jobs for w in workers)
        active_slots = sum(len(w.active_job_ids) for w in workers)

        queued_jobs = sum(
            1 for r in self._telemetry_records.values()
            if r.final_state in ("QUEUED", "VALIDATING")
        )

        completed_records = [
            r for r in self._telemetry_records.values()
            if r.final_state == "COMPLETED"
        ]

        return self.engine.evaluate_capacity(
            total_workers=total_workers,
            total_slots=total_slots,
            active_slots=active_slots,
            queued_jobs=queued_jobs,
            completed_history=completed_records,
            min_sample_size=min_sample_size,
        )

    # =========================================================================
    # 6. Operational Alerting & Deduplication
    # =========================================================================

    def _check_operational_alerts_for_job(self, record: RenderJobTelemetryRecord) -> None:
        """Internal check evaluating alerts for individual job telemetry updates."""
        # Verification failure alert
        if record.final_state == "COMPLETED" and not record.is_output_verified:
            self.engine.evaluate_operational_alerts(
                existing_alerts=self._alerts,
                dedup_key=f"verification_failure_{record.job_id}",
                severity=OperationalAlertSeverity.ERROR,
                title="Render Output Verification Failure",
                message=f"Job '{record.job_id}' finished but failed SHA-256 or header verification.",
                metadata={"job_id": record.job_id, "project_id": record.project_id},
            )

        # Long running job alert
        if record.total_duration > self.job_duration_warning_seconds:
            self.engine.evaluate_operational_alerts(
                existing_alerts=self._alerts,
                dedup_key=f"long_running_job_{record.job_id}",
                severity=OperationalAlertSeverity.WARNING,
                title="Abnormally Long-Running Render Job",
                message=f"Job '{record.job_id}' elapsed {record.total_duration:.1f}s (> threshold {self.job_duration_warning_seconds}s).",
                metadata={"job_id": record.job_id, "duration": record.total_duration},
            )

    def get_alerts(self, status: Optional[OperationalAlertStatus] = None) -> List[OperationalAlert]:
        """Returns operational alerts filtered by status."""
        if status:
            return [a for a in self._alerts.values() if a.status == status]
        return list(self._alerts.values())

    def resolve_alert(self, alert_id: str) -> bool:
        """Marks an active alert as resolved."""
        for alert in self._alerts.values():
            if alert.alert_id == alert_id:
                alert.status = OperationalAlertStatus.RESOLVED
                alert.resolved_at = time.time()
                return True
        return False

    def dismiss_alert(self, alert_id: str) -> bool:
        """Dismisses an alert."""
        for alert in self._alerts.values():
            if alert.alert_id == alert_id:
                alert.status = OperationalAlertStatus.DISMISSED
                return True
        return False

    # =========================================================================
    # 7. Dashboard Overview Data Aggregator
    # =========================================================================

    def get_dashboard_overview(
        self,
        project_id: Optional[str] = None,
        requesting_role: str = "admin",
    ) -> Dict[str, Any]:
        """Generates comprehensive dashboard payload with real metrics, alerts, and capacity."""
        queue_summary = self.get_queue_analytics(project_id=project_id, requesting_user_role=requesting_role)
        worker_snapshots = self.get_worker_monitoring_snapshots() if requesting_role == "admin" else []
        capacity = self.evaluate_farm_capacity() if requesting_role == "admin" else None
        active_alerts = [a.to_dict() for a in self.get_alerts(OperationalAlertStatus.OPEN)]

        return {
            "schema_version": "video-studio.render-monitoring.v1",
            "timestamp": time.time(),
            "project_id": project_id,
            "requesting_role": requesting_role,
            "queue_summary": queue_summary.to_dict(),
            "worker_fleet": [w.to_dict() for w in worker_snapshots],
            "capacity_forecast": capacity.to_dict() if capacity else None,
            "pricing_model": self._pricing_model.to_dict(),
            "active_alerts": active_alerts,
        }

    # =========================================================================
    # 8. Telemetry Retention & Cleanup
    # =========================================================================

    def prune_old_telemetry(self, max_age_seconds: float) -> int:
        """Prunes historical telemetry older than max_age_seconds while keeping active jobs."""
        now = time.time()
        cutoff = now - max_age_seconds
        to_delete = []

        for j_id, rec in self._telemetry_records.items():
            if rec.final_state in ("COMPLETED", "CANCELLED", "FAILED"):
                final_t = rec.finalized_at or rec.render_completed_at or rec.created_at
                if final_t < cutoff:
                    to_delete.append(j_id)

        for j_id in to_delete:
            del self._telemetry_records[j_id]

        return len(to_delete)


# Singleton
render_monitoring_service = RenderMonitoringService()
