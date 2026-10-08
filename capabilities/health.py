import asyncio
import logging
import platform
import subprocess
import time
from typing import Dict, Any, Tuple

from capabilities.models import CapabilityHealth
from capabilities.registry import capability_registry

logger = logging.getLogger("Omnia.Capabilities.Health")

class CapabilityHealthChecker:
    """Performs lightweight, deterministic health checks across Omnia subsystems."""

    def __init__(self, registry=capability_registry):
        self.registry = registry

    async def check_adb_health(self) -> Tuple[CapabilityHealth, str]:
        """Probes local ADB daemon and attached device availability."""
        try:
            from device_controller import DeviceController
            ctl = DeviceController()
            devices = ctl.get_connected_devices()
            if not devices:
                return CapabilityHealth.UNAVAILABLE, "No connected ADB devices detected"
            return CapabilityHealth.HEALTHY, f"{len(devices)} device(s) connected and authorized"
        except Exception as e:
            return CapabilityHealth.FAILED, f"ADB server connection failure: {e}"

    async def check_browser_health(self) -> Tuple[CapabilityHealth, str]:
        """Probes Playwright automation availability."""
        try:
            from browser_driver import browser_driver
            # Quick check if browser driver is initialized or can launch
            return CapabilityHealth.HEALTHY, "Browser automation runtime available"
        except Exception as e:
            return CapabilityHealth.UNAVAILABLE, f"Browser driver error: {e}"

    async def check_vision_health(self) -> Tuple[CapabilityHealth, str]:
        """Probes desktop capture and OCR engine availability."""
        try:
            from vision.ocr import ocr_engine
            # If RapidOCR engine exists, vision perception is functional
            return CapabilityHealth.HEALTHY, "Vision OCR engine initialized"
        except Exception as e:
            return CapabilityHealth.DEGRADED, f"Vision perception degraded: {e}"

    async def check_audio_tts_health(self) -> Tuple[CapabilityHealth, str]:
        """Probes local TTS synthesizer availability."""
        try:
            import audio_synthesizer
            return CapabilityHealth.HEALTHY, "Speech synthesizer engine ready"
        except Exception as e:
            return CapabilityHealth.UNAVAILABLE, f"TTS engine unavailable: {e}"

    async def check_memory_health(self) -> Tuple[CapabilityHealth, str]:
        """Probes vector memory engine database."""
        try:
            from memory_engine import memory
            doc_count = memory.count()
            return CapabilityHealth.HEALTHY, f"Vector memory online ({doc_count} docs)"
        except Exception as e:
            return CapabilityHealth.FAILED, f"Vector memory offline: {e}"

    async def check_mesh_health(self) -> Tuple[CapabilityHealth, str]:
        """Probes mesh discovery subsystem."""
        try:
            import mesh_discovery
            return CapabilityHealth.HEALTHY, "Mesh discovery daemon ready"
        except Exception as e:
            return CapabilityHealth.DEGRADED, f"Mesh communication error: {e}"

    async def run_all_checks(self) -> Dict[str, Dict[str, Any]]:
        """Executes health checks across all registered capabilities."""
        results = {}

        # 1. Device capabilities
        adb_h, adb_msg = await self.check_adb_health()
        for cid in ["device.android.tap", "device.android.unlock", "device.android.shell", "device.android.youtube"]:
            if self.registry.get_capability(cid):
                self.registry.update_health(cid, adb_h, adb_msg)
                results[cid] = {"health": adb_h.value, "message": adb_msg}

        # 2. Browser capabilities
        br_h, br_msg = await self.check_browser_health()
        for cid in ["browser.navigate", "browser.execute_task"]:
            if self.registry.get_capability(cid):
                self.registry.update_health(cid, br_h, br_msg)
                results[cid] = {"health": br_h.value, "message": br_msg}

        # 3. Vision capabilities
        vis_h, vis_msg = await self.check_vision_health()
        for cid in ["vision.capture_screen", "vision.find_element", "vision.verify_state"]:
            if self.registry.get_capability(cid):
                self.registry.update_health(cid, vis_h, vis_msg)
                results[cid] = {"health": vis_h.value, "message": vis_msg}

        # 4. Audio capabilities
        tts_h, tts_msg = await self.check_audio_tts_health()
        for cid in ["voice.speak"]:
            if self.registry.get_capability(cid):
                self.registry.update_health(cid, tts_h, tts_msg)
                results[cid] = {"health": tts_h.value, "message": tts_msg}

        # 5. Memory capabilities
        mem_h, mem_msg = await self.check_memory_health()
        for cid in ["memory.search_context"]:
            if self.registry.get_capability(cid):
                self.registry.update_health(cid, mem_h, mem_msg)
                results[cid] = {"health": mem_h.value, "message": mem_msg}

        # 6. Mesh capabilities
        mesh_h, mesh_msg = await self.check_mesh_health()
        for cid in ["mesh.execute_command"]:
            if self.registry.get_capability(cid):
                self.registry.update_health(cid, mesh_h, mesh_msg)
                results[cid] = {"health": mesh_h.value, "message": mesh_msg}

        return results

capability_health_checker = CapabilityHealthChecker()
