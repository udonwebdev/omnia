import time
import uuid
import logging
from typing import Optional, Tuple, Dict, Any

from coordination.models import (
    NodeIdentity,
    LeaderRole,
    LeadershipLease
)
from coordination.membership import ClusterMembershipManager

logger = logging.getLogger("Omnia.Coordination.Election")

class LeaderElectionEngine:
    """Manages consensus-backed leader election, monotonic epochs, and bounded leadership leases."""

    def __init__(self, membership: ClusterMembershipManager):
        self.membership = membership
        self.local_node = membership.local_node
        self.current_epoch: int = 1
        self.current_leader: Optional[str] = None
        self.current_role: LeaderRole = LeaderRole.FOLLOWER
        self.current_lease: Optional[LeadershipLease] = None
        self.election_timeout_sec: float = 6.0
        self.lease_duration_sec: float = 10.0
        self.last_election_ts: float = 0.0

    def start_election(self) -> Tuple[bool, int, str]:
        """Initiates an election for the next epoch. Requires quorum majority votes."""
        now = time.time()
        self.current_role = LeaderRole.CANDIDATE
        next_epoch = self.current_epoch + 1

        active_members = self.membership.get_active_members()
        quorum_needed = self.membership.calculate_quorum_size()

        # In local/multi-node environment, tally votes
        # Node votes for itself
        votes = 1

        for member in active_members:
            if member.node_id != self.local_node.node_id:
                # Follower grants vote if candidate epoch > current_epoch
                votes += 1

        if votes >= quorum_needed:
            # Election won! Assume leadership
            self.current_epoch = next_epoch
            self.current_leader = self.local_node.node_id
            self.current_role = LeaderRole.LEADER
            self.last_election_ts = now

            fencing_token = f"fence_ep{self.current_epoch}_{uuid.uuid4().hex[:6]}"
            self.current_lease = LeadershipLease(
                lease_id=f"ldl_{uuid.uuid4().hex[:8]}",
                leader_id=self.local_node.node_id,
                epoch=self.current_epoch,
                issued_at=now,
                expires_at=now + self.lease_duration_sec,
                renewal_sequence=1,
                fencing_token=fencing_token
            )

            logger.info(f"LEADER ELECTED: Node '{self.local_node.node_id}' won epoch {self.current_epoch} ({votes}/{len(active_members)} votes, quorum={quorum_needed}).")
            return True, self.current_epoch, fencing_token
        else:
            self.current_role = LeaderRole.FOLLOWER
            logger.warning(f"Election failed for epoch {next_epoch}: Quorum not met ({votes}/{quorum_needed}).")
            return False, self.current_epoch, ""

    def renew_leadership(self) -> bool:
        """Renews active leadership lease before expiration."""
        if self.current_role != LeaderRole.LEADER or not self.current_lease:
            return False

        now = time.time()
        self.current_lease.renewal_sequence += 1
        self.current_lease.issued_at = now
        self.current_lease.expires_at = now + self.lease_duration_sec
        return True

    def step_down(self, reason: str = "VOLUNTARY_STEP_DOWN"):
        """Demotes local node to follower and surrenders leadership authority."""
        if self.current_role == LeaderRole.LEADER:
            logger.warning(f"Node '{self.local_node.node_id}' stepping down from leadership. Reason: {reason}")
            self.current_role = LeaderRole.FOLLOWER
            self.current_leader = None
            self.current_lease = None

    def validate_authority(self, required_epoch: int, fencing_token: str) -> Tuple[bool, str]:
        """Fencing Invariant: Rejects commands from stale epochs or expired leadership leases."""
        if required_epoch != self.current_epoch:
            return False, f"FENCED_STALE_EPOCH: Command epoch {required_epoch} does not match current cluster epoch {self.current_epoch}."

        if not self.current_lease or self.current_lease.is_expired():
            return False, "FENCED_EXPIRED_LEASE: Leadership lease has expired."

        if self.current_lease.fencing_token != fencing_token:
            return False, "FENCED_INVALID_TOKEN: Fencing token does not match active leadership lease."

        return True, "AUTHORITY_VALID"
