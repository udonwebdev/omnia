import asyncio
import logging
from typing import Dict, List, Optional, Any
from replication.models import StateDelta, Snapshot

logger = logging.getLogger("Omnia.Replication.Backpressure")

class ReplicationBackpressureManager:
    """Monitors replication queue saturation, peer lag, and triggers snapshot fallback when needed."""

    def __init__(self, max_queue_depth: int = 1000, max_lag_revisions: int = 500):
        self.max_queue_depth = max_queue_depth
        self.max_lag_revisions = max_lag_revisions
        self._peer_queues: Dict[str, asyncio.Queue] = {}

    def get_or_create_queue(self, peer_node: str) -> asyncio.Queue:
        if peer_node not in self._peer_queues:
            self._peer_queues[peer_node] = asyncio.Queue(maxsize=self.max_queue_depth)
        return self._peer_queues[peer_node]

    def can_enqueue(self, peer_node: str) -> bool:
        q = self.get_or_create_queue(peer_node)
        return q.qsize() < self.max_queue_depth

    def should_fallback_to_snapshot(self, peer_lag: int) -> bool:
        """When peer falls too far behind (gap > max_lag_revisions), switch to snapshot transfer."""
        return peer_lag > self.max_lag_revisions

    def get_queue_depth(self, peer_node: str) -> int:
        q = self._peer_queues.get(peer_node)
        return q.qsize() if q else 0

backpressure_manager = ReplicationBackpressureManager()
