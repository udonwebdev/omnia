import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
from typing import List, Dict, Any
from ppadb.client import Client as AdbClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Omnia.DeviceController")

class DeviceController:
    """High-concurrency ADB bridge designed for low-latency parallel device control."""
    def __init__(self, host: str = "127.0.0.1", port: int = 5037, max_workers: int = 16):
        self.host = host
        self.port = port
        self.max_workers = max_workers
        self.client = AdbClient(host=self.host, port=self.port)
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self.refresh_devices()

    def refresh_devices(self) -> List[Any]:
        """Scans and updates the active device list."""
        try:
            self.devices = self.client.devices()
            logger.info(f"Discovered {len(self.devices)} connected device(s).")
            return self.devices
        except Exception as e:
            logger.error(f"Failed to communicate with ADB server: {e}")
            self.devices = []
            return []

    def list_serials(self) -> List[str]:
        """Returns hardware serial identifiers for all active devices."""
        return [dev.get_serial_no() for dev in self.devices]

    def _sync_shell(self, device: Any, command: str) -> str:
        """Executes a blocking shell command on a single target device."""
        try:
            return device.shell(command)
        except Exception as ex:
            return f"Error ({device.get_serial_no()}): {ex}"

    async def broadcast_shell(self, command: str) -> Dict[str, str]:
        """Dispatches an ADB shell command concurrently across all devices (10x concurrency)."""
        if not self.devices:
            self.refresh_devices()
            if not self.devices:
                return {"status": "error", "message": "No devices available."}

        loop = asyncio.get_running_loop()
        tasks = [
            loop.run_in_executor(self.executor, self._sync_shell, dev, command)
            for dev in self.devices
        ]
        
        results = await asyncio.gather(*tasks)
        return {dev.get_serial_no(): res for dev, res in zip(self.devices, results)}

    async def wake_and_unlock_mesh(self) -> Dict[str, str]:
        """Concurrently turns screen on and swipes to dismiss lock screen on all nodes."""
        logger.info("Broadcasting wake and swipe-unlock to all mesh nodes...")
        # 26: KEYEVENT_POWER, 82: KEYEVENT_MENU (unlock fallback)
        unlock_script = "input keyevent 26 && input swipe 500 1600 500 400 150 || input keyevent 82"
        return await self.broadcast_shell(unlock_script)

    async def launch_youtube(self, video_id: str) -> Dict[str, str]:
        """Instantly opens a target YouTube video URL across all devices."""
        logger.info(f"Launching YouTube video ID {video_id} on all nodes...")
        intent = f"am start -a android.intent.action.VIEW -d 'vnd.youtube:{video_id}'"
        return await self.broadcast_shell(intent)

    async def trigger_browser_url(self, url: str) -> Dict[str, str]:
        """Opens a targeted web URL in the default browser across all devices."""
        logger.info(f"Navigating all devices to: {url}")
        intent = f"am start -a android.intent.action.VIEW -d '{url}'"
        return await self.broadcast_shell(intent)

if __name__ == "__main__":
    # Standalone diagnostic test
    async def test_run():
        controller = DeviceController()
        print(f"Active Devices: {controller.list_serials()}")
        if controller.devices:
            print("Testing wake-and-unlock on connected mesh...")
            res = await controller.wake_and_unlock_mesh()
            print("Results:", res)

    asyncio.run(test_run())
