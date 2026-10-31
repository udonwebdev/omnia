"""
Omnia Module 39: Autonomous Workflow Optimization & Process Intelligence Engine.
Workflow Discovery & Execution Trace Normalizer.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from process_intelligence.models import (
    ExecutionTraceRecord,
    ProcessEventRecord,
    ProcessEventType,
    TraceStatus,
)
from process_intelligence.persistence import ProcessIntelligenceRepository

logger = logging.getLogger("Omnia.Process.Discovery")


class WorkflowDiscoveryEngine:
    """
    Ingests raw process events, normalizes timestamps, reconstructs execution traces,
    and calculates active execution duration vs passive waiting periods.
    Never invents missing events.
    """

    def __init__(self, repository: Optional[ProcessIntelligenceRepository] = None):
        self.repo = repository or ProcessIntelligenceRepository()

    def record_process_event(
        self,
        trace_id: str,
        workflow_id: str,
        task_id: str,
        event_type: ProcessEventType,
        timestamp: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        duration_sec: float = 0.0,
        waiting_time_sec: float = 0.0,
        error_category: Optional[str] = None,
        resource_id: Optional[str] = None,
        metadata_payload: Optional[Dict[str, Any]] = None,
        event_id: Optional[str] = None,
    ) -> ProcessEventRecord:
        """Records a normalized process event and ensures the trace container exists."""
        eid = event_id or f"evt-{uuid.uuid4().hex[:8]}"
        ts = timestamp or datetime.now(timezone.utc).isoformat()

        event = ProcessEventRecord(
            event_id=eid,
            trace_id=trace_id,
            workflow_id=workflow_id,
            task_id=task_id,
            parent_task_id=parent_task_id,
            event_type=event_type,
            timestamp=ts,
            duration_sec=max(0.0, duration_sec),
            waiting_time_sec=max(0.0, waiting_time_sec),
            error_category=error_category,
            resource_id=resource_id,
            metadata_payload=metadata_payload or {},
        )
        self.repo.save_event(event)

        # Update trace metadata
        trace = self.repo.get_trace(trace_id)
        if not trace:
            trace = ExecutionTraceRecord(
                trace_id=trace_id,
                workflow_id=workflow_id,
                execution_id=trace_id,
                status=TraceStatus.RUNNING,
                started_at=ts,
                completed_at=None,
                total_duration_sec=0.0,
                total_waiting_sec=0.0,
                total_active_sec=0.0,
                retry_count=0,
                failure_count=0,
                is_complete=False,
                events_count=1,
            )
        else:
            trace.events_count += 1
            if event_type == ProcessEventType.TASK_RETRY:
                trace.retry_count += 1
            elif event_type == ProcessEventType.TASK_FAIL:
                trace.failure_count += 1

        self.repo.save_trace(trace)
        return event

    def reconstruct_trace(self, trace_id: str) -> ExecutionTraceRecord:
        """
        Reconstructs the trace by sorting events chronologically, calculating cumulative
        active and waiting durations, and determining terminal completion state.
        """
        trace = self.repo.get_trace(trace_id)
        if not trace:
            raise ValueError(f"Execution trace '{trace_id}' not found.")

        events = self.repo.list_events_for_trace(trace_id)
        if not events:
            return trace

        # Sort chronologically by ISO-8601 timestamp to handle out-of-order delivery
        sorted_events = sorted(events, key=lambda e: e.timestamp)

        total_active = sum(e.duration_sec for e in sorted_events)
        total_waiting = sum(e.waiting_time_sec for e in sorted_events)
        retries = sum(1 for e in sorted_events if e.event_type == ProcessEventType.TASK_RETRY)
        failures = sum(1 for e in sorted_events if e.event_type == ProcessEventType.TASK_FAIL)

        start_time_iso = sorted_events[0].timestamp
        end_time_iso = sorted_events[-1].timestamp

        # Check if terminal state achieved
        last_evt = sorted_events[-1]
        if last_evt.event_type in (ProcessEventType.TASK_COMPLETE, ProcessEventType.APPROVAL_GRANT):
            status = TraceStatus.COMPLETED
            is_complete = True
            completed_at = end_time_iso
        elif last_evt.event_type in (ProcessEventType.TASK_FAIL, ProcessEventType.APPROVAL_REJECT):
            status = TraceStatus.FAILED
            is_complete = True
            completed_at = end_time_iso
        else:
            status = TraceStatus.RUNNING
            is_complete = False
            completed_at = None

        total_duration = total_active + total_waiting

        updated_trace = ExecutionTraceRecord(
            trace_id=trace.trace_id,
            workflow_id=trace.workflow_id,
            execution_id=trace.execution_id,
            status=status,
            started_at=start_time_iso,
            completed_at=completed_at,
            total_duration_sec=round(total_duration, 4),
            total_waiting_sec=round(total_waiting, 4),
            total_active_sec=round(total_active, 4),
            retry_count=retries,
            failure_count=failures,
            is_complete=is_complete,
            events_count=len(sorted_events),
        )
        self.repo.save_trace(updated_trace)
        logger.info(
            f"Reconstructed trace '{trace_id}': Active={total_active:.2f}s, Wait={total_waiting:.2f}s, Complete={is_complete}"
        )
        return updated_trace
