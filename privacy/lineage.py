"""
privacy/lineage.py
Data Lineage & Provenance Tracker:
Maintains directed acyclic and cyclic flows of data movement across
sources, transformations, stores, downstream replicas, AI models, and vendors.
Crucial for verified cascading deletion orchestration and data provenance audits.
"""

import uuid
import time
import logging
from collections import deque
from typing import List, Dict, Any, Set, Optional

from privacy.models import LineageRecord
from privacy.persistence import PrivacyRepository

logger = logging.getLogger("omnia.privacy.lineage")


class DataLineageTracker:
    def __init__(self, repo: PrivacyRepository):
        self.repo = repo

    def record_lineage(
        self,
        source_asset_id: str,
        dest_asset_id: str,
        operation_type: str,
        purpose: str,
        transformation_type: str = "RAW_COPY",
        actor: str = "omnia_pipeline"
    ) -> LineageRecord:
        """Records a directed data flow between source and destination assets."""
        lid = f"lin_{uuid.uuid4().hex[:12]}"
        now = time.time()

        rec = LineageRecord(
            lineage_id=lid,
            source_asset_id=source_asset_id,
            dest_asset_id=dest_asset_id,
            operation_type=operation_type,
            purpose=purpose,
            transformation_type=transformation_type,
            actor=actor,
            timestamp=now
        )
        saved = self.repo.save_lineage(rec)
        self.repo.log_audit("LINEAGE_RECORDED", actor, {
            "lineage_id": lid,
            "source": source_asset_id,
            "dest": dest_asset_id,
            "op": operation_type
        })
        logger.info(f"Lineage recorded: {source_asset_id} -> {dest_asset_id} [{operation_type}]")
        return saved

    def trace_downstream(self, asset_id: str) -> List[str]:
        """Performs breadth-first traversal to discover all downstream assets that received data.

        This guarantees that when data is marked for deletion, all secondary stores,
        caches, models, and replicas are identified.
        """
        all_records = self.repo.list_lineage()
        adjacency: Dict[str, List[str]] = {}
        for r in all_records:
            adjacency.setdefault(r.source_asset_id, []).append(r.dest_asset_id)

        visited: Set[str] = set()
        queue = deque([asset_id])
        downstream: List[str] = []

        while queue:
            curr = queue.popleft()
            for neighbor in adjacency.get(curr, []):
                if neighbor not in visited and neighbor != asset_id:
                    visited.add(neighbor)
                    downstream.append(neighbor)
                    queue.append(neighbor)

        return downstream

    def trace_upstream(self, asset_id: str) -> List[str]:
        """Discovers all upstream origin assets for an asset."""
        all_records = self.repo.list_lineage()
        reverse_adjacency: Dict[str, List[str]] = {}
        for r in all_records:
            reverse_adjacency.setdefault(r.dest_asset_id, []).append(r.source_asset_id)

        visited: Set[str] = set()
        queue = deque([asset_id])
        upstream: List[str] = []

        while queue:
            curr = queue.popleft()
            for neighbor in reverse_adjacency.get(curr, []):
                if neighbor not in visited and neighbor != asset_id:
                    visited.add(neighbor)
                    upstream.append(neighbor)
                    queue.append(neighbor)

        return upstream

    def get_lineage_graph(self, asset_id: str) -> Dict[str, Any]:
        """Constructs graph nodes and edges involving the target asset."""
        downstream = self.trace_downstream(asset_id)
        upstream = self.trace_upstream(asset_id)
        all_nodes = set([asset_id] + downstream + upstream)

        all_records = self.repo.list_lineage()
        edges = []
        for r in all_records:
            if r.source_asset_id in all_nodes and r.dest_asset_id in all_nodes:
                edges.append({
                    "source": r.source_asset_id,
                    "target": r.dest_asset_id,
                    "operation": r.operation_type,
                    "purpose": r.purpose,
                    "transformation": r.transformation_type,
                    "timestamp": r.timestamp
                })

        return {
            "root_asset": asset_id,
            "nodes": list(all_nodes),
            "edges": edges,
            "downstream_count": len(downstream),
            "upstream_count": len(upstream)
        }
