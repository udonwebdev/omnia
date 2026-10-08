import time
import json
import hashlib
from enum import Enum
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

class ConfigType(str, Enum):
    STRING = "STRING"
    INTEGER = "INTEGER"
    FLOAT = "FLOAT"
    BOOLEAN = "BOOLEAN"
    ENUM = "ENUM"
    JSON = "JSON"
    SECRET_REF = "SECRET_REF"
    DURATION = "DURATION"
    PERCENTAGE = "PERCENTAGE"
    URL = "URL"
    LIST = "LIST"

class ConfigScope(str, Enum):
    GLOBAL = "GLOBAL"
    CLUSTER = "CLUSTER"
    NODE = "NODE"
    DEVICE = "DEVICE"

    @property
    def precedence(self) -> int:
        """Higher integer = higher precedence: DEVICE (4) > NODE (3) > CLUSTER (2) > GLOBAL (1)."""
        mapping = {
            ConfigScope.GLOBAL: 1,
            ConfigScope.CLUSTER: 2,
            ConfigScope.NODE: 3,
            ConfigScope.DEVICE: 4
        }
        return mapping[self]

class RuntimeMutability(str, Enum):
    HOT_RELOAD = "HOT_RELOAD"
    RESTART_REQUIRED = "RESTART_REQUIRED"
    DRAIN_REQUIRED = "DRAIN_REQUIRED"
    IMMUTABLE = "IMMUTABLE"

class RolloutStrategy(str, Enum):
    ALL_AT_ONCE = "ALL_AT_ONCE"
    ROLLING = "ROLLING"
    CANARY = "CANARY"
    MANUAL = "MANUAL"

class RolloutStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"

class ConfigVersionStatus(str, Enum):
    DRAFT = "DRAFT"
    STAGED = "STAGED"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    ROLLED_BACK = "ROLLED_BACK"

class DriftType(str, Enum):
    VALUE_MISMATCH = "VALUE_MISMATCH"
    VERSION_MISMATCH = "VERSION_MISMATCH"
    UNAUTHORIZED_OVERRIDE = "UNAUTHORIZED_OVERRIDE"
    MISSING_KEY = "MISSING_KEY"

@dataclass
class ConfigSchema:
    key: str
    domain: str
    data_type: ConfigType
    default_value: Any
    scope: ConfigScope = ConfigScope.CLUSTER
    mutability: RuntimeMutability = RuntimeMutability.HOT_RELOAD
    requires_restart: bool = False
    is_secret: bool = False
    allowed_values: List[Any] = field(default_factory=list)
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    unit: Optional[str] = None
    description: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    schema_spec: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "domain": self.domain,
            "data_type": self.data_type.value,
            "default_value": self.default_value,
            "scope": self.scope.value,
            "mutability": self.mutability.value,
            "requires_restart": self.requires_restart,
            "is_secret": self.is_secret,
            "allowed_values": self.allowed_values,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "unit": self.unit,
            "description": self.description,
            "dependencies": self.dependencies,
            "schema_spec": self.schema_spec,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

@dataclass
class ConfigValue:
    key: str
    scope: ConfigScope
    entity_id: str
    value: Any
    version: int
    is_secret_ref: bool = False
    updated_at: float = field(default_factory=time.time)

    def to_dict(self, mask_secrets: bool = True) -> Dict[str, Any]:
        display_val = self.value
        if mask_secrets and (self.is_secret_ref or (isinstance(self.value, str) and self.value.startswith("secret://"))):
            display_val = "[SECRET_MASKED]"
        return {
            "key": self.key,
            "scope": self.scope.value,
            "entity_id": self.entity_id,
            "value": display_val,
            "version": self.version,
            "is_secret_ref": self.is_secret_ref,
            "updated_at": self.updated_at
        }

