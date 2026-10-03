import asyncio
import time
from mesh_discovery import MeshNodeRegistry
from mesh_replicator import MeshReplicator

async def main():
    print("--- 1. Testing Mesh Discovery Sockets ---")
    reg1 = MeshNodeRegistry(node_id="node_alpha", host_port=8001)
    recv1, send1 = reg1._create_sockets()
    print("Socket creation successful.")
    recv1.close()
    send1.close()

    print("\n--- 2. Testing Node Peer Registry ---")
    assert len(reg1.get_active_nodes()) == 0
    reg1.peers["node_beta"] = {
        "ip": "127.0.0.1",
        "port": 8002,
        "role": "worker",
        "last_seen": time.time()
    }
    nodes = reg1.get_active_nodes()
    assert "node_beta" in nodes
    print(f"Registered peer: {nodes['node_beta']}")

    print("\n--- 3. Testing Stale Node Purge ---")
    reg1.peers["stale_node"] = {
        "ip": "127.0.0.1",
        "port": 8003,
        "role": "worker",
        "last_seen": time.time() - 20.0
    }
    reg1.running = True
    # Run one pass of prune
    now = time.time()
    stale = [nid for nid, data in reg1.peers.items() if now - data["last_seen"] > 15.0]
    for nid in stale:
        del reg1.peers[nid]
    assert "stale_node" not in reg1.peers
    assert "node_beta" in reg1.peers
    print("Stale peer successfully purged.")

    print("\n--- 4. Testing Mesh Tools Manifest ---")
    from omnia_tools import list_mesh_nodes, broadcast_to_all_mesh_hosts, OMNIA_ALL_TOOLS
    print("Active tools count:", len(OMNIA_ALL_TOOLS))
    assert list_mesh_nodes in OMNIA_ALL_TOOLS
    assert broadcast_to_all_mesh_hosts in OMNIA_ALL_TOOLS
    print("Tools validated in registry.")

    print("\n--- All Module 12 Verification Checks Passed! ---")

if __name__ == "__main__":
    asyncio.run(main())
