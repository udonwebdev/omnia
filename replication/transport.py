import logging
from typing import Dict, Any, List, Optional
from mesh_replicator import mesh_replicator
from mesh_discovery import mesh_registry
from replication.models import StateDelta, Snapshot

logger = logging.getLogger("Omnia.Replication.Transport")

class ReplicationTransport:
    """Dispatches replication deltas and snapshot requests using Module 12 mesh networking."""

    def __init__(self, replicator=None, registry=None):
        self.replicator = replicator or mesh_replicator
        self.registry = registry or mesh_registry

    async def broadcast_delta(self, delta: StateDelta) -> List[str]:
        """Broadcasts a state delta across all active mesh nodes."""
        payload = {
            "type": "REPLICATION_DELTA",
            "delta_id": delta.delta_id,
            "namespace_id": delta.namespace_id,
            "entity_id": delta.entity_id,
            "source_node": delta.source_node,
            "source_epoch": delta.source_epoch,
            "base_revision": delta.base_revision,
            "target_revision": delta.target_revision,
            "operation": delta.operation.value,
            "payload": delta.payload,
            "causal_metadata": delta.causal_metadata,
            "integrity_hash": delta.integrity_hash,
            "created_at": delta.created_at
        }
        try:
            results = await self.replicator.broadcast_mesh_command("/api/replication/delta", payload)
            return [peer_id for peer_id, resp in results.items() if "error" not in resp]
        except Exception as e:
            logger.error(f"Failed to broadcast delta '{delta.delta_id}': {e}")
            return []

    async def send_snapshot(self, peer_ip: str, peer_port: int, snapshot: Snapshot) -> bool:
        """Sends a frozen snapshot to a reconnecting or lagging peer."""
        payload = {
            "type": "REPLICATION_SNAPSHOT",
            "snapshot_id": snapshot.snapshot_id,
            "namespace_id": snapshot.namespace_id,
            "source_node": snapshot.source_node,
            "source_epoch": snapshot.source_epoch,
            "revision": snapshot.revision,
            "record_count": snapshot.record_count,
            "content_hash": snapshot.content_hash,
            "records": [
                {
                    "state_id": r.state_id,
                    "namespace_id": r.namespace_id,
                    "entity_type": r.entity_type,
                    "entity_id": r.entity_id,
                    "owner_node": r.owner_node,
                    "owner_epoch": r.owner_epoch,
                    "revision": r.revision,
                    "payload": r.payload,
                    "schema_version": r.schema_version,
                    "integrity_hash": r.integrity_hash
                }
                for r in snapshot.records
            ]
        }
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(f"http://{peer_ip}:{peer_port}/api/replication/snapshot", json=payload)
                return resp.status_code == 200
        except Exception as e:
            logger.error(f"Failed to send snapshot to {peer_ip}:{peer_port}: {e}")
            return False

replication_transport = ReplicationTransport()
