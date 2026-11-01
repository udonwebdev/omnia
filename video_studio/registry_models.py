"""OMNIA Video Studio — Module 1: Capability Models, Status Model & Requirements.

Defines the authoritative data models for:
- VideoStudioCapabilityCategory (16 standardized categories)
- VideoStudioCapabilityStatus (UNREGISTERED, REGISTERED, DISABLED, ENABLED, AVAILABLE, UNAVAILABLE, DEGRADED, INITIALIZING, READY, FAILED, EXPERIMENTAL)
- ImplementationState (PLANNED, STUB, EXPERIMENTAL, IMPLEMENTED, DEPRECATED)
- HardwareRequirements (CPU, GPU, VRAM, RAM, NPU, HW Encoders/Decoders)
- AIRequirements (abstract capability type, model size, offline requirement)
- CapabilityDependency (id, min_version, max_version, optional)
- CapabilityProviderDescriptor (provider_id, name, priority, is_local, is_available)
- VideoStudioCapabilityDescriptor (full structured metadata)
- CapabilityHealthReport (structured diagnostics, reasons, recovery suggestions)
"""

import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set

# ==============================================================================
# 1. Standardized Categories (16 Domains)
# ==============================================================================

class VideoStudioCategory(str, Enum):
    EDITING = "EDITING"
    TIMELINE = "TIMELINE"
    MEDIA = "MEDIA"
    MOTION = "MOTION"
    COMPOSITING = "COMPOSITING"
    TRACKING = "TRACKING"
    AUDIO = "AUDIO"
    COLOR = "COLOR"
    CAPTIONS = "CAPTIONS"
    GRAPHICS = "GRAPHICS"
    AI = "AI"
    RECORDING = "RECORDING"
    RENDERING = "RENDERING"
    EXPORT = "EXPORT"
    COLLABORATION = "COLLABORATION"
    EXTENSIONS = "EXTENSIONS"

# ==============================================================================
# 2. Capability Status & Implementation State Models
# ==============================================================================

class VideoStudioCapabilityStatus(str, Enum):
    UNREGISTERED = "UNREGISTERED"
    REGISTERED = "REGISTERED"
    DISABLED = "DISABLED"
    ENABLED = "ENABLED"
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    DEGRADED = "DEGRADED"
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    FAILED = "FAILED"
    EXPERIMENTAL = "EXPERIMENTAL"

class ImplementationState(str, Enum):
    PLANNED = "PLANNED"          # Catalog entry roadmap, not yet implemented
    STUB = "STUB"                # Interfaces and mock stubs defined
    EXPERIMENTAL = "EXPERIMENTAL"# Alpha / developmental implementation
    IMPLEMENTED = "IMPLEMENTED"  # Fully implemented and verified
    DEPRECATED = "DEPRECATED"

# ==============================================================================
# 3. Hardware & Platform Requirements
# ==============================================================================

class AccelerationAPI(str, Enum):
    CUDA = "CUDA"
    METAL = "METAL"
    DIRECTML = "DIRECTML"
    VULKAN = "VULKAN"
    OPENCL = "OPENCL"
    NVENC = "NVENC"
    NVDEC = "NVDEC"
    QSV = "QSV"
    AMF = "AMF"
    VIDEOTOOLBOX = "VIDEOTOOLBOX"

@dataclass
class HardwareRequirements:
    min_ram_mb: int = 1024
    recommended_ram_mb: int = 4096
    requires_gpu: bool = False
    min_vram_mb: int = 0
    requires_npu: bool = False
    required_acceleration: List[AccelerationAPI] = field(default_factory=list)
    requires_hw_encoder: bool = False
    requires_hw_decoder: bool = False
    min_disk_space_mb: int = 500

    def to_dict(self) -> Dict[str, Any]:
        return {
            "min_ram_mb": self.min_ram_mb,
            "recommended_ram_mb": self.recommended_ram_mb,
            "requires_gpu": self.requires_gpu,
            "min_vram_mb": self.min_vram_mb,
            "requires_npu": self.requires_npu,
            "required_acceleration": [a.value for a in self.required_acceleration],
            "requires_hw_encoder": self.requires_hw_encoder,
            "requires_hw_decoder": self.requires_hw_decoder,
            "min_disk_space_mb": self.min_disk_space_mb,
        }

