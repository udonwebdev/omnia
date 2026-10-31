"""
Omnia Module 39: Autonomous Workflow Optimization & Process Intelligence Engine.
Failure Pattern Detector & Rework Cost Analyzer.
"""

from __future__ import annotations

import logging
import uuid
from typing import Dict, List, Optional

from process_intelligence.models import (
    FailurePatternRecord,
    ProcessEventType,
)
from process_intelligence.persistence import ProcessIntelligenceRepository

logger = logging.getLogger("Omnia.Process.Failures")


class FailurePatternDetector:
    """
    Groups recurring execution failures into error clusters, measures rework duration,
    and estimates operational cost overhead from failed operations.
    """

    def __init__(self, repository: Optional[ProcessIntelligenceRepository] = None):
        self.repo = repository or ProcessIntelligenceRepository()

    def analyze_failure_patterns(
        self,
        workflow_id: str,
        hourly_compute_rate: float = 30.0,
    ) -> List[FailurePatternRecord]:
        """Clusters failures by error category and computes cumulative rework cost."""
        traces = self.repo.list_traces_for_workflow(workflow_id)
        if not traces:
            return []

        error_clusters: Dict[str, dict] = {}

        for t in traces:
            events = self.repo.list_events_for_trace(t.trace_id)
            for evt in events:
                if evt.event_type in (ProcessEventType.TASK_FAIL, ProcessEventType.TASK_RETRY) and evt.error_category:
                    err = evt.error_category
                    if err not in error_clusters:
                        error_clusters[err] = {
                            "tasks": set(),
                            "count": 0,
                            "rework_sec": 0.0,
                        }
                    error_clusters[err]["tasks"].add(evt.task_id)
                    error_clusters[err]["count"] += 1
                    error_clusters[err]["rework_sec"] += evt.duration_sec

        records: List[FailurePatternRecord] = []
        for err, data in error_clusters.items():
            rework_hours = data["rework_sec"] / 3600.0
            cost = rework_hours * hourly_compute_rate
            rec = FailurePatternRecord(
                pattern_id=f"fail-{uuid.uuid4().hex[:8]}",
                workflow_id=workflow_id,
                error_type=err,
                affected_tasks=list(data["tasks"]),
                occurrence_count=data["count"],
                total_rework_duration_sec=round(data["rework_sec"], 2),
                estimated_rework_cost=round(cost, 2),
            )
            self.repo.save_failure_pattern(rec)
            records.append(rec)

        logger.info(f"Identified {len(records)} failure clusters for workflow '{workflow_id}'")
        return records
