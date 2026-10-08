import logging
from typing import Dict, Any, List, Optional
from intent.models import UserIntent

logger = logging.getLogger("Omnia.Intent.ContextResolver")

class PlanningContext:
    """Aggregates active device mesh, browser tabs, memory context, and policy constraints."""

    def __init__(self, intent: UserIntent, initial_context: Optional[Dict[str, Any]] = None):
        self.intent = intent
        self.raw_context = initial_context or {}
        self.devices: List[str] = []
        self.browser_urls: List[str] = []
        self.recent_memory_snippets: List[str] = []
        self.active_locks: List[str] = []
        self.resolved_entities: Dict[str, Any] = {}

    def resolve(self):
        """Pulls live environmental states from Omnia subsystems."""
        # 1. Resolve connected ADB devices
        try:
            from device_controller import device_mesh
            self.devices = device_mesh.list_devices()
        except Exception:
            self.devices = self.raw_context.get("devices", [])

        # 2. Resolve browser context
        try:
            from browser_driver import browser_driver
            if browser_driver.page:
                self.browser_urls.append(browser_driver.page.url)
        except Exception:
            pass

        # 3. Pull relevant semantic memory preferences if available
        try:
            from memory_engine import memory
            hits = memory.search_context(self.intent.raw_text, limit=2)
            for h in hits:
                self.recent_memory_snippets.append(h.get("content", ""))
        except Exception:
            pass

        # 4. Resolve explicit target device
        if "android" in self.intent.target_devices:
            if self.devices:
                self.resolved_entities["target_device_serial"] = self.devices[0]
            else:
                self.resolved_entities["target_device_serial"] = "emulator-5554"  # Default fallback if unattached

        # 5. Resolve target URL
        if self.intent.target_websites:
            target_url = self.intent.target_websites[0]
            if not target_url.startswith("http"):
                target_url = f"https://{target_url}"
            self.resolved_entities["target_url"] = target_url

        return self

def resolve_context(intent: UserIntent, initial_context: Optional[Dict[str, Any]] = None) -> PlanningContext:
    ctx = PlanningContext(intent, initial_context)
    return ctx.resolve()
