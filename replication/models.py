import time
import uuid
import hashlib
import json
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Set

class StateClassification(Enum):
    """Explicit sensitivity and replication domain classification."""
    AUTHORITATIVE = "AUTHORITATIVE"
    REPLICATED = "REPLICATED"
    DERIVED = "DERIVED"
    EPHEMERAL = "EPHEMERAL"
    LOCAL_ONLY = "LOCAL_ONLY"
    SENSITIVE = "SENSITIVE"

class ConsistencyPolicy(Enum):
    """Consistency contract for a given state namespace."""
    STRONG = "STRONG"
    CAUSAL = "CAUSAL"
    EVENTUAL = "EVENTUAL"
    LOCAL_ONLY = "LOCAL_ONLY"
    OWNER_AUTHORITATIVE = "OWNER_AUTHORITATIVE"

class DeltaOperation(Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    PATCH = "PATCH"
    DELETE = "DELETE"
    REPLACE = "REPLACE"

class ConflictType(Enum):
    CONCURRENT_MODIFICATION = "CONCURRENT_MODIFICATION"
    STALE_EPOCH = "STALE_EPOCH"
    OWNERSHIP_MISMATCH = "OWNERSHIP_MISMATCH"
    VERSION_GAP = "VERSION_GAP"
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"

class ConflictResolutionStrategy(Enum):
    REJECT_STALE = "REJECT_STALE"
    OWNER_WINS = "OWNER_WINS"
    EPOCH_WINS = "EPOCH_WINS"
    MERGE = "MERGE"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    RECONSTRUCT_FROM_AUTHORITY = "RECONSTRUCT_FROM_AUTHORITY"

class PeerSyncStatus(Enum):
    INITIALIZING = "INITIALIZING"
    SYNCED = "SYNCED"
    SYNCING = "SYNCING"
    CATCHING_UP = "CATCHING_UP"
    LAGGING = "LAGGING"
    DIVERGED = "DIVERGED"
    CONFLICT = "CONFLICT"
    BLOCKED = "BLOCKED"
    OFFLINE = "OFFLINE"
    UNAUTHORIZED = "UNAUTHORIZED"

@dataclass
class StateNamespace:
    """Represents a synchronized category of state with explicit replication boundaries."""
    namespace_id: str
    name: str
    owner_type: str = "NODE"  # NODE, LEADER, MESH, LOCAL
    replication_policy: StateClassification = StateClassification.REPLICATED
    consistency_policy: ConsistencyPolicy = ConsistencyPolicy.OWNER_AUTHORITATIVE
    sensitivity: StateClassification = StateClassification.REPLICATED
    schema_version: str = "1.0.0"
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_replicable(self) -> bool:
        """Sensitive or local-only namespaces must never be replicated."""
        if self.sensitivity in {StateClassification.SENSITIVE, StateClassification.LOCAL_ONLY}:
            return False
        if self.replication_policy in {StateClassification.LOCAL_ONLY, StateClassification.EPHEMERAL}:
            return False
        return self.enabled

@dataclass
class StateRecord:
    """Represents a logical piece of replicated state."""
    state_id: str = field(default_factory=lambda: f"st_{uuid.uuid4().hex[:8]}")
    namespace_id: str = ""
    entity_type: str = ""
    entity_id: str = ""
    owner_node: str = ""
    owner_epoch: int = 1
    revision: int = 1
    payload: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1.0.0"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    integrity_hash: str = ""

    def __post_init__(self):
        if not self.integrity_hash:
            self.integrity_hash = self.compute_hash()

    def compute_hash(self) -> str:
        """Deterministic SHA-256 hash across entity key, revision, epoch, and payload."""
        sorted_payload = json.dumps(self.payload, sort_keys=True, separators=(',', ':'))
        raw = f"{self.namespace_id}:{self.entity_type}:{self.entity_id}:{self.owner_node}:{self.owner_epoch}:{self.revision}:{sorted_payload}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

@dataclass
class StateVersion:
    """Represents a specific state revision with causal lineage."""
    namespace_id: str
    entity_id: str
    revision: int
    epoch: int
    source_node: str
    timestamp: float = field(default_factory=time.time)
    causal_metadata: Dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""

@dataclass
class StateDelta:
    """Represents an incremental state transition."""
    delta_id: str = field(default_factory=lambda: f"dlta_{uuid.uuid4().hex[:8]}")
    namespace_id: str = ""
    entity_id: str = ""
    source_node: str = ""
    source_epoch: int = 1
    base_revision: int = 0
    target_revision: int = 1
    operation: DeltaOperation = DeltaOperation.UPDATE
    payload: Dict[str, Any] = field(default_factory=dict)
    causal_metadata: Dict[str, Any] = field(default_factory=dict)
    integrity_hash: str = ""
    created_at: float = field(default_factory=time.time)

    def __post_init__(self):
        if not self.integrity_hash:
            self.integrity_hash = self.compute_hash()

    def compute_hash(self) -> str:
        sorted_payload = json.dumps(self.payload, sort_keys=True, separators=(',', ':'))
        raw = f"{self.delta_id}:{self.namespace_id}:{self.entity_id}:{self.source_node}:{self.source_epoch}:{self.base_revision}:{self.target_revision}:{self.operation.value}:{sorted_payload}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

@dataclass
class Snapshot:
    """Represents a frozen state partition image with boundary hash."""
    snapshot_id: str = field(default_factory=lambda: f"snap_{uuid.uuid4().hex[:8]}")
    namespace_id: str = ""
    source_node: str = ""
    source_epoch: int = 1
    revision: int = 1
    created_at: float = field(default_factory=time.time)
    schema_version: str = "1.0.0"
    record_count: int = 0
    content_hash: str = ""
    records: List[StateRecord] = field(default_factory=list)

    def compute_hash(self) -> str:
        hashes = [r.integrity_hash for r in sorted(self.records, key=lambda x: (x.entity_type, x.entity_id))]
        raw = f"{self.snapshot_id}:{self.namespace_id}:{self.source_node}:{self.source_epoch}:{self.revision}:{','.join(hashes)}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

@dataclass
class SyncCursor:
    """Tracks continuous replication progress for a peer node."""
    peer_node: str
    namespace_id: str
    last_applied_revision: int = 0
    last_acknowledged_revision: int = 0
    last_verified_revision: int = 0
    last_sync_time: float = field(default_factory=time.time)
    status: PeerSyncStatus = PeerSyncStatus.INITIALIZING

@dataclass
class ReplicationPeer:
    """Tracks synchronization relationship and lag with a cluster peer."""
    node_id: str
    connection_state: str = "CONNECTED"  # CONNECTED, DISCONNECTED, DEGRADED
    authorized_namespaces: Set[str] = field(default_factory=set)
    last_seen: float = field(default_factory=time.time)
    lag: int = 0
    sync_status: PeerSyncStatus = PeerSyncStatus.INITIALIZING
    failure_count: int = 0

@dataclass
class Conflict:
    """Represents explicit replication conflicts preserving diagnostic evidence."""
    conflict_id: str = field(default_factory=lambda: f"cfl_{uuid.uuid4().hex[:8]}")
    namespace_id: str = ""
    entity_id: str = ""
    local_version: Dict[str, Any] = field(default_factory=dict)
    remote_version: Dict[str, Any] = field(default_factory=dict)
    conflict_type: ConflictType = ConflictType.CONCURRENT_MODIFICATION
    resolution_strategy: ConflictResolutionStrategy = ConflictResolutionStrategy.EPOCH_WINS
    resolution_status: str = "PENDING"  # PENDING, RESOLVED, ESCALATED
    created_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    evidence: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ReplicationTelemetry:
    """Real-time observability snapshot for supervisor and HUD."""
    local_node_id: str = ""
    cluster_epoch: int = 1
    total_namespaces: int = 0
    active_peers: int = 0
    peer_lag_map: Dict[str, int] = field(default_factory=dict)
    sync_status_map: Dict[str, str] = field(default_factory=dict)
    total_deltas_applied: int = 0
    total_snapshots_installed: int = 0
    active_conflicts: int = 0
    fencing_rejections: int = 0
    integrity_failures: int = 0
    divergence_count: int = 0
