"""Omnia Module 22: Distributed Coordination, Leader Election & Worker Consensus.

Provides authoritative distributed coordination, cluster membership, consensus-backed
leader election with monotonic epochs, bounded leadership leases, fencing tokens,
distributed task ownership claims, distributed locks, and crash recovery.
"""

from coordination.models import (
    NodeIdentity,
    NodeMembershipState,
    NodeTrustState,
    NodeHealthState,
    LeaderRole,
    OwnershipState,
    LockState,
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
from coordination.service import CoordinationService, coordination_service

__all__ = [
    "NodeIdentity",
    "NodeMembershipState",
    "NodeTrustState",
    "NodeHealthState",
    "LeaderRole",
    "OwnershipState",
    "LockState",
    "CoordinationHealth",
    "LeadershipLease",
    "OwnershipClaim",
    "DistributedLock",
    "CoordinationTelemetry",
    "ClusterMembershipManager",
    "LeaderElectionEngine",
    "OwnershipCoordinator",
    "CoordinationPersistenceManager",
    "CoordinationService",
    "coordination_service"
]
