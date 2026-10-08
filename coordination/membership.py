import time
import logging
from typing import Dict, List, Optional, Set, Any

from coordination.models import (
    NodeIdentity,
    NodeMembershipState,
    NodeTrustState,
    NodeHealthState
)

logger = logging.getLogger("Omnia.Coordination.Membership")

class ClusterMembershipManager:
    """Manages active cluster membership, heartbeats, and failure detection."""

    def __init__(self, local_node: NodeIdentity):
        self.local_node = local_node
        self._members: Dict[str, NodeIdentity] = {local_node.node_id: local_node}
        self.membership_version = 1
        self.heartbeat_timeout_sec = 15.0

    def register_node(self, node: NodeIdentity) -> bool:
        """Enrolls or updates a node in cluster membership."""
        if node.trust_state in {NodeTrustState.QUARANTINED, NodeTrustState.REVOKED}:
            logger.warning(f"Registration rejected: Node {node.node_id} is in {node.trust_state.value} state.")
            return False

        node.last_seen = time.time()
        node.membership_state = NodeMembershipState.ACTIVE
        self._members[node.node_id] = node
        self.membership_version += 1
        logger.info(f"Node registered in cluster: {node.node_id} ({node.node_name})")
        return True

    def remove_node(self, node_id: str, reason: str = "VOLUNTARY_LEAVE"):
        """Removes a node from cluster membership."""
        if node_id in self._members:
            node = self._members[node_id]
            node.membership_state = NodeMembershipState.LEFT
            del self._members[node_id]
            self.membership_version += 1
            logger.info(f"Node removed from cluster: {node_id}. Reason: {reason}")

    def quarantine_node(self, node_id: str, reason: str = "SECURITY_VIOLATION"):
        """Quarantines an offending or anomalous node."""
        if node_id in self._members:
            node = self._members[node_id]
            node.membership_state = NodeMembershipState.QUARANTINED
            node.trust_state = NodeTrustState.QUARANTINED
            self.membership_version += 1
            logger.warning(f"Node QUARANTINED: {node_id}. Reason: {reason}")

    def record_heartbeat(self, node_id: str):
        """Records a received heartbeat from a cluster peer."""
        if node_id in self._members:
            node = self._members[node_id]
            node.last_seen = time.time()
            if node.membership_state == NodeMembershipState.SUSPECTED:
                node.membership_state = NodeMembershipState.ACTIVE
                logger.info(f"Suspected node {node_id} recovered via heartbeat.")

    def scan_for_dead_nodes(self) -> List[str]:
        """Scans members and marks nodes with expired heartbeats as SUSPECTED or UNREACHABLE."""
        now = time.time()
        suspected = []
        for nid, node in list(self._members.items()):
            if nid == self.local_node.node_id:
                continue
            elapsed = now - node.last_seen
            if elapsed > self.heartbeat_timeout_sec * 2:
                node.membership_state = NodeMembershipState.UNREACHABLE
                suspected.append(nid)
            elif elapsed > self.heartbeat_timeout_sec:
                node.membership_state = NodeMembershipState.SUSPECTED
                suspected.append(nid)
        return suspected

    def get_active_members(self) -> List[NodeIdentity]:
        """Returns all currently active and healthy cluster nodes."""
        return [
            m for m in self._members.values()
            if m.membership_state == NodeMembershipState.ACTIVE and m.trust_state == NodeTrustState.TRUSTED
        ]

    def get_cluster_size(self) -> int:
        """Returns total non-quarantined/non-removed cluster size for quorum calculations."""
        return len([
            m for m in self._members.values()
            if m.membership_state not in {NodeMembershipState.LEFT, NodeMembershipState.REMOVED, NodeMembershipState.QUARANTINED}
            and m.trust_state != NodeTrustState.QUARANTINED
        ])

    def calculate_quorum_size(self) -> int:
        """Quorum calculation: floor(N / 2) + 1 over cluster membership."""
        n = self.get_cluster_size()
        return (n // 2) + 1

    def get_node(self, node_id: str) -> Optional[NodeIdentity]:
        """Returns node identity by ID if present."""
        return self._members.get(node_id)

    def enroll_node(
        self,
        node_id: str,
        node_name: str = "remote-node",
        endpoint_url: str = "http://127.0.0.1:8000",
        metadata: Optional[Dict[str, Any]] = None
    ) -> NodeIdentity:
        """Helper to instantiate and register a new node."""
        node = NodeIdentity(
            node_id=node_id,
            node_name=node_name,
            endpoint_url=endpoint_url,
            metadata=metadata or {}
        )
        self.register_node(node)
        return node

    def detect_failures(self) -> List[str]:
        """Alias for scan_for_dead_nodes."""
        return self.scan_for_dead_nodes()

    def has_quorum(self, votes: Optional[int] = None) -> bool:
        v = votes if votes is not None else len(self.get_active_members())
        return v >= self.calculate_quorum_size()
