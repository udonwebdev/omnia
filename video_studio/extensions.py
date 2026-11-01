"""OMNIA Video Studio — Extension Architecture & Capability Boundaries (Module 0).

Defines the explicit permissions, contracts, and sandboxing requirements for plugins
and extensions targeting Video Studio (codecs, effects, transitions, AI providers, exporters).
Extensions are granted strictly scoped capabilities and cannot access arbitrary OMNIA Core internals.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Set, Optional

class ExtensionKind(str, Enum):
    EFFECT = "EFFECT"
    TRANSITION = "TRANSITION"
    CODEC = "CODEC"
    EXPORTER = "EXPORTER"
    IMPORTER = "IMPORTER"
    AI_PROVIDER = "AI_PROVIDER"
    AUDIO_PROCESSOR = "AUDIO_PROCESSOR"
    CONTROL_SURFACE = "CONTROL_SURFACE"
    GENERATOR = "GENERATOR"

class ExtensionPermission(str, Enum):
    GPU_COMPUTE = "gpu:compute"
    READ_MEDIA = "media:read"
    WRITE_CACHE = "cache:write"
    WRITE_EXPORT = "export:write"
    AI_INFERENCE = "ai:inference"
    AUDIO_DSP = "audio:dsp"
    NETWORK_RESTRICTED = "network:restricted"
    DEVICE_CONTROL = "device:control"

@dataclass
class ExtensionManifest:
    extension_id: str
    name: str
    version: str
    kind: ExtensionKind
    entry_point: str
    author: str
    granted_permissions: Set[ExtensionPermission] = field(default_factory=set)
    supported_platforms: List[str] = field(default_factory=lambda: ["windows", "linux", "macos"])
    min_video_studio_version: str = "0.1.0"
    sandbox_required: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate_permissions(self) -> bool:
        """Enforces that extensions do not request unauthorized core capabilities."""
        unauthorized = {
            "core:filesystem_root",
            "core:shell_unrestricted",
            "core:credentials",
            "core:database_write"
        }
        for perm in self.granted_permissions:
            if perm in unauthorized:
                return False
        return True

@dataclass
class ExtensionRuntimeStatus:
    extension_id: str
    is_active: bool = False
    is_sandboxed: bool = True
    memory_usage_mb: float = 0.0
    cpu_percent: float = 0.0
    crash_count: int = 0
    last_error: Optional[str] = None
