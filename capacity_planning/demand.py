"""
Omnia Module 42: Autonomous Capacity Planning, Infrastructure Forecasting & Elastic Resource Intelligence.
Workload Demand Analyzer: Workload Characterization, Burstiness, and Concurrency Intelligence.
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from capacity_planning.models import (
    WorkloadCategory,
    WorkloadDemandProfile,
)
from capacity_planning.persistence import CapacityRepository

logger = logging.getLogger("Omnia.Capacity.Demand")


class WorkloadDemandAnalyzer:
    """
    Analyzes workload profiles, resource consumption patterns, burstiness indices,
    and concurrency requirements by workload category.
    Integrates with Module 21 Scheduler demand tracking.
    """

    def __init__(self, repository: Optional[CapacityRepository] = None):
        self.repo = repository or CapacityRepository()

    def record_workload_demand(
        self,
        category: WorkloadCategory,
        workload_name: str,
        cpu_consumption: float,
        memory_mb: float,
        duration_sec: float,
        request_rate_per_sec: float = 0.0,
        peak_cpu_consumption: Optional[float] = None,
        concurrency_requirement: int = 1,
    ) -> WorkloadDemandProfile:
        """
        Records or updates a workload demand profile.
        Calculates burstiness index (peak / avg) and updates rolling averages.
        """
        existing = [p for p in self.repo.list_workload_demands() if p.workload_name == workload_name]
        
        peak_cpu = peak_cpu_consumption if peak_cpu_consumption is not None else cpu_consumption
        burst_index = (peak_cpu / max(0.001, cpu_consumption)) if cpu_consumption > 0 else 1.0

        if existing:
            p = existing[0]
            # Rolling update
            n = p.sample_count
            new_n = n + 1
            p.avg_cpu_consumption = round((p.avg_cpu_consumption * n + cpu_consumption) / new_n, 4)
            p.avg_memory_mb = round((p.avg_memory_mb * n + memory_mb) / new_n, 2)
            p.avg_duration_sec = round((p.avg_duration_sec * n + duration_sec) / new_n, 2)
            p.request_rate_per_sec = round((p.request_rate_per_sec * n + request_rate_per_sec) / new_n, 2)
            p.burstiness_index = round(max(p.burstiness_index, burst_index), 2)
            p.concurrency_requirement = max(p.concurrency_requirement, concurrency_requirement)
            p.sample_count = new_n
        else:
            pid = f"wdp-{uuid.uuid4().hex[:8]}"
            p = WorkloadDemandProfile(
                profile_id=pid,
                category=category,
                workload_name=workload_name,
                avg_cpu_consumption=round(cpu_consumption, 4),
                avg_memory_mb=round(memory_mb, 2),
                avg_duration_sec=round(duration_sec, 2),
                request_rate_per_sec=round(request_rate_per_sec, 2),
                burstiness_index=round(burst_index, 2),
                concurrency_requirement=concurrency_requirement,
                sample_count=1,
            )

        self.repo.save_workload_demand(p)
        logger.info(f"Updated demand profile for '{workload_name}' [{category.value}] (Burstiness={p.burstiness_index})")
        return p

    def list_demand_profiles(self, category: Optional[WorkloadCategory] = None) -> List[WorkloadDemandProfile]:
        profiles = self.repo.list_workload_demands()
        if category:
            profiles = [p for p in profiles if p.category == category]
        return profiles
