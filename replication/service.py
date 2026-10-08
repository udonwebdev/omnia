import time
import uuid
import logging
from typing import Dict, List, Optional, Tuple, Any, Set

from replication.models import (
    StateRecord,
    StateDelta,
    Snapshot,
    SyncCursor,
    ReplicationPeer,
    PeerSyncStatus,
    DeltaOperation,
    ConflictType,
    ConflictResolutionStrategy,
    ReplicationTelemetry
)
from replication.namespaces import namespace_registry
from replication.versioning import VersionComparator, ReplicationOwnershipEnforcer, ownership_enforcer
from replication.deltas import delta_manager, DeltaManager
from replication.snapshots import snapshot_manager
from replication.integrity import integrity_verifier
from replication.conflicts import conflict_resolver
from replication.reconciliation import reconciliation_engine
from replication.backpressure import backpressure_manager
from replication.persistence import replication_persistence
from coordination import coordination_service
from events.models import Event, EventEnvelope, EventPriority, EventDurability, EventSeverity
from events.fabric import event_fabric

logger = logging.getLogger("Omnia.Replication.Service")

class ReplicationService:
    """Authoritative distributed state synchronization, replication, and reconciliation service for Omnia."""

    def __init__(
        self,
        node_id: Optional[str] = None,
        persistence=None,
        coordination=None
    ):
        self.node_id = node_id or coordination_service.node_id
        self.persistence = persistence or replication_persistence
        self.coordination = coordination or coordination_service
        self.delta_manager = DeltaManager()
        self.ownership_enforcer = ReplicationOwnershipEnforcer(coord_service=self.coordination)

        self._peers: Dict[str, ReplicationPeer] = {}
        self._local_records: Dict[str, StateRecord] = {}  # (namespace_id, entity_id) -> record
        self._fencing_rejections = 0
        self._integrity_failures = 0
        self._divergence_count = 0
        self._running = False

    def start(self):
        """Starts replication service and loads persisted local state records."""
        if self._running:
            return

        logger.info(f"Starting ReplicationService for node '{self.node_id}'...")
        # Load local state from persistence store for each active namespace
        for ns in namespace_registry.list_namespaces():
            if ns.is_replicable():
                recs = self.persistence.list_records_for_namespace(ns.namespace_id)
                for r in recs:
                    key = f"{r.namespace_id}:{r.entity_id}"
                    self._local_records[key] = r

        self._running = True
        logger.info(f"ReplicationService initialized with {len(self._local_records)} local state records.")

    def stop(self):
        """Gracefully halts replication service."""
        self._running = False
        logger.info("ReplicationService stopped.")

    # --- Authoritative State Mutation (Local Node Publishing) ---

    def publish_state(
        self,
        namespace_id: str,
        entity_id: str,
        payload: Dict[str, Any],
        operation: DeltaOperation = DeltaOperation.UPDATE,
        entity_type: str = "ENTITY"
    ) -> Tuple[bool, Optional[StateRecord], Optional[StateDelta], str]:
        """Publishes an authoritative local state change, increments revision, and generates a broadcastable delta."""
        # 1. Namespace Security & Classification Check
        if not namespace_registry.can_replicate(namespace_id):
            msg = f"REPLICATION_DENIED: Namespace '{namespace_id}' is non-replicable, local-only, or sensitive."
            logger.warning(msg)
            return False, None, None, msg

        # 2. Module 22 Epoch Authority
        current_epoch = self.coordination.election.current_epoch
        key = f"{namespace_id}:{entity_id}"
        existing = self._local_records.get(key)
        base_rev = existing.revision if existing else 0
        target_rev = base_rev + 1

        # 3. Create StateDelta
        delta = self.delta_manager.create_delta(
            namespace_id=namespace_id,
            entity_id=entity_id,
            source_node=self.node_id,
            source_epoch=current_epoch,
            base_revision=base_rev,
            target_revision=target_rev,
            operation=operation,
            payload=payload
        )

        # 4. Apply locally
        ok, new_record, apply_msg = self.delta_manager.apply_delta_to_record(existing, delta)
        if not ok or not new_record:
            return False, None, None, apply_msg

        new_record.entity_type = entity_type
        self._local_records[key] = new_record
        self.persistence.save_state_record(new_record)
        self.persistence.save_delta(delta)

        # 5. Emit Event Fabric notification
        self._emit_event("replication.delta_applied", {
            "delta_id": delta.delta_id,
            "namespace_id": namespace_id,
            "entity_id": entity_id,
            "revision": target_rev
        })

        return True, new_record, delta, "STATE_PUBLISHED"

    # --- Incoming Remote Replication (Delta Application) ---

    def apply_remote_delta(self, delta: StateDelta) -> Tuple[bool, Optional[StateRecord], str]:
        """Validates and applies an incoming delta from a remote peer node."""
        # 1. Verify Namespace Replicability
        if not namespace_registry.can_replicate(delta.namespace_id):
            return False, None, f"REPLICATION_DENIED: Namespace '{delta.namespace_id}' cannot be replicated."

        # 2. Verify Delta Integrity Hash
        if delta.compute_hash() != delta.integrity_hash:
            self._integrity_failures += 1
            logger.error(f"CHECKSUM_MISMATCH: Delta '{delta.delta_id}' integrity hash is invalid.")
            self._emit_event("replication.delta_rejected", {
                "delta_id": delta.delta_id,
                "namespace_id": delta.namespace_id,
                "reason": "CHECKSUM_MISMATCH"
            })
            return False, None, "CHECKSUM_MISMATCH"

        key = f"{delta.namespace_id}:{delta.entity_id}"
        existing = self._local_records.get(key)

        # 3. Idempotency Check: If already applied, acknowledge immediately
        if delta.delta_id in self.delta_manager._applied_deltas:
            logger.info(f"Duplicate delta '{delta.delta_id}' received; acknowledged idempotently.")
            return True, existing, "IDEMPOTENT_DUPLICATE_APPLIED"

        # 4. Module 22 Epoch Fencing & Ownership Verification
        valid_auth, auth_msg = self.ownership_enforcer.validate_incoming_delta(delta, existing)
        if not valid_auth:
            # If revision is obsolete/duplicate in same epoch, acknowledge idempotently
            if "DUPLICATE_OR_STALE_REVISION" in auth_msg:
                return True, existing, "IDEMPOTENT_DUPLICATE_APPLIED"
            self._fencing_rejections += 1
            self._emit_event("replication.delta_rejected", {
                "delta_id": delta.delta_id,
                "namespace_id": delta.namespace_id,
                "reason": auth_msg
            })
            return False, existing, auth_msg

        # 5. Apply Idempotently & Handle Version Gaps
        ok, new_record, apply_msg = self.delta_manager.apply_delta_to_record(existing, delta)
        if not ok:
            return False, existing, apply_msg

        if new_record:
            self._local_records[key] = new_record
            self.persistence.save_state_record(new_record)
            self.persistence.save_delta(delta)

            # Update Sync Cursor for sender
            self._update_cursor(delta.source_node, delta.namespace_id, delta.target_revision)

            self._emit_event("replication.delta_applied", {
                "delta_id": delta.delta_id,
                "namespace_id": delta.namespace_id,
                "entity_id": delta.entity_id,
                "revision": delta.target_revision
            })

            # Check buffered deltas to fill subsequent revisions
            self._drain_buffered_deltas(delta.namespace_id, delta.entity_id)

        return True, new_record, apply_msg

    # --- Snapshot Generation & Installation ---

    def create_snapshot(self, namespace_id: str) -> Optional[Snapshot]:
        """Creates a frozen partition snapshot for a namespace."""
        recs = [r for r in self._local_records.values() if r.namespace_id == namespace_id]
        snap = snapshot_manager.create_snapshot(
            namespace_id=namespace_id,
            source_node=self.node_id,
            source_epoch=self.coordination.election.current_epoch,
            records=recs
        )
        self.persistence.save_snapshot(snap)
        self._emit_event("replication.snapshot_started", {
            "snapshot_id": snap.snapshot_id,
            "namespace_id": namespace_id,
            "source_node": self.node_id
        })
        return snap

    def install_snapshot(self, snapshot: Snapshot) -> Tuple[bool, str]:
        """Installs a received snapshot atomically after cryptographic verification."""
        # 1. Validate snapshot checksum and internal integrity
        valid, msg = snapshot_manager.validate_snapshot(snapshot)
        if not valid:
            self._integrity_failures += 1
            logger.error(f"Snapshot installation failed: {msg}")
            return False, msg

        # 2. Epoch check: Snapshot epoch must not be older than current cluster epoch
        if snapshot.source_epoch < self.coordination.election.current_epoch:
            self._fencing_rejections += 1
            return False, "FENCED_STALE_EPOCH: Snapshot epoch is older than cluster epoch."

        # 3. Atomically update local state records
        for r in snapshot.records:
            key = f"{r.namespace_id}:{r.entity_id}"
            self._local_records[key] = r
            self.persistence.save_state_record(r)

        # Clear buffered deltas for entities in this namespace
        for r in snapshot.records:
            self.delta_manager.clear_buffered_deltas(r.namespace_id, r.entity_id)

        self._update_cursor(snapshot.source_node, snapshot.namespace_id, snapshot.revision)

        self._emit_event("replication.snapshot_applied", {
            "snapshot_id": snapshot.snapshot_id,
            "namespace_id": snapshot.namespace_id,
            "record_count": snapshot.record_count
        })
        logger.info(f"Installed snapshot '{snapshot.snapshot_id}' for namespace '{snapshot.namespace_id}' (Rev: {snapshot.revision}).")
        return True, "SNAPSHOT_INSTALLED"

    # --- Anti-Entropy Reconciliation & Divergence ---

    def reconcile_with_peer(
        self,
        peer_node_id: str,
        namespace_id: str,
        remote_records: List[StateRecord]
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Compares local records with remote records, detects divergence, and applies safe convergence."""
        local_recs = [r for r in self._local_records.values() if r.namespace_id == namespace_id]
        diverged, divergent_entities, details = reconciliation_engine.detect_divergence(
            namespace_id=namespace_id,
            local_records=local_recs,
            remote_records=remote_records
        )

        if not diverged:
            self._update_cursor(peer_node_id, namespace_id, max([r.revision for r in local_recs], default=0), status=PeerSyncStatus.SYNCED)
            self._emit_event("replication.reconciliation_completed", {
                "namespace_id": namespace_id,
                "status": "CONVERGED"
            })
            return True, "CONVERGED", details

        self._divergence_count += 1
        self._emit_event("replication.state_diverged", {
            "namespace_id": namespace_id,
            "local_hash": details.get("local_hash", ""),
            "remote_hash": details.get("remote_hash", "")
        })

        local_map = {r.entity_id: r for r in local_recs}
        remote_map = {r.entity_id: r for r in remote_records}
        current_epoch = self.coordination.election.current_epoch

        reconciled_count = 0
        conflicts_count = 0

        for eid in divergent_entities:
            l_r = local_map.get(eid)
            r_r = remote_map.get(eid)
            action, chosen_record = reconciliation_engine.reconcile_divergent_entity(
                namespace_id=namespace_id,
                local_record=l_r,
                remote_record=r_r,
                current_epoch=current_epoch
            )

            if action == "ACCEPT_REMOTE" and chosen_record:
                key = f"{namespace_id}:{eid}"
                self._local_records[key] = chosen_record
                self.persistence.save_state_record(chosen_record)
                reconciled_count += 1
            elif action == "ESCALATE_CONFLICT":
                conflicts_count += 1

        details["reconciled_count"] = reconciled_count
        details["conflicts_count"] = conflicts_count

        return True, "RECONCILED", details

    # --- Telemetry & Helper Methods ---

    def register_peer(self, peer_id: str) -> ReplicationPeer:
        peer = ReplicationPeer(node_id=peer_id, sync_status=PeerSyncStatus.SYNCED)
        self._peers[peer_id] = peer
        return peer

    def get_peer(self, peer_id: str) -> Optional[ReplicationPeer]:
        return self._peers.get(peer_id)

    def get_state(self, namespace_id: str, entity_id: str) -> Optional[StateRecord]:
        key = f"{namespace_id}:{entity_id}"
        return self._local_records.get(key)

    def list_records(self, namespace_id: str) -> List[StateRecord]:
        return [r for r in self._local_records.values() if r.namespace_id == namespace_id]

    def get_telemetry(self) -> ReplicationTelemetry:
        lag_map = {}
        status_map = {}
        for pid, p in self._peers.items():
            lag_map[pid] = p.lag
            status_map[pid] = p.sync_status.value

        return ReplicationTelemetry(
            local_node_id=self.node_id,
            cluster_epoch=self.coordination.election.current_epoch,
            total_namespaces=len(namespace_registry.list_namespaces()),
            active_peers=len(self._peers),
            peer_lag_map=lag_map,
            sync_status_map=status_map,
            total_deltas_applied=len(self.delta_manager._applied_deltas),
            total_snapshots_installed=0,
            active_conflicts=len(conflict_resolver.list_conflicts(status="PENDING")),
            fencing_rejections=self._fencing_rejections,
            integrity_failures=self._integrity_failures,
            divergence_count=self._divergence_count
        )

    def _update_cursor(self, peer_node: str, namespace_id: str, rev: int, status: PeerSyncStatus = PeerSyncStatus.SYNCED):
        cursor = SyncCursor(
            peer_node=peer_node,
            namespace_id=namespace_id,
            last_applied_revision=rev,
            last_acknowledged_revision=rev,
            last_verified_revision=rev,
            last_sync_time=time.time(),
            status=status
        )
        self.persistence.save_sync_cursor(cursor)

    def _drain_buffered_deltas(self, namespace_id: str, entity_id: str):
        buffered = self.delta_manager.get_buffered_deltas(namespace_id, entity_id)
        if not buffered:
            return

        key = f"{namespace_id}:{entity_id}"
        current = self._local_records.get(key)
        for delta in list(buffered):
            if current and delta.base_revision == current.revision:
                ok, new_rec, _ = self.delta_manager.apply_delta_to_record(current, delta)
                if ok and new_rec:
                    self._local_records[key] = new_rec
                    self.persistence.save_state_record(new_rec)
                    current = new_rec
                    buffered.remove(delta)

    def _emit_event(self, event_type: str, payload: Dict[str, Any]):
        try:
            envelope = EventEnvelope(
                event_type=event_type,
                source=f"replication.{self.node_id}",
                priority=EventPriority.NORMAL,
                severity=EventSeverity.INFO,
                durability=EventDurability.DURABLE
            )
            event = Event(envelope=envelope, payload=payload)
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(event_fabric.publish(event))
            except RuntimeError:
                asyncio.run(event_fabric.publish(event))
        except Exception as e:
            logger.error(f"Failed to publish replication event '{event_type}': {e}")

replication_service = ReplicationService()
