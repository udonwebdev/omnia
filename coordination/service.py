import time
import uuid
import logging
from typing import Dict, Any, Optional, List, Tuple

from coordination.models import (
    NodeIdentity,
    NodeTrustState,
    NodeMembershipState,
    LeaderRole,
    CoordinationHealth,
    LeadershipLease,
    OwnershipClaim,
    DistributedLock,
    CoordinationTelemetry
)
from coordination.membership import ClusterMembershipManager
from coordination.election import LeaderElectionEngine
from coordination.ownership import OwnershipCoordinator
from coordination.persistence import CoordinationPersistenceManager
from events.models import Event, EventEnvelope, EventPriority, EventDurability, EventSeverity
from events.fabric import event_fabric

logger = logging.getLogger("Omnia.Coordination.Service")

class CoordinationService:
    """Authoritative distributed coordination subsystem for Omnia.
    
    Coordinates cluster membership, consensus-backed leader election with monotonic epochs,
    bounded leadership leases, fencing tokens, exclusive work ownership, distributed locks,
    and crash recovery.
    """

    def __init__(
        self,
        node_id: Optional[str] = None,
        node_name: str = "omnia-node",
        persistence: Optional[CoordinationPersistenceManager] = None
    ):
        self.node_id = node_id or f"node_{uuid.uuid4().hex[:8]}"
        self.persistence = persistence or CoordinationPersistenceManager()
        
        # Initialize sub-components
        self.local_node = NodeIdentity(
            node_id=self.node_id,
            node_name=node_name
        )
        self.membership = ClusterMembershipManager(
            local_node=self.local_node
        )
        self.election = LeaderElectionEngine(membership=self.membership)
        self.ownership = OwnershipCoordinator(local_node_id=self.node_id)
        
        self.health = CoordinationHealth.INITIALIZING
        self._running = False
        self._fencing_violations = 0
        self._ownership_conflicts = 0

    def start(self):
        """Starts coordination subsystem and reconciles state from persistent store."""
        if self._running:
            return

        logger.info(f"Starting CoordinationService for node '{self.node_id}'...")
        
        # 1. Startup reconciliation in persistence store
        recon_stats = self.persistence.reconcile_on_startup()
        
        # 2. Persist local node identity
        self.persistence.save_node(self.membership.local_node)
        
        # 3. Check for existing active leadership lease
        active_lease = self.persistence.get_active_leadership_lease()
        if active_lease and not active_lease.is_expired():
            self.election.current_epoch = active_lease.epoch
            self.election.current_leader = active_lease.leader_id
            if active_lease.leader_id == self.node_id:
                self.election.current_role = LeaderRole.LEADER
                self.election.current_lease = active_lease
                self.health = CoordinationHealth.LEADER
            else:
                self.election.current_role = LeaderRole.FOLLOWER
                self.health = CoordinationHealth.FOLLOWER
        else:
            self.health = CoordinationHealth.READY

        self._running = True

        # 4. Emit coordination.started event
        self._emit_event("coordination.started", {
            "node_id": self.node_id,
            "epoch": self.election.current_epoch
        })
        logger.info(f"CoordinationService started. Node '{self.node_id}', Role '{self.election.current_role.value}', Epoch {self.election.current_epoch}.")

    def stop(self):
        """Gracefully halts coordination service and voluntarily steps down if leader."""
        if not self._running:
            return

        logger.info(f"Stopping CoordinationService for node '{self.node_id}'...")
        if self.election.current_role == LeaderRole.LEADER:
            self.step_down(reason="SERVICE_STOP")

        self.membership.local_node.membership_state = NodeMembershipState.LEFT
        self.persistence.save_node(self.membership.local_node)
        self._running = False
        self.health = CoordinationHealth.READY

    def enroll_remote_node(
        self,
        node_id: str,
        node_name: str = "remote-node",
        endpoint_url: str = "http://127.0.0.1:8000",
        metadata: Optional[Dict[str, Any]] = None
    ) -> NodeIdentity:
        """Enrolls a remote node into cluster membership and persists it."""
        node = self.membership.enroll_node(
            node_id=node_id,
            node_name=node_name,
            endpoint_url=endpoint_url,
            metadata=metadata
        )
        self.persistence.save_node(node)
        self._emit_event("node.joined", {
            "node_id": node.node_id,
            "epoch": self.election.current_epoch
        })
        return node

    def trigger_heartbeat(self, node_id: Optional[str] = None):
        """Records a heartbeat from a node."""
        target_id = node_id or self.node_id
        self.membership.record_heartbeat(target_id)
        node = self.membership.get_node(target_id)
        if node:
            self.persistence.save_node(node)

    def elect_leader(self) -> Tuple[bool, int, str]:
        """Runs a leader election. If won, persists the lease and publishes events."""
        self._emit_event("leader.election_started", {
            "candidate_id": self.node_id,
            "epoch": self.election.current_epoch + 1
        })

        success, epoch, fencing_token = self.election.start_election()
        if success:
            self.health = CoordinationHealth.LEADER
            if self.election.current_lease:
                self.persistence.save_leadership_lease(self.election.current_lease)
                self._emit_event("leader.elected", {
                    "leader_id": self.node_id,
                    "epoch": epoch,
                    "lease_expires_at": self.election.current_lease.expires_at
                })
                self._emit_event("coordination.epoch_changed", {
                    "old_epoch": epoch - 1,
                    "new_epoch": epoch,
                    "leader_id": self.node_id
                })
        else:
            self.health = CoordinationHealth.NO_QUORUM
            self._emit_event("leader.lost", {
                "leader_id": self.node_id,
                "epoch": epoch,
                "reason": "ELECTION_QUORUM_NOT_MET"
            })

        return success, epoch, fencing_token

    def renew_leadership(self) -> bool:
        """Renews leadership lease."""
        if self.election.renew_leadership():
            if self.election.current_lease:
                self.persistence.save_leadership_lease(self.election.current_lease)
            return True
        return False

    def step_down(self, reason: str = "VOLUNTARY_STEP_DOWN"):
        """Steps down from leadership."""
        old_epoch = self.election.current_epoch
        self.election.step_down(reason)
        self.health = CoordinationHealth.FOLLOWER
        self._emit_event("leader.lost", {
            "leader_id": self.node_id,
            "epoch": old_epoch,
            "reason": reason
        })

    def validate_authority(self, required_epoch: int, fencing_token: str) -> Tuple[bool, str]:
        """Validates that a command is authorized by the current leader and lease."""
        valid, reason = self.election.validate_authority(required_epoch, fencing_token)
        if not valid:
            self._fencing_violations += 1
            logger.warning(f"Fencing violation on node '{self.node_id}': {reason}")
        return valid, reason

    def claim_task_ownership(
        self,
        task_id: str,
        owner_node_id: Optional[str] = None,
        lease_sec: float = 30.0
    ) -> Tuple[bool, Optional[OwnershipClaim], str]:
        """Claims exclusive distributed ownership for executing a task."""
        claimant = owner_node_id or self.node_id
        success, claim, message = self.ownership.claim_ownership(
            subject_type="TASK",
            subject_id=task_id,
            owner_node_id=claimant,
            epoch=self.election.current_epoch,
            lease_sec=lease_sec
        )

        if success and claim:
            self.persistence.save_ownership_claim(claim)
            self._emit_event("ownership.claimed", {
                "claim_id": claim.claim_id,
                "subject_type": "TASK",
                "subject_id": task_id,
                "owner_node_id": claimant,
                "epoch": self.election.current_epoch,
                "fencing_token": claim.fencing_token
            })
        else:
            self._ownership_conflicts += 1
            current_owner = self.ownership.get_owner("TASK", task_id) or "UNKNOWN"
            self._emit_event("ownership.rejected", {
                "subject_id": task_id,
                "attempted_by": claimant,
                "current_owner": current_owner
            })

        return success, claim, message

    def release_task_ownership(self, task_id: str, owner_node_id: Optional[str] = None) -> bool:
        """Releases task ownership claim upon completion or failure."""
        claimant = owner_node_id or self.node_id
        claim = self.ownership.get_claim("TASK", task_id)
        claim_id = claim.claim_id if claim else ""

        if self.ownership.release_ownership("TASK", task_id, claimant):
            if claim:
                self.persistence.save_ownership_claim(claim)
            self._emit_event("ownership.released", {
                "claim_id": claim_id,
                "subject_id": task_id
            })
            return True
        return False

    def get_task_owner(self, task_id: str) -> Optional[str]:
        """Returns node ID of the task owner, or None if unclaimed."""
        return self.ownership.get_owner("TASK", task_id)

    def acquire_lock(
        self,
        resource_id: str,
        owner_node_id: Optional[str] = None,
        lease_sec: float = 15.0
    ) -> Tuple[bool, Optional[DistributedLock], str]:
        """Acquires a lease-bound distributed lock."""
        claimant = owner_node_id or self.node_id
        success, lock, message = self.ownership.acquire_distributed_lock(
            resource_id=resource_id,
            owner_node_id=claimant,
            epoch=self.election.current_epoch,
            lease_sec=lease_sec
        )
        if success and lock:
            self.persistence.save_lock(lock)
        return success, lock, message

    def release_lock(self, resource_id: str, owner_node_id: Optional[str] = None) -> bool:
        """Releases distributed lock."""
        claimant = owner_node_id or self.node_id
        lock = self.ownership.get_lock(resource_id)
        if self.ownership.release_distributed_lock(resource_id, claimant):
            if lock:
                self.persistence.save_lock(lock)
            return True
        return False

    def reap_expired_claims_and_locks(self) -> Dict[str, int]:
        """Reaps expired claims and locks locally and persists state changes."""
        reaped_claims = self.ownership.reap_expired_claims()
        reaped_locks = self.ownership.reap_expired_locks()

        for c in reaped_claims:
            self.persistence.save_ownership_claim(c)
            self._emit_event("ownership.expired", {
                "claim_id": c.claim_id,
                "subject_id": c.subject_id
            })

        for l in reaped_locks:
            self.persistence.save_lock(l)

        return {
            "reaped_claims_count": len(reaped_claims),
            "reaped_locks_count": len(reaped_locks)
        }

    def detect_node_failures(self) -> List[str]:
        """Detects suspected inactive cluster nodes and triggers node.suspected events."""
        suspected = self.membership.detect_failures()
        for nid in suspected:
            node = self.membership.get_node(nid)
            last_seen_sec = (time.time() - node.last_seen) if node else 0.0
            self._emit_event("node.suspected", {
                "node_id": nid,
                "last_seen_sec": round(last_seen_sec, 2)
            })
        return suspected

    def get_telemetry(self) -> CoordinationTelemetry:
        """Returns coordination telemetry."""
        active_claims = len(self.ownership.get_active_claims())
        active_locks = len(self.ownership.get_active_locks())
        active_members = len(self.membership.get_active_members())
        quorum_size = self.membership.calculate_quorum_size()
        has_quorum = self.membership.has_quorum()

        return CoordinationTelemetry(
            local_node_id=self.node_id,
            health=self.health,
            current_epoch=self.election.current_epoch,
            current_leader=self.election.current_leader,
            role=self.election.current_role,
            cluster_size=active_members,
            active_nodes=active_members,
            quorum_size=quorum_size,
            has_quorum=has_quorum,
            active_claims=active_claims,
            active_locks=active_locks,
            election_count=self.election.current_epoch - 1,
            failover_count=0,
            fencing_violations=self._fencing_violations,
            ownership_conflicts=self._ownership_conflicts
        )

    def _emit_event(self, event_type: str, payload: Dict[str, Any]):
        """Helper to construct and broadcast events across the Event Fabric."""
        try:
            prio = EventPriority.CRITICAL if "split_brain" in event_type or "failed" in event_type else EventPriority.HIGH
            envelope = EventEnvelope(
                event_type=event_type,
                source=f"coordination.{self.node_id}",
                priority=prio,
                severity=EventSeverity.CRITICAL if prio == EventPriority.CRITICAL else EventSeverity.INFO,
                durability=EventDurability.DURABLE
            )
            event = Event(
                envelope=envelope,
                payload=payload
            )
            # Use background task if running inside event loop or call sync
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(event_fabric.publish(event))
            except RuntimeError:
                asyncio.run(event_fabric.publish(event))
        except Exception as e:
            logger.error(f"Failed to publish event '{event_type}': {e}")

# Global singleton
coordination_service = CoordinationService()
