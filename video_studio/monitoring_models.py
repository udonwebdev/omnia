"""OMNIA Video Studio — Module 46: Render Farm Monitoring, Cost Attribution & Capacity Planning Models.

Authoritative domain models for:
- RenderOperationalMeasurementType: Hardware, telemetry, and duration measurement scopes.
- RenderJobTelemetryRecord: Structured execution profile, stage durations, frame stats, and resource metrics.
- WorkerMonitoringSnapshot: Live health, queue backlog, resource utilization, and error history.
- QueueAnalyticsSummary: Aggregated queue metrics, wait times, render durations, percentiles, and failure distribution.
- CostPricingModel: Administrator-configurable unit rates for CPU, GPU, worker hours, storage, and egress data transfer.
- JobCostAttribution: Transparent cost attribution breakdown distinguishing measured quantities from configured rates.
- CapacityForecast: Practical queue pressure, worker saturation, bottleneck detection, and confidence levels.
- OperationalAlertSeverity & OperationalAlert: Deduplicated incident alerts for worker dropouts, queue backlogs, and verification failures.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


MONITORING_SCHEMA_VERSION = "video-studio.render-monitoring.v1"


class OperationalAlertSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class OperationalAlertStatus(str, Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class RenderFailureCategory(str, Enum):
    """Structured taxonomy of render pipeline failures."""
    MISSING_MEDIA = "MISSING_MEDIA"
    INVALID_CONFIGURATION = "INVALID_CONFIGURATION"
    UNSUPPORTED_CODEC = "UNSUPPORTED_CODEC"
    WORKER_DISCONNECTED = "WORKER_DISCONNECTED"
    RESOURCE_EXHAUSTION = "RESOURCE_EXHAUSTION"
    ASSET_TRANSFER_FAILURE = "ASSET_TRANSFER_FAILURE"
    ENCODING_FAILURE = "ENCODING_FAILURE"
    OUTPUT_VERIFICATION_FAILURE = "OUTPUT_VERIFICATION_FAILURE"
    PERMISSION_FAILURE = "PERMISSION_FAILURE"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"
    UNKNOWN = "UNKNOWN"


@dataclass
class HardwareTelemetry:
    """Accurately captured hardware execution measurements. None indicates unmeasured."""
    cpu_utilization_percent: Optional[float] = None
    memory_used_mb: Optional[float] = None
    memory_peak_mb: Optional[float] = None
    gpu_utilization_percent: Optional[float] = None
    gpu_memory_used_mb: Optional[float] = None
    is_measured: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu_utilization_percent": self.cpu_utilization_percent,
            "memory_used_mb": self.memory_used_mb,
            "memory_peak_mb": self.memory_peak_mb,
            "gpu_utilization_percent": self.gpu_utilization_percent,
            "gpu_memory_used_mb": self.gpu_memory_used_mb,
            "is_measured": self.is_measured,
        }


@dataclass
class RenderJobTelemetryRecord:
    """Structured operational telemetry capturing the exact lifecycle of a render job."""
    telemetry_id: str = field(default_factory=lambda: f"telem_{uuid.uuid4().hex[:10]}")
    job_id: str = ""
    project_id: str = ""
    sequence_id: str = ""
    worker_id: Optional[str] = None
    
    # State & Verification
    final_state: str = "COMPLETED"
    is_output_verified: bool = False
    failure_category: RenderFailureCategory = RenderFailureCategory.UNKNOWN
    failure_reason: Optional[str] = None
    retry_count: int = 0

    # Lifecycle Timestamps
    created_at: float = field(default_factory=time.time)
    queued_at: Optional[float] = None
    scheduled_at: Optional[float] = None
    render_started_at: Optional[float] = None
    render_completed_at: Optional[float] = None
    finalized_at: Optional[float] = None

    # Measured Durations (in seconds)
    queue_wait_duration: float = 0.0
    preparation_duration: float = 0.0
    encoding_duration: float = 0.0
    verification_duration: float = 0.0
    total_duration: float = 0.0

    # Output & Transfer Volumes
    frames_processed: int = 0
    total_frames: int = 0
    output_size_bytes: int = 0
    asset_transfer_bytes: int = 0
    asset_transfer_duration: float = 0.0

    # Encoding Parameters
    container: str = "mp4"
    video_codec: str = "h264"
    resolution: str = "1920x1080"
    fps: float = 24.0

    # Hardware Telemetry
    hardware: HardwareTelemetry = field(default_factory=HardwareTelemetry)

    def calculate_durations(self) -> None:
        """Calculates exact stage durations from captured timestamps."""
        if self.queued_at and self.scheduled_at and self.scheduled_at >= self.queued_at:
            self.queue_wait_duration = max(0.0, self.scheduled_at - self.queued_at)
        elif self.created_at and self.scheduled_at and self.scheduled_at >= self.created_at:
            self.queue_wait_duration = max(0.0, self.scheduled_at - self.created_at)

        if self.scheduled_at and self.render_started_at and self.render_started_at >= self.scheduled_at:
            self.preparation_duration = max(0.0, self.render_started_at - self.scheduled_at)

        if self.render_started_at and self.render_completed_at and self.render_completed_at >= self.render_started_at:
            self.encoding_duration = max(0.0, self.render_completed_at - self.render_started_at)

        if self.render_completed_at and self.finalized_at and self.finalized_at >= self.render_completed_at:
            self.verification_duration = max(0.0, self.finalized_at - self.render_completed_at)

        if self.created_at and self.finalized_at and self.finalized_at >= self.created_at:
            self.total_duration = max(0.0, self.finalized_at - self.created_at)
        elif self.render_started_at and self.render_completed_at:
            self.total_duration = self.preparation_duration + self.encoding_duration + self.verification_duration

    def to_dict(self) -> Dict[str, Any]:
        return {
            "telemetry_id": self.telemetry_id,
            "job_id": self.job_id,
            "project_id": self.project_id,
            "sequence_id": self.sequence_id,
            "worker_id": self.worker_id,
            "final_state": self.final_state,
            "is_output_verified": self.is_output_verified,
            "failure_category": self.failure_category.value,
            "failure_reason": self.failure_reason,
            "retry_count": self.retry_count,
            "created_at": self.created_at,
            "queued_at": self.queued_at,
            "scheduled_at": self.scheduled_at,
            "render_started_at": self.render_started_at,
            "render_completed_at": self.render_completed_at,
            "finalized_at": self.finalized_at,
            "queue_wait_duration": round(self.queue_wait_duration, 3),
            "preparation_duration": round(self.preparation_duration, 3),
            "encoding_duration": round(self.encoding_duration, 3),
            "verification_duration": round(self.verification_duration, 3),
            "total_duration": round(self.total_duration, 3),
            "frames_processed": self.frames_processed,
            "total_frames": self.total_frames,
            "output_size_bytes": self.output_size_bytes,
            "asset_transfer_bytes": self.asset_transfer_bytes,
            "asset_transfer_duration": round(self.asset_transfer_duration, 3),
            "container": self.container,
            "video_codec": self.video_codec,
            "resolution": self.resolution,
            "fps": self.fps,
            "hardware": self.hardware.to_dict(),
        }


@dataclass
class WorkerMonitoringSnapshot:
    """Live state, capability profile, and telemetry summary for a single worker."""
    worker_id: str
    name: str
    status: str
    is_alive: bool
    last_heartbeat: float
    heartbeat_delay_seconds: float
    active_jobs_count: int
    max_concurrent_jobs: int
    utilization_percent: float
    total_completed_jobs: int
    total_failed_jobs: int
    has_gpu: bool
    protocol_version: str
    hardware_telemetry: Optional[HardwareTelemetry] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "name": self.name,
            "status": self.status,
            "is_alive": self.is_alive,
            "last_heartbeat": self.last_heartbeat,
            "heartbeat_delay_seconds": round(self.heartbeat_delay_seconds, 2),
            "active_jobs_count": self.active_jobs_count,
            "max_concurrent_jobs": self.max_concurrent_jobs,
            "utilization_percent": round(self.utilization_percent, 2),
            "total_completed_jobs": self.total_completed_jobs,
            "total_failed_jobs": self.total_failed_jobs,
            "has_gpu": self.has_gpu,
            "protocol_version": self.protocol_version,
            "hardware_telemetry": self.hardware_telemetry.to_dict() if self.hardware_telemetry else None,
        }


@dataclass
class QueueAnalyticsSummary:
    """Statistical evaluation of render queue throughput, durations, and failure patterns."""
    total_jobs: int = 0
    queued_jobs: int = 0
    active_jobs: int = 0
    completed_jobs: int = 0
    failed_jobs: int = 0
    cancelled_jobs: int = 0
    
    # Timing Statistics (seconds)
    avg_queue_wait_seconds: float = 0.0
    p50_queue_wait_seconds: float = 0.0
    p95_queue_wait_seconds: float = 0.0
    p99_queue_wait_seconds: float = 0.0

    avg_render_duration_seconds: float = 0.0
    p50_render_duration_seconds: float = 0.0
    p95_render_duration_seconds: float = 0.0
    p99_render_duration_seconds: float = 0.0

    throughput_jobs_per_hour: float = 0.0
    failure_rate_percent: float = 0.0
    retry_success_rate_percent: float = 0.0
    verification_failure_count: int = 0

    failure_breakdown_by_category: Dict[str, int] = field(default_factory=dict)
    worker_distribution: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_jobs": self.total_jobs,
            "queued_jobs": self.queued_jobs,
            "active_jobs": self.active_jobs,
            "completed_jobs": self.completed_jobs,
            "failed_jobs": self.failed_jobs,
            "cancelled_jobs": self.cancelled_jobs,
            "avg_queue_wait_seconds": round(self.avg_queue_wait_seconds, 2),
            "p50_queue_wait_seconds": round(self.p50_queue_wait_seconds, 2),
            "p95_queue_wait_seconds": round(self.p95_queue_wait_seconds, 2),
            "p99_queue_wait_seconds": round(self.p99_queue_wait_seconds, 2),
            "avg_render_duration_seconds": round(self.avg_render_duration_seconds, 2),
            "p50_render_duration_seconds": round(self.p50_render_duration_seconds, 2),
            "p95_render_duration_seconds": round(self.p95_render_duration_seconds, 2),
            "p99_render_duration_seconds": round(self.p99_render_duration_seconds, 2),
            "throughput_jobs_per_hour": round(self.throughput_jobs_per_hour, 2),
            "failure_rate_percent": round(self.failure_rate_percent, 2),
            "retry_success_rate_percent": round(self.retry_success_rate_percent, 2),
            "verification_failure_count": self.verification_failure_count,
            "failure_breakdown_by_category": dict(self.failure_breakdown_by_category),
            "worker_distribution": dict(self.worker_distribution),
        }


@dataclass
class CostPricingModel:
    """Configurable baseline rates for compute, worker time, storage, and transfers."""
    currency: str = "USD"
    worker_hour_rate: float = 0.50          # Cost per active worker wall-clock hour
    gpu_hour_rate: float = 1.25             # Cost per GPU active compute hour
    cpu_core_hour_rate: float = 0.08        # Cost per CPU core execution hour
    storage_gb_month_rate: float = 0.02     # Cost per GB-month of stored output
    transfer_gb_rate: float = 0.05          # Cost per GB of egress/transfer

    def to_dict(self) -> Dict[str, Any]:
        return {
            "currency": self.currency,
            "worker_hour_rate": self.worker_hour_rate,
            "gpu_hour_rate": self.gpu_hour_rate,
            "cpu_core_hour_rate": self.cpu_core_hour_rate,
            "storage_gb_month_rate": self.storage_gb_month_rate,
            "transfer_gb_rate": self.transfer_gb_rate,
        }


@dataclass
class JobCostAttribution:
    """Transparently decomposed render job cost attribution based on measured resource metrics."""
    job_id: str
    project_id: str
    currency: str = "USD"
    
    # Measured resource quantities
    worker_seconds: float = 0.0
    gpu_seconds: float = 0.0
    storage_bytes: int = 0
    transfer_bytes: int = 0
    
    # Calculated cost elements
    worker_compute_cost: float = 0.0
    gpu_compute_cost: float = 0.0
    storage_cost: float = 0.0
    transfer_cost: float = 0.0
    total_estimated_cost: float = 0.0

    is_estimate: bool = True
    pricing_model: CostPricingModel = field(default_factory=CostPricingModel)

    def calculate(self, pricing: CostPricingModel) -> None:
        """Computes cost elements from measured quantities using provided rate configuration."""
        self.pricing_model = pricing
        self.currency = pricing.currency

        # Worker wall-clock hours
        worker_hours = max(0.0, self.worker_seconds / 3600.0)
        self.worker_compute_cost = worker_hours * pricing.worker_hour_rate

        # GPU compute hours
        gpu_hours = max(0.0, self.gpu_seconds / 3600.0)
        self.gpu_compute_cost = gpu_hours * pricing.gpu_hour_rate

        # Output Storage (assuming 1 month standard staging retention)
        gb_stored = max(0.0, self.storage_bytes / (1024.0 ** 3))
        self.storage_cost = gb_stored * pricing.storage_gb_month_rate

        # Data Transfer / Ingestion
        gb_transferred = max(0.0, self.transfer_bytes / (1024.0 ** 3))
        self.transfer_cost = gb_transferred * pricing.transfer_gb_rate

        self.total_estimated_cost = (
            self.worker_compute_cost + self.gpu_compute_cost + self.storage_cost + self.transfer_cost
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "project_id": self.project_id,
            "currency": self.currency,
            "worker_seconds": round(self.worker_seconds, 2),
            "gpu_seconds": round(self.gpu_seconds, 2),
            "storage_bytes": self.storage_bytes,
            "transfer_bytes": self.transfer_bytes,
            "worker_compute_cost": round(self.worker_compute_cost, 4),
            "gpu_compute_cost": round(self.gpu_compute_cost, 4),
            "storage_cost": round(self.storage_cost, 4),
            "transfer_cost": round(self.transfer_cost, 4),
            "total_estimated_cost": round(self.total_estimated_cost, 4),
            "is_estimate": self.is_estimate,
        }


@dataclass
class CapacityForecast:
    """Evaluates farm load pressure, worker capacity saturation, and bottleneck predictions."""
    is_available: bool = False
    sample_size: int = 0
    rejection_reason: Optional[str] = None
    
    current_worker_count: int = 0
    total_slot_capacity: int = 0
    occupied_slots: int = 0
    worker_saturation_percent: float = 0.0

    current_queue_depth: int = 0
    estimated_wait_time_minutes: float = 0.0
    throughput_jobs_per_hour: float = 0.0
    identified_bottlenecks: List[str] = field(default_factory=list)
    recommended_workers: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_available": self.is_available,
            "sample_size": self.sample_size,
            "rejection_reason": self.rejection_reason,
            "current_worker_count": self.current_worker_count,
            "total_slot_capacity": self.total_slot_capacity,
            "occupied_slots": self.occupied_slots,
            "worker_saturation_percent": round(self.worker_saturation_percent, 2),
            "current_queue_depth": self.current_queue_depth,
            "estimated_wait_time_minutes": round(self.estimated_wait_time_minutes, 2),
            "throughput_jobs_per_hour": round(self.throughput_jobs_per_hour, 2),
            "identified_bottlenecks": list(self.identified_bottlenecks),
            "recommended_workers": self.recommended_workers,
        }


@dataclass
class OperationalAlert:
    """Deduplicated incident notification for operational farm events."""
    alert_id: str = field(default_factory=lambda: f"alert_{uuid.uuid4().hex[:8]}")
    dedup_key: str = ""
    severity: OperationalAlertSeverity = OperationalAlertSeverity.WARNING
    status: OperationalAlertStatus = OperationalAlertStatus.OPEN
    title: str = ""
    message: str = ""
    source: str = "RenderMonitoring"
    occurred_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    occurrence_count: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "dedup_key": self.dedup_key,
            "severity": self.severity.value,
            "status": self.status.value,
            "title": self.title,
            "message": self.message,
            "source": self.source,
            "occurred_at": self.occurred_at,
            "updated_at": self.updated_at,
            "resolved_at": self.resolved_at,
            "occurrence_count": self.occurrence_count,
            "metadata": dict(self.metadata),
        }
