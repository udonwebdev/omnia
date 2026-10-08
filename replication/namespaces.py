import logging
from typing import Dict, Optional, List
from replication.models import StateNamespace, StateClassification, ConsistencyPolicy

logger = logging.getLogger("Omnia.Replication.Namespaces")

# Authoritative Operational Namespaces
DEFAULT_NAMESPACES: Dict[str, StateNamespace] = {
    # 1. Distributed Tasks (Authoritative + Replicated across nodes)
    "tasks": StateNamespace(
        namespace_id="tasks",
        name="Distributed Task State",
        owner_type="NODE",
        replication_policy=StateClassification.REPLICATED,
        consistency_policy=ConsistencyPolicy.OWNER_AUTHORITATIVE,
        sensitivity=StateClassification.AUTHORITATIVE
    ),
    # 2. Missions (Supervised Missions)
    "missions": StateNamespace(
        namespace_id="missions",
        name="Supervised Mission Progress",
        owner_type="LEADER",
        replication_policy=StateClassification.REPLICATED,
        consistency_policy=ConsistencyPolicy.OWNER_AUTHORITATIVE,
        sensitivity=StateClassification.AUTHORITATIVE
    ),
    # 3. Scheduled Work (Admitted Resources & Allocations)
    "schedules": StateNamespace(
        namespace_id="schedules",
        name="Resource Scheduler Allocations",
        owner_type="LEADER",
        replication_policy=StateClassification.REPLICATED,
        consistency_policy=ConsistencyPolicy.STRONG,
        sensitivity=StateClassification.AUTHORITATIVE
    ),
    # 4. Capabilities (Cluster Capability Health & Providers)
    "capabilities": StateNamespace(
        namespace_id="capabilities",
        name="Cluster Capabilities Registry",
        owner_type="MESH",
        replication_policy=StateClassification.REPLICATED,
        consistency_policy=ConsistencyPolicy.EVENTUAL,
        sensitivity=StateClassification.REPLICATED
    ),
    # 5. Credentials / Secrets (STRICTLY LOCAL_ONLY + SENSITIVE)
    "secrets": StateNamespace(
        namespace_id="secrets",
        name="Local Node Secrets and Credentials",
        owner_type="LOCAL",
        replication_policy=StateClassification.LOCAL_ONLY,
        consistency_policy=ConsistencyPolicy.LOCAL_ONLY,
        sensitivity=StateClassification.SENSITIVE,
        enabled=False
    ),
    # 6. Audio/Microphone Buffers (STRICTLY LOCAL_ONLY)
    "audio_buffers": StateNamespace(
        namespace_id="audio_buffers",
        name="Raw Audio Buffers",
        owner_type="LOCAL",
        replication_policy=StateClassification.LOCAL_ONLY,
        consistency_policy=ConsistencyPolicy.LOCAL_ONLY,
        sensitivity=StateClassification.LOCAL_ONLY,
        enabled=False
    ),
    # 7. Transient Frames & OCR (STRICTLY EPHEMERAL)
    "ephemeral_frames": StateNamespace(
        namespace_id="ephemeral_frames",
        name="Temporary Vision Frames",
        owner_type="LOCAL",
        replication_policy=StateClassification.EPHEMERAL,
        consistency_policy=ConsistencyPolicy.LOCAL_ONLY,
        sensitivity=StateClassification.EPHEMERAL,
        enabled=False
    ),
    # 8. Cluster Runtime Configuration (Authoritative + Replicated across nodes)
    "config": StateNamespace(
        namespace_id="config",
        name="Cluster Runtime Configuration & Policy",
        owner_type="LEADER",
        replication_policy=StateClassification.REPLICATED,
        consistency_policy=ConsistencyPolicy.STRONG,
        sensitivity=StateClassification.AUTHORITATIVE
    )
}

class NamespaceRegistry:
    """Manages namespace definitions and enforces sensitivity/replication policy boundaries."""

    def __init__(self):
        self._namespaces: Dict[str, StateNamespace] = dict(DEFAULT_NAMESPACES)

    def register_namespace(self, ns: StateNamespace) -> bool:
        if ns.namespace_id in self._namespaces:
            logger.warning(f"Namespace '{ns.namespace_id}' already registered. Updating.")
        self._namespaces[ns.namespace_id] = ns
        return True

    def get_namespace(self, namespace_id: str) -> Optional[StateNamespace]:
        return self._namespaces.get(namespace_id)

    def list_namespaces(self) -> List[StateNamespace]:
        return list(self._namespaces.values())

    def can_replicate(self, namespace_id: str) -> bool:
        """Enforces that unknown namespaces default to non-replicated, and sensitive state is never replicated."""
        ns = self._namespaces.get(namespace_id)
        if not ns:
            # Default behavior for unknown state: DO NOT REPLICATE
            logger.warning(f"Replication blocked: Unknown namespace '{namespace_id}'. Defaulting to non-replicated.")
            return False
        return ns.is_replicable()

namespace_registry = NamespaceRegistry()