@dataclass
class PlatformRequirements:
    supported_platforms: List[str] = field(default_factory=lambda: ["windows", "linux", "macos"])
    unsupported_platforms: List[str] = field(default_factory=list)
    supported_architectures: List[str] = field(default_factory=lambda: ["x64", "arm64", "AMD64"])

    def is_supported(self, current_platform: str, current_arch: str) -> bool:
        p = current_platform.lower()
        if p in [up.lower() for up in self.unsupported_platforms]:
            return False
        if self.supported_platforms and p not in [sp.lower() for sp in self.supported_platforms]:
            return False
        a = current_arch.lower()
        if self.supported_architectures and not any(sa.lower() in a or a in sa.lower() for sa in self.supported_architectures):
            return False
        return True

# ==============================================================================
# 4. AI & Provider Requirements
# ==============================================================================

@dataclass
class AIRequirements:
    abstract_capability: Optional[str] = None  # e.g., "speech_to_text", "optical_flow", "depth_estimation"
    supports_offline: bool = True
    requires_network: bool = False
    min_model_parameter_tier: str = "any"  # "nano", "small", "base", "large", "any"

@dataclass
class CapabilityProviderDescriptor:
    provider_id: str
    name: str
    priority: int = 100  # lower = higher priority
    is_local: bool = True
    is_available: bool = True
    health_status: str = "HEALTHY"
    version: str = "1.0.0"
    details: Dict[str, Any] = field(default_factory=dict)

# ==============================================================================
# 5. Dependency Declaration
# ==============================================================================

@dataclass
class CapabilityDependency:
    dependency_id: str
    is_optional: bool = False
    min_version: Optional[str] = None
    max_version: Optional[str] = None
    description: str = ""

# ==============================================================================
# 6. Structured Diagnostics & Health
# ==============================================================================

@dataclass
class CapabilityHealthReport:
    capability_id: str
    is_healthy: bool = True
    status: VideoStudioCapabilityStatus = VideoStudioCapabilityStatus.AVAILABLE
    reason: Optional[str] = None
    recovery_suggestion: Optional[str] = None
    failed_dependencies: List[str] = field(default_factory=list)
    hardware_shortfalls: List[str] = field(default_factory=list)
    last_check_ts: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "is_healthy": self.is_healthy,
            "status": self.status.value,
            "reason": self.reason,
            "recovery_suggestion": self.recovery_suggestion,
            "failed_dependencies": self.failed_dependencies,
            "hardware_shortfalls": self.hardware_shortfalls,
            "last_check_ts": self.last_check_ts,
        }

# ==============================================================================
# 7. Authoritative Capability Descriptor
# ==============================================================================

@dataclass
class VideoStudioCapabilityDescriptor:
    id: str  # Dot-notated identity e.g. "video.timeline.multitrack"
    name: str
    description: str
    category: VideoStudioCategory
    version: str = "1.0.0"
    implementation_state: ImplementationState = ImplementationState.PLANNED
    enabled: bool = True
    experimental: bool = False
    dependencies: List[CapabilityDependency] = field(default_factory=list)
    hardware_requirements: HardwareRequirements = field(default_factory=HardwareRequirements)
    platform_requirements: PlatformRequirements = field(default_factory=PlatformRequirements)
    ai_requirements: Optional[AIRequirements] = None
    permissions: List[str] = field(default_factory=list)
    providers: Dict[str, CapabilityProviderDescriptor] = field(default_factory=dict)
    active_provider_id: Optional[str] = None
    configuration_keys: List[str] = field(default_factory=list)
    documentation: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "version": self.version,
            "implementation_state": self.implementation_state.value,
            "enabled": self.enabled,
            "experimental": self.experimental,
            "dependencies": [
                {
                    "id": d.dependency_id,
                    "optional": d.is_optional,
                    "min_version": d.min_version,
                    "max_version": d.max_version
                } for d in self.dependencies
            ],
            "hardware": self.hardware_requirements.to_dict(),
            "platforms": self.platform_requirements.supported_platforms,
            "permissions": self.permissions,
            "providers": [p.provider_id for p in self.providers.values()],
            "active_provider": self.active_provider_id,
            "tags": self.tags,
            "documentation": self.documentation,
        }