@dataclass
class ConfigVersion:
    version: int
    parent_version: Optional[int]
    scope: ConfigScope
    target_entity: str
    content_hash: str
    values: Dict[str, Any]
    author: str
    justification: Optional[str] = None
    approval_token: Optional[str] = None
    status: ConfigVersionStatus = ConfigVersionStatus.STAGED
    created_at: float = field(default_factory=time.time)
    activated_at: Optional[float] = None

    @staticmethod
    def compute_hash(values: Dict[str, Any], scope: str, target_entity: str, parent_version: Optional[int]) -> str:
        canonical = json.dumps({
            "values": values,
            "scope": scope,
            "target_entity": target_entity,
            "parent_version": parent_version
        }, sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_dict(self, mask_secrets: bool = True) -> Dict[str, Any]:
        masked_values = {}
        for k, v in self.values.items():
            if mask_secrets and isinstance(v, str) and v.startswith("secret://"):
                masked_values[k] = "[SECRET_MASKED]"
            else:
                masked_values[k] = v

        return {
            "version": self.version,
            "parent_version": self.parent_version,
            "scope": self.scope.value,
            "target_entity": self.target_entity,
            "content_hash": self.content_hash,
            "values": masked_values,
            "author": self.author,
            "justification": self.justification,
            "approval_token": self.approval_token,
            "status": self.status.value,
            "created_at": self.created_at,
            "activated_at": self.activated_at
        }

@dataclass
class ConfigChange:
    key: str
    old_value: Any
    new_value: Any
    scope: ConfigScope
    entity_id: str
    change_type: str  # ADDED, MODIFIED, REMOVED
    requires_restart: bool = False
    is_secret: bool = False

    def to_dict(self, mask_secrets: bool = True) -> Dict[str, Any]:
        old_val = self.old_value
        new_val = self.new_value
        if mask_secrets and (self.is_secret or (isinstance(old_val, str) and old_val.startswith("secret://"))):
            old_val = "[MASKED]" if old_val is not None else None
        if mask_secrets and (self.is_secret or (isinstance(new_val, str) and new_val.startswith("secret://"))):
            new_val = "[MASKED]" if new_val is not None else None

        return {
            "key": self.key,
            "old_value": old_val,
            "new_value": new_val,
            "scope": self.scope.value,
            "entity_id": self.entity_id,
            "change_type": self.change_type,
            "requires_restart": self.requires_restart,
            "is_secret": self.is_secret
        }

@dataclass
class ConfigRollout:
    rollout_id: str
    version: int
    strategy: RolloutStrategy
    status: RolloutStatus
    batch_size: int = 1
    failure_threshold_pct: float = 0.0
    target_nodes: List[str] = field(default_factory=list)
    completed_nodes: List[str] = field(default_factory=list)
    failed_nodes: List[str] = field(default_factory=list)
    current_batch: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    failure_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rollout_id": self.rollout_id,
            "version": self.version,
            "strategy": self.strategy.value,
            "status": self.status.value,
            "batch_size": self.batch_size,
            "failure_threshold_pct": self.failure_threshold_pct,
            "target_nodes": self.target_nodes,
            "completed_nodes": self.completed_nodes,
            "failed_nodes": self.failed_nodes,
            "current_batch": self.current_batch,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "failure_reason": self.failure_reason
        }

@dataclass
class DriftRecord:
    drift_id: str
    node_id: str
    detected_at: float
    key: str
    expected_version: int
    expected_value: Any
    actual_value: Any
    drift_type: DriftType
    status: str = "DETECTED"
    resolved_at: Optional[float] = None
    resolution_notes: Optional[str] = None

    def to_dict(self, mask_secrets: bool = True) -> Dict[str, Any]:
        exp_val = self.expected_value
        act_val = self.actual_value
        if mask_secrets and isinstance(exp_val, str) and exp_val.startswith("secret://"):
            exp_val = "[MASKED]"
        if mask_secrets and isinstance(act_val, str) and act_val.startswith("secret://"):
            act_val = "[MASKED]"

        return {
            "drift_id": self.drift_id,
            "node_id": self.node_id,
            "detected_at": self.detected_at,
            "key": self.key,
            "expected_version": self.expected_version,
            "expected_value": exp_val,
            "actual_value": act_val,
            "drift_type": self.drift_type.value,
            "status": self.status,
            "resolved_at": self.resolved_at,
            "resolution_notes": self.resolution_notes
        }

@dataclass
class ConfigTelemetry:
    current_version: int
    total_keys: int
    active_rollout: Optional[Dict[str, Any]] = None
    pending_restart_nodes: List[str] = field(default_factory=list)
    active_drift_count: int = 0
    overrides_count: int = 0
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_version": self.current_version,
            "total_keys": self.total_keys,
            "active_rollout": self.active_rollout,
            "pending_restart_nodes": self.pending_restart_nodes,
            "active_drift_count": self.active_drift_count,
            "overrides_count": self.overrides_count,
            "last_updated": self.last_updated
        }
