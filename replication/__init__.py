"""Omnia Module 23: Distributed State Synchronization, Replication & Reconciliation Engine.

Provides authoritative distributed state propagation, delta streams, out-of-order buffering,
gap detection, frozen snapshots, anti-entropy reconciliation, and deterministic conflict resolution.
"""

from replication.models import (
    StateClassification,
    ConsistencyPolicy,
    DeltaOperation,
    ConflictType,
    ConflictResolutionStrategy,
    PeerSyncStatus,
    StateNamespace,
    StateRecord,
    StateVersion,
    StateDelta,
    Snapshot,
    SyncCursor,
    ReplicationPeer,
    Conflict,
    ReplicationTelemetry
)

from replication.namespaces import namespace_registry, NamespaceRegistry
from replication.versioning import VersionComparator, ReplicationOwnershipEnforcer, ownership_enforcer
from replication.deltas import delta_manager, DeltaManager
from replication.snapshots import snapshot_manager, SnapshotManager
from replication.integrity import integrity_verifier, StateIntegrityVerifier
from replication.conflicts import conflict_resolver, ConflictResolver
from replication.reconciliation import reconciliation_engine, StateReconciliationEngine
from replication.backpressure import backpressure_manager, ReplicationBackpressureManager
from replication.persistence import replication_persistence, ReplicationPersistenceManager
from replication.service import replication_service, ReplicationService

__all__ = [
    "StateClassification",
    "ConsistencyPolicy",
    "DeltaOperation",
    "ConflictType",
    "ConflictResolutionStrategy",
    "PeerSyncStatus",
    "StateNamespace",
    "StateRecord",
    "StateVersion",
    "StateDelta",
    "Snapshot",
    "SyncCursor",
    "ReplicationPeer",
    "Conflict",
    "ReplicationTelemetry",
    "namespace_registry",
    "NamespaceRegistry",
    "VersionComparator",
    "ReplicationOwnershipEnforcer",
    "ownership_enforcer",
    "delta_manager",
    "DeltaManager",
    "snapshot_manager",
    "SnapshotManager",
    "integrity_verifier",
    "StateIntegrityVerifier",
    "conflict_resolver",
    "ConflictResolver",
    "reconciliation_engine",
    "StateReconciliationEngine",
    "backpressure_manager",
    "ReplicationBackpressureManager",
    "replication_persistence",
    "ReplicationPersistenceManager",
    "replication_service",
    "ReplicationService"
]
