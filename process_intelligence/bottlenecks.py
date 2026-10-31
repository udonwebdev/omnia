"""
Omnia Module 39: Autonomous Workflow Optimization & Process Intelligence Engine.
Bottleneck Detection Engine: Queue Waiting, Approval Delays & Contention.
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from process_intelligence.models import (
    BottleneckFinding,
    BottleneckType,
    FindingSeverity,
    ProcessEventType,
)
from process_intelligence.persistence import ProcessIntelligenceRepository

logger = logging.getLogger("Omnia.Process.Bottlenecks")


class BottleneckDetectionEngine:
    """
    Identifies evidence-backed bottlenecks across workflow tasks:
    queue delays, repeated approval stalls, high retry rates, and serial execution bottlenecks.
    """

    def __init__(self, repository: Optional[ProcessIntelligenceRepository] = None):
        self.repo = repository or ProcessIntelligenceRepository()

    def detect_bottlenecks(self, workflow_id: str) -> List[BottleneckFinding]:
        """Scans all events and traces for a workflow to pinpoint structural bottlenecks."""
        traces = self.repo.list_traces_for_workflow(workflow_id)
        if not traces:
            return []

        task_wait_times: dict[str, list[float]] = {}
        task_durations: dict[str, list[float]] = {}
        task_retries: dict[str, int] = {}
        supporting_traces: dict[str, list[str]] = {}

        for t in traces:
            events = self.repo.list_events_for_trace(t.trace_id)
            for evt in events:
                tid = evt.task_id
                if tid not in task_wait_times:
                    task_wait_times[tid] = []
                    task_durations[tid] = []
                    task_retries[tid] = 0
                    supporting_traces[tid] = []

                task_wait_times[tid].append(evt.waiting_time_sec)
                task_durations[tid].append(evt.duration_sec)
                if evt.event_type == ProcessEventType.TASK_RETRY:
                    task_retries[tid] += 1
                if t.trace_id not in supporting_traces[tid]:
                    supporting_traces[tid].append(t.trace_id)

        findings: List[BottleneckFinding] = []
        n_traces = len(traces)

        for tid, waits in task_wait_times.items():
            avg_wait = sum(waits) / len(waits) if waits else 0.0
            avg_duration = sum(task_durations[tid]) / len(task_durations[tid]) if task_durations[tid] else 0.0
            retries = task_retries.get(tid, 0)
            traces_involved = supporting_traces.get(tid, [])

            # Bottleneck 1: Excessive Queue Waiting
            if avg_wait > 5.0:
                sev = FindingSeverity.HIGH if avg_wait > 15.0 else FindingSeverity.MEDIUM
                f = BottleneckFinding(
                    finding_id=f"bn-{uuid.uuid4().hex[:8]}",
                    workflow_id=workflow_id,
                    component_id=tid,
                    bottleneck_type=BottleneckType.QUEUE_WAITING,
                    severity=sev,
                    estimated_delay_sec=round(avg_wait, 2),
                    frequency_ratio=round(len(traces_involved) / n_traces, 2),
                    confidence=0.92,
                    potential_causes=["Resource pool saturation", "Worker starvation", "Lock contention"],
                    recommended_action="Increase worker allocation or implement non-blocking asynchronous dispatch.",
                    supporting_trace_ids=traces_involved[:5],
                )
                self.repo.save_bottleneck(f)
                findings.append(f)

            # Bottleneck 2: Approval Gate Delay
            if "approval" in tid.lower() and avg_wait > 30.0:
                f = BottleneckFinding(
                    finding_id=f"bn-{uuid.uuid4().hex[:8]}",
                    workflow_id=workflow_id,
                    component_id=tid,
                    bottleneck_type=BottleneckType.APPROVAL_DELAY,
                    severity=FindingSeverity.HIGH,
                    estimated_delay_sec=round(avg_wait, 2),
                    frequency_ratio=round(len(traces_involved) / n_traces, 2),
                    confidence=0.95,
                    potential_causes=["Human operator unavailable", "Unautomated policy review"],
                    recommended_action="Automate policy pre-checks via Module 09 or implement timeout alerts.",
                    supporting_trace_ids=traces_involved[:5],
                )
                self.repo.save_bottleneck(f)
                findings.append(f)

            # Bottleneck 3: Retry Loop / Unreliable Task
            if retries >= n_traces * 0.5:
                f = BottleneckFinding(
                    finding_id=f"bn-{uuid.uuid4().hex[:8]}",
                    workflow_id=workflow_id,
                    component_id=tid,
                    bottleneck_type=BottleneckType.RETRY_LOOP,
                    severity=FindingSeverity.CRITICAL if retries > n_traces else FindingSeverity.HIGH,
                    estimated_delay_sec=round(retries * 2.5, 2),
                    frequency_ratio=round(retries / n_traces, 2),
                    confidence=0.88,
                    potential_causes=["Transient downstream timeouts", "Flaky third-party dependency"],
                    recommended_action="Introduce circuit breakers, exponential backoff, and idempotent caching.",
                    supporting_trace_ids=traces_involved[:5],
                )
                self.repo.save_bottleneck(f)
                findings.append(f)

        logger.info(f"Detected {len(findings)} bottlenecks for workflow '{workflow_id}'")
        return findings
