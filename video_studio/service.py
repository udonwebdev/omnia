"""OMNIA Video Studio — Subsystem Manager & Lifecycle Service (Module 0).

Manages discovery, registration, validation, initialization, and isolated execution
of the optional Video Studio subsystem.
Implements non-negotiable isolation rules:
- Enabled/Disabled runtime states.
- Degraded/Failed fallback behavior that never destabilizes OMNIA Core.
- Graceful event publishing and health reporting.
"""

import time
import logging
from typing import Dict, Any, Optional, Tuple, List

from video_studio.models import (
    VideoStudioState,
    VideoStudioFeatureContract,
    VideoStudioCapabilities,
    ComputeCapabilities,
    ComputeBackend,
    VideoStudioError,
)
from video_studio.catalog import VIDEO_STUDIO_CAPABILITY_CATALOG
from video_studio.registry import video_studio_capability_registry, VideoStudioCapabilityRegistry
from video_studio.catalog_loader import populate_roadmap_capabilities

logger = logging.getLogger("Omnia.VideoStudio.Service")

class VideoStudioService:
    """Central singleton controller for OMNIA Video Studio subsystem lifecycle."""

    def __init__(self):
        self._contract = VideoStudioFeatureContract()
        self._registry = video_studio_capability_registry
        populate_roadmap_capabilities(self._registry)
        self._active_jobs: Dict[str, Any] = {}
        self._is_initialized = False

    @property
    def registry(self) -> VideoStudioCapabilityRegistry:
        return self._registry

    @property
    def contract(self) -> VideoStudioFeatureContract:
        return self._contract

    @property
    def state(self) -> VideoStudioState:
        return self._contract.state

    @property
    def is_enabled(self) -> bool:
        return self._contract.is_enabled

    @property
    def is_available(self) -> bool:
        return self._contract.is_available

    def discover(self) -> VideoStudioFeatureContract:
        """Stage 1: Discover compute capabilities and environment suitability."""
        self._set_state(VideoStudioState.DISCOVERED, "Discovered Video Studio capability surface.")
        
        # Probe hardware compute availability safely
        backends = [ComputeBackend.CPU]
        try:
            # Probe CUDA or DirectML if available without importing heavy ML packages
            import platform
            system_name = platform.system().lower()
            if system_name == "windows":
                backends.append(ComputeBackend.DIRECTML)
            elif system_name == "darwin":
                backends.append(ComputeBackend.METAL)
        except Exception:
            pass

        self._contract.compute_capabilities = ComputeCapabilities(
            primary_backend=ComputeBackend.CPU,
            available_backends=backends
        )
        return self._contract

    def register(self, force_enabled: Optional[bool] = None) -> Tuple[bool, str]:
        """Stage 2: Register into OMNIA capability catalog and check configuration."""
        self.discover()
        self._set_state(VideoStudioState.REGISTERED, "Subsystem registered into OMNIA runtime.")

        # Check configuration from OMNIA config plane if available
        enabled = False
        try:
            from config import config_control_plane
            val = config_control_plane.resolve_effective_value("video_studio.enabled")
            if val is not None:
                enabled = bool(val)
        except Exception as e:
            logger.debug(f"Config service lookup skipped or deferred: {e}")

        if force_enabled is not None:
            enabled = force_enabled

        self._contract.is_enabled = enabled
        if not enabled:
            self._set_state(VideoStudioState.DISABLED, "Video Studio is currently disabled by configuration.")
            return True, "REGISTERED_DISABLED"

        return self.validate_and_initialize()

    def validate_and_initialize(self) -> Tuple[bool, str]:
        """Stages 3 & 4: Validate prerequisites and initialize subsystem."""
        if not self._contract.is_enabled:
            self._set_state(VideoStudioState.DISABLED, "Subsystem disabled.")
            return True, "DISABLED"

        self._set_state(VideoStudioState.VALIDATING, "Validating system resources and boundaries.")

        # Validate minimum resource limits
        reqs = self._contract.resource_requirements
        try:
            import psutil
            mem = psutil.virtual_memory()
            available_mb = mem.available / (1024 * 1024)
            if available_mb < reqs.min_ram_mb:
                msg = f"Insufficient system memory: {available_mb:.0f} MB available, {reqs.min_ram_mb} MB required."
                self._contract.error_message = msg
                self._set_state(VideoStudioState.DEGRADED, msg)
                return False, msg
        except ImportError:
            # psutil optional; non-fatal
            pass

        self._set_state(VideoStudioState.INITIALIZING, "Initializing module boundaries.")

        # Module 0: Capabilities are cataloged but not executed
        self._contract.active_capabilities = VideoStudioCapabilities()
        self._is_initialized = True
        self._set_state(VideoStudioState.READY, "Video Studio architectural foundation ready.")
        return True, "READY"

    def enable(self) -> Tuple[bool, str]:
        """Dynamically enables the subsystem."""
        self._contract.is_enabled = True
        return self.validate_and_initialize()

    def disable(self) -> Tuple[bool, str]:
        """Dynamically disables the subsystem cleanly."""
        self._contract.is_enabled = False
        self._set_state(VideoStudioState.DISABLED, "Video Studio manually disabled.")
        return True, "DISABLED"

    def mark_degraded(self, reason: str) -> None:
        """Isolates a sub-component failure without crashing OMNIA."""
        self._contract.error_message = reason
        self._set_state(VideoStudioState.DEGRADED, reason)

    def mark_failed(self, error: Exception) -> None:
        """Records an isolated failure without propagating fatal exceptions to OMNIA Core."""
        msg = f"{error.__class__.__name__}: {str(error)}"
        self._contract.error_message = msg
        self._set_state(VideoStudioState.FAILED, msg)
        logger.error(f"Video Studio isolated failure: {msg}")

    def get_status_summary(self) -> Dict[str, Any]:
        """Returns structured diagnostics dictionary for HUD or CLI display."""
        reg_total = len(self._registry.list())
        reg_avail = len(self._registry.list_available())
        reg_enabled = len(self._registry.list_enabled())
        return {
            "feature_id": self._contract.metadata.feature_id,
            "display_name": self._contract.metadata.display_name,
            "version": self._contract.metadata.version,
            "state": self._contract.state.value,
            "is_enabled": self._contract.is_enabled,
            "is_available": self._contract.is_available,
            "compute_backends": [b.value for b in self._contract.compute_capabilities.available_backends],
            "total_catalog_capabilities": reg_total,
            "available_capabilities": reg_avail,
            "enabled_capabilities": reg_enabled,
            "catalog_groups": list(VIDEO_STUDIO_CAPABILITY_CATALOG.keys()),
            "media_engine": {
                "active_projects": len(getattr(self, "_active_projects", [])),
                "storage_root": getattr(self, "_storage_root", "./data/video_studio"),
            },
            "error_message": self._contract.error_message,
        }

    def _set_state(self, new_state: VideoStudioState, reason: str = "") -> None:
        old_state = self._contract.state
        self._contract.state = new_state
        self._contract.last_state_change_ts = time.time()
        logger.info(f"VideoStudio state changed: {old_state.value} -> {new_state.value} ({reason})")

        # Emit typed event via EventFabric if available
        try:
            import asyncio
            from events import event_fabric, Event, EventEnvelope, EventPriority, EventSeverity, EventDurability
            loop = asyncio.get_event_loop() if asyncio.get_event_loop().is_running() else None
            if loop:
                loop.create_task(event_fabric.publish(Event(
                    envelope=EventEnvelope(
                        event_type="video_studio.status_changed",
                        source="video_studio.service",
                        priority=EventPriority.NORMAL,
                        severity=EventSeverity.NOTICE if new_state != VideoStudioState.FAILED else EventSeverity.ERROR,
                        durability=EventDurability.OPERATIONAL
                    ),
                    payload={
                        "old_state": old_state.value,
                        "new_state": new_state.value,
                        "reason": reason
                    }
                )))
        except Exception:
            pass

# Global Singleton instance
video_studio_service = VideoStudioService()
