import httpx
import logging
from typing import Dict, Any, List
from mesh_discovery import mesh_registry

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Omnia.MeshReplicator")

class MeshReplicator:
    """Propagates state updates and global tasks across discovered peer hosts."""

    async def broadcast_state(self, state: str, details: str = "") -> List[str]:
        peers = mesh_registry.get_active_nodes()
        if not peers:
            return []

        delivered = []
        async with httpx.AsyncClient(timeout=2.0) as client:
            for peer_id, info in peers.items():
                url = f"http://{info['ip']}:{info['port']}/api/state"
                try:
                    resp = await client.post(url, json={"state": state, "message": details})
                    if resp.status_code == 200:
                        delivered.append(peer_id)
                except Exception as e:
                    logger.warning(f"Replication failed for peer {peer_id} at {url}: {e}")
        return delivered

    async def broadcast_mesh_command(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        peers = mesh_registry.get_active_nodes()
        results = {}
        async with httpx.AsyncClient(timeout=5.0) as client:
            for peer_id, info in peers.items():
                target_url = f"http://{info['ip']}:{info['port']}{endpoint}"
                try:
                    resp = await client.post(target_url, json=payload)
                    results[peer_id] = resp.json()
                except Exception as ex:
                    results[peer_id] = {"error": str(ex)}
        return results

mesh_replicator = MeshReplicator()
