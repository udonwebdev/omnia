import socket
import json
import time
import asyncio
import logging
import platform
from typing import Dict, Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Omnia.MeshDiscovery")

MULTICAST_GROUP = "239.255.42.99"
MULTICAST_PORT = 53530
HEARTBEAT_INTERVAL = 5.0
NODE_TIMEOUT = 15.0

class MeshNodeRegistry:
    """Manages dynamic LAN node discovery via UDP multicast."""

    def __init__(self, node_id: str, host_port: int = 8000):
        self.node_id = node_id
        self.host_port = host_port
        self.peers: Dict[str, Dict[str, Any]] = {}
        self.running = False

    def _create_sockets(self):
        # Listener socket
        recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # On Windows, binding to "" or "0.0.0.0" on MULTICAST_PORT
        if platform.system() == "Windows":
            recv_sock.bind(("", MULTICAST_PORT))
        else:
            try:
                recv_sock.bind((MULTICAST_GROUP, MULTICAST_PORT))
            except Exception:
                recv_sock.bind(("", MULTICAST_PORT))
        
        mreq = socket.inet_aton(MULTICAST_GROUP) + socket.inet_aton("0.0.0.0")
        recv_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        recv_sock.setblocking(False)

        # Broadcast socket
        send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        send_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        # Enable loopback so local test probes can communicate
        try:
            send_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        except Exception:
            pass
        send_sock.setblocking(False)

        return recv_sock, send_sock

    async def broadcast_loop(self, send_sock: socket.socket):
        while self.running:
            payload = json.dumps({
                "node_id": self.node_id,
                "port": self.host_port,
                "timestamp": time.time(),
                "role": "orchestrator"
            }).encode("utf-8")
            try:
                send_sock.sendto(payload, (MULTICAST_GROUP, MULTICAST_PORT))
            except Exception as e:
                logger.warning(f"Heartbeat send failed: {e}")
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def listen_loop(self, recv_sock: socket.socket):
        loop = asyncio.get_running_loop()
        while self.running:
            try:
                # Windows asyncio loop.sock_recvfrom works on Python 3.11+
                data, addr = await loop.sock_recvfrom(recv_sock, 1024)
                message = json.loads(data.decode("utf-8"))
                peer_id = message.get("node_id")

                if peer_id and peer_id != self.node_id:
                    self.peers[peer_id] = {
                        "ip": addr[0],
                        "port": message.get("port", 8000),
                        "role": message.get("role", "node"),
                        "last_seen": time.time()
                    }
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(0.1)

    async def prune_stale_peers(self):
        while self.running:
            now = time.time()
            stale = [nid for nid, data in self.peers.items() if now - data["last_seen"] > NODE_TIMEOUT]
            for nid in stale:
                logger.info(f"Pruning disconnected mesh node: {nid}")
                del self.peers[nid]
            await asyncio.sleep(5.0)

    async def start(self):
        self.running = True
        recv_sock, send_sock = self._create_sockets()
        logger.info(f"Mesh Discovery active on multicast {MULTICAST_GROUP}:{MULTICAST_PORT}")
        try:
            await asyncio.gather(
                self.broadcast_loop(send_sock),
                self.listen_loop(recv_sock),
                self.prune_stale_peers()
            )
        finally:
            recv_sock.close()
            send_sock.close()

    def stop(self):
        self.running = False

    def get_active_nodes(self) -> Dict[str, Dict[str, Any]]:
        return self.peers

mesh_registry = MeshNodeRegistry(node_id=f"omnia_host_{int(time.time())}")
