"""OMNIA Video Studio — Module 46: Render Farm Monitoring & Analytics Engine.

Pure mathematical and algorithmic engine providing:
1. Percentile calculations (p50, p95, p99) without external heavy dependencies.
2. Queue throughput and duration aggregations.
3. Transparent cost calculations strictly based on measured telemetry and pricing configurations.
4. Capacity forecasting and saturation modeling with honest sample-size validation.
5. Deterministic failure classification taxonomy.
6. Operational alert deduplication and lifecycle state machine.
"""

from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional, Tuple

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
)


class RenderMonitoringEngine:
    """Pure algorithmic calculations for render farm telemetry and cost analytics."""

    # =========================================================================
    # 1. Statistical & Percentile Calculations
    # =========================================================================

    @staticmethod
    def calculate_percentile(values: List[float], percentile: float) -> float:
        """Calculates exact nearest-rank percentile for a list of floats.
        
        percentile must be between 0.0 and 100.0.
        """
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        if percentile <= 0.0:
            return sorted_vals[0]
        if percentile >= 100.0:
            return sorted_vals[-1]

        k = (len(sorted_vals) - 1) * (percentile / 100.0)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return float(sorted_vals[int(k)])
        d0 = sorted_vals[int(f)] * (c - k)
        d1 = sorted_vals[int(c)] * (k - f)
        return float(d0 + d1)

    @classmethod
    def aggregate_queue_metrics(
        cls,
        telemetry_records: List[RenderJobTelemetryRecord],
        time_window_seconds: Optional[float] = None,
    ) -> QueueAnalyticsSummary:
        """Aggregates queue telemetry records into operational analytics."""
        summary = QueueAnalyticsSummary()
        if not telemetry_records:
            return summary

        summary.total_jobs = len(telemetry_records)
        wait_times: List[float] = []
        render_durations: List[float] = []
        failure_counts: Dict[str, int] = {}
        worker_counts: Dict[str, int] = {}
        retried_jobs = 0
        retried_successes = 0

        min_time = float("inf")
        max_time = float("-inf")

        for rec in telemetry_records:
            # Lifecycle counts
            state = rec.final_state.upper()
            if state == "COMPLETED":
                summary.completed_jobs += 1
            elif state == "FAILED":
                summary.failed_jobs += 1
            elif state == "CANCELLED":
                summary.cancelled_jobs += 1
            elif state in ("QUEUED", "VALIDATING"):
                summary.queued_jobs += 1
            else:
                summary.active_jobs += 1

            # Output verification failures
            if not rec.is_output_verified and state == "COMPLETED":
                summary.verification_failure_count += 1

            # Failures taxonomy
            if rec.failure_category != RenderFailureCategory.UNKNOWN or state == "FAILED":
                cat_name = rec.failure_category.value
                failure_counts[cat_name] = failure_counts.get(cat_name, 0) + 1

            # Worker assignments
            if rec.worker_id:
                worker_counts[rec.worker_id] = worker_counts.get(rec.worker_id, 0) + 1

            # Retries
            if rec.retry_count > 0:
                retried_jobs += 1
                if state == "COMPLETED":
                    retried_successes += 1

            # Durations
            if rec.queue_wait_duration > 0.0:
                wait_times.append(rec.queue_wait_duration)
            if rec.encoding_duration > 0.0 or rec.total_duration > 0.0:
                # Use total render execution (prep + encode + verify)
                dur = (rec.preparation_duration + rec.encoding_duration + rec.verification_duration)
                if dur > 0.0:
                    render_durations.append(dur)

            # Window boundary tracking
            if rec.created_at:
                min_time = min(min_time, rec.created_at)
                max_time = max(max_time, rec.finalized_at or rec.render_completed_at or rec.created_at)

        # Durations & Percentiles
        if wait_times:
            summary.avg_queue_wait_seconds = sum(wait_times) / len(wait_times)
            summary.p50_queue_wait_seconds = cls.calculate_percentile(wait_times, 50.0)
            summary.p95_queue_wait_seconds = cls.calculate_percentile(wait_times, 95.0)
            summary.p99_queue_wait_seconds = cls.calculate_percentile(wait_times, 99.0)

        if render_durations:
            summary.avg_render_duration_seconds = sum(render_durations) / len(render_durations)
            summary.p50_render_duration_seconds = cls.calculate_percentile(render_durations, 50.0)
            summary.p95_render_duration_seconds = cls.calculate_percentile(render_durations, 95.0)
            summary.p99_render_duration_seconds = cls.calculate_percentile(render_durations, 99.0)

        # Rates & Throughput
        if summary.total_jobs > 0:
            summary.failure_rate_percent = (summary.failed_jobs / summary.total_jobs) * 100.0

        if retried_jobs > 0:
            summary.retry_success_rate_percent = (retried_successes / retried_jobs) * 100.0

        # Throughput jobs per hour
        total_time_span = time_window_seconds
        if not total_time_span and max_time > min_time:
            total_time_span = max_time - min_time

        if total_time_span and total_time_span > 0:
            hours = total_time_span / 3600.0
            summary.throughput_jobs_per_hour = summary.completed_jobs / hours if hours > 0 else 0.0
        else:
            summary.throughput_jobs_per_hour = float(summary.completed_jobs)

        summary.failure_breakdown_by_category = failure_counts
        summary.worker_distribution = worker_counts
        return summary

    # =========================================================================
    # 2. Transparent Cost Attribution
    # =========================================================================

    @staticmethod
    def calculate_job_cost(
        record: RenderJobTelemetryRecord,
        pricing: CostPricingModel,
    ) -> JobCostAttribution:
        """Calculates precise cost attribution from real measured telemetry."""
        attribution = JobCostAttribution(
            job_id=record.job_id,
            project_id=record.project_id,
            worker_seconds=record.total_duration,
            gpu_seconds=record.encoding_duration if (record.hardware.gpu_utilization_percent or 0) > 0 else 0.0,
            storage_bytes=record.output_size_bytes,
            transfer_bytes=record.asset_transfer_bytes,
            is_estimate=True,
        )
        attribution.calculate(pricing)
        return attribution

    # =========================================================================
    # 3. Capacity & Saturation Forecasting
    # =========================================================================

    @classmethod
    def evaluate_capacity(
        cls,
        total_workers: int,
        total_slots: int,
        active_slots: int,
        queued_jobs: int,
        completed_history: List[RenderJobTelemetryRecord],
        min_sample_size: int = 5,
    ) -> CapacityForecast:
        """Generates honest capacity prediction only if sufficient historical samples exist."""
        forecast = CapacityForecast(
            current_worker_count=total_workers,
            total_slot_capacity=total_slots,
            occupied_slots=active_slots,
            current_queue_depth=queued_jobs,
            sample_size=len(completed_history),
        )

        if total_slots > 0:
            forecast.worker_saturation_percent = min(100.0, (active_slots / total_slots) * 100.0)
        else:
            forecast.worker_saturation_percent = 100.0 if queued_jobs > 0 else 0.0

        # Enforce requirement: do not manufacture predictions if history is insufficient
        if len(completed_history) < min_sample_size:
            forecast.is_available = False
            forecast.rejection_reason = (
                f"Insufficient historical samples: require at least {min_sample_size} completed jobs, "
                f"got {len(completed_history)}."
            )
            return forecast

        # Calculate average job render duration from valid history
        durations = [
            (r.preparation_duration + r.encoding_duration + r.verification_duration)
            for r in completed_history
            if (r.preparation_duration + r.encoding_duration + r.verification_duration) > 0
        ]
        if not durations:
            forecast.is_available = False
            forecast.rejection_reason = "No measurable render durations recorded in history."
            return forecast

        avg_duration_sec = sum(durations) / len(durations)
        slots = max(1, total_slots)

        # Throughput: slots * (3600 / avg_duration_sec)
        hourly_throughput_per_slot = 3600.0 / avg_duration_sec if avg_duration_sec > 0 else 0.0
        forecast.throughput_jobs_per_hour = slots * hourly_throughput_per_slot

        # Expected wait time for the queue: (queued_jobs / slots) * avg_duration_sec in minutes
        expected_wait_sec = (queued_jobs / slots) * avg_duration_sec
        forecast.estimated_wait_time_minutes = expected_wait_sec / 60.0

        # Bottlenecks
        bottlenecks = []
        if forecast.worker_saturation_percent >= 90.0:
            bottlenecks.append("WORKER_CONCURRENCY_EXHAUSTION")
        if queued_jobs > (total_slots * 2):
            bottlenecks.append("HIGH_QUEUE_BACKLOG")
        if total_workers == 0:
            bottlenecks.append("NO_REGISTERED_WORKERS")

        forecast.identified_bottlenecks = bottlenecks

        # Recommended workers to clear queue within 30 minutes
        if avg_duration_sec > 0 and queued_jobs > 0:
            target_seconds = 1800.0 # 30 mins
            required_slots = math.ceil((queued_jobs * avg_duration_sec) / target_seconds)
            forecast.recommended_workers = max(total_workers, required_slots)
        else:
            forecast.recommended_workers = total_workers

        forecast.is_available = True
        return forecast

    # =========================================================================
    # 4. Failure Categorization
    # =========================================================================

    @staticmethod
    def classify_failure(error_message: Optional[str]) -> RenderFailureCategory:
        """Maps arbitrary operational errors to structured failure categories."""
        if not error_message:
            return RenderFailureCategory.UNKNOWN

        msg = error_message.lower()
        if "missing media" in msg or "asset not found" in msg or "file not found" in msg or "no such file" in msg:
            return RenderFailureCategory.MISSING_MEDIA
        if "invalid configuration" in msg or "invalid parameter" in msg or "resolution" in msg:
            return RenderFailureCategory.INVALID_CONFIGURATION
        if "unsupported codec" in msg or "unknown codec" in msg or "format not supported" in msg:
            return RenderFailureCategory.UNSUPPORTED_CODEC
        if "heartbeat" in msg or "disconnect" in msg or "timeout" in msg or "worker unreachable" in msg:
            return RenderFailureCategory.WORKER_DISCONNECTED
        if "memory" in msg or "oom" in msg or "disk full" in msg or "exhausted" in msg:
            return RenderFailureCategory.RESOURCE_EXHAUSTION
        if "transfer" in msg or "chunk" in msg or "checksum" in msg or "corrupted payload" in msg:
            return RenderFailureCategory.ASSET_TRANSFER_FAILURE
        if "encode" in msg or "ffmpeg" in msg or "muxer" in msg or "codec error" in msg:
            return RenderFailureCategory.ENCODING_FAILURE
        if "verification" in msg or "corrupt output" in msg or "header check failed" in msg:
            return RenderFailureCategory.OUTPUT_VERIFICATION_FAILURE
        if "permission" in msg or "access denied" in msg or "unauthorized" in msg:
            return RenderFailureCategory.PERMISSION_FAILURE
        if "connection refused" in msg or "socket" in msg or "network down" in msg:
            return RenderFailureCategory.INFRASTRUCTURE_FAILURE

        return RenderFailureCategory.UNKNOWN

    # =========================================================================
    # 5. Alert Deduplication & Evaluation
    # =========================================================================

    @staticmethod
    def evaluate_operational_alerts(
        existing_alerts: Dict[str, OperationalAlert],
        dedup_key: str,
        severity: OperationalAlertSeverity,
        title: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> OperationalAlert:
        """Deduplicates alerts by key: updates existing open alert or creates new one."""
        if dedup_key in existing_alerts:
            alert = existing_alerts[dedup_key]
            if alert.status in (OperationalAlertStatus.OPEN, OperationalAlertStatus.ACKNOWLEDGED):
                alert.occurrence_count += 1
                alert.updated_at = time.time()
                alert.severity = severity
                alert.message = message
                if metadata:
                    alert.metadata.update(metadata)
                return alert

        # Create new alert
        new_alert = OperationalAlert(
            dedup_key=dedup_key,
            severity=severity,
            status=OperationalAlertStatus.OPEN,
            title=title,
            message=message,
            occurred_at=time.time(),
            updated_at=time.time(),
            occurrence_count=1,
            metadata=dict(metadata or {}),
        )
        existing_alerts[dedup_key] = new_alert
        return new_alert
