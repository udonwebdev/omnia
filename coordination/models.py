import time
import uuid
import hashlib
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Set

class NodeMembershipState(Enum):
    JOINING = "JOINING"
    ACTIVE = "ACTIVE"
    SUSPECTED = "SUSPECTED"
    UNREACHABLE = "UNREACHABLE"
    LEAVING = "LEAVING"
    LEFT = "LEFT"
    QUARANTINED = "QUARANTINED"
    REMOVED = "REMOVED"

class NodeTrustState(Enum):
    TRUSTED = "TRUSTED"
    UNKNOWN = "UNKNOWN"
    DEGRADED = "DEGRADED"
    SUSPICIOUS = "SUSPICIOUS"
    QUARANTINED = "QUARANTINED"
    REVOKED = "REVOKED"

class NodeHealthState(Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    SUSPECTED = "SUSPECTED"
    UNREACHABLE = "UNREACHABLE"
    DEAD = "DEAD"

class LeaderRole(Enum):
    FOLLOWER = "FOLLOWER"
    CANDIDATE = "CANDIDATE"
    LEADER = "LEADER"
    OBSERVER = "OBSERVER"
    QUARANTINED = "QUARANTINED"

class OwnershipState(Enum):
    REQUESTED = "REQUESTED"
    CLAIMED = "CLAIMED"
    ACTIVE = "ACTIVE"
    RELEASING = "RELEASING"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"
    FENCED = "FENCED"
    TRANSFERRED = "TRANSFERRED"
    REVOKED = "REVOKED"

class LockState(Enum):
    ACQUIRED = "ACQUIRED"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"
    FENCED = "FENCED"

class CoordinationHealth(Enum):
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    LEADER = "LEADER"
    FOLLOWER = "FOLLOWER"
    DEGRADED = "DEGRADED"
    NO_QUORUM = "NO_QUORUM"
    RECOVERING = "RECOVERING"
    QUARANTINED = "QUARANTINED"
    FAILED = "FAILED"

@dataclass
class NodeIdentity:
    """Cryptographically verifiable and stable identity of an Omnia node."""
    node_id: str = field(default_factory=lambda: f"node_{uuid.uuid4().hex[:8]}")
    node_name: str = "omnia-node"
    node_version: str = "1.0.0"
    public_key: Optional[str] = None
    identity_fingerprint: str = ""
    platform: str = "windows"
    architecture: str = "x86_64"
    endpoint_url: str = "http://127.0.0.1:8000"
    trust_state: NodeTrustState = NodeTrustState.TRUSTED
    membership_state: NodeMembershipState = NodeMembershipState.ACTIVE
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.identity_fingerprint:
            raw = f"{self.node_id}:{self.node_name}:{self.platform}:{self.created_at}"
            self.identity_fingerprint = hashlib.sha256(raw.encode("utf-8")).hexdigest()

@dataclass
class LeadershipLease:
    """Bounded leadership token enforcing authoritative command fencing."""
    lease_id: str = field(default_factory=lambda: f"ldl_{uuid.uuid4().hex[:8]}")
    leader_id: str = ""
    epoch: int = 1
    issued_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 10.0)
    renewal_sequence: int = 1
    fencing_token: str = ""

    def is_expired(self, now: Optional[float] = None) -> bool:
        current = now or time.time()
        return current >= self.expires_at

@dataclass
class OwnershipClaim:
    """Distributed ownership contract preventing concurrent execution of tasks or missions."""
    claim_id: str = field(default_factory=lambda: f"own_{uuid.uuid4().hex[:8]}")
    subject_type: str = "TASK"  # TASK, MISSION, RESOURCE, WORKER
    subject_id: str = ""
    owner_node_id: str = ""
    epoch: int = 1
    issued_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 30.0)
    fencing_token: str = ""
    state: OwnershipState = OwnershipState.ACTIVE
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self, now: Optional[float] = None) -> bool:
        current = now or time.time()
        return current >= self.expires_at

@dataclass
class DistributedLock:
    """Lease-bound distributed lock with fencing token."""
    lock_id: str = field(default_factory=lambda: f"dlock_{uuid.uuid4().hex[:8]}")
    resource_id: str = ""
    owner_node_id: str = ""
    epoch: int = 1
    fencing_token: str = ""
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 15.0)
    state: LockState = LockState.ACQUIRED

    def is_expired(self, now: Optional[float] = None) -> bool:
        current = now or time.time()
        return current >= self.expires_at

@dataclass
class CoordinationTelemetry:
    """Telemetry snapshot of the distributed coordination cluster."""
    local_node_id: str = ""
    health: CoordinationHealth = CoordinationHealth.INITIALIZING
    current_epoch: int = 1
    current_leader: Optional[str] = None
    role: LeaderRole = LeaderRole.FOLLOWER
    cluster_size: int = 1
    active_nodes: int = 1
    quorum_size: int = 1
    has_quorum: bool = True
    active_claims: int = 0
    active_locks: int = 0
    election_count: int = 0
    failover_count: int = 0
    fencing_violations: int = 0
    ownership_conflicts: int = 0

