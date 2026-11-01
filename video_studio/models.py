"""OMNIA Video Studio — Core Architectural Domain Models & Error Definitions.

Provides typed feature contracts, lifecycles, compute capabilities, error isolation hierarchies,
and metadata definitions conforming to OMNIA conventions.
"""

import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set

# ==============================================================================
# 1. Subsystem Lifecycle & Operational Status
# ==============================================================================

class VideoStudioState(str, Enum):
    """Lifecycle and operational states for the Video Studio subsystem."""
    DISCOVERED = "DISCOVERED"
    REGISTERED = "REGISTERED"
    VALIDATING = "VALIDATING"
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    RUNNING = "RUNNING"
    AVAILABLE = "AVAILABLE"
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    EXPERIMENTAL = "EXPERIMENTAL"
    FAILED = "FAILED"

# ==============================================================================
# 2. Compute & Hardware Capability Abstraction
# ==============================================================================

class ComputeBackend(str, Enum):
    """Supported compute backends for video processing, VFX, and AI inference."""
    CPU = "CPU"
    CUDA = "CUDA"
    METAL = "METAL"
    DIRECTML = "DIRECTML"
    NPU = "NPU"
    HARDWARE_VIDEO_ENCODER = "HARDWARE_VIDEO_ENCODER"
    HARDWARE_VIDEO_DECODER = "HARDWARE_VIDEO_DECODER"

@dataclass
class ComputeCapabilities:
    """Hardware and compute capability footprint discovered on the host node."""
    primary_backend: ComputeBackend = ComputeBackend.CPU
    available_backends: List[ComputeBackend] = field(default_factory=lambda: [ComputeBackend.CPU])
    gpu_device_name: Optional[str] = None
    vram_bytes_total: int = 0
    vram_bytes_free: int = 0
    hardware_encoders: List[str] = field(default_factory=list)  # e.g., ["nvenc_h264", "qsv_hevc", "amf_av1"]
    hardware_decoders: List[str] = field(default_factory=list)
    supports_fp16: bool = False
    supports_bf16: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "primary_backend": self.primary_backend.value,
            "available_backends": [b.value for b in self.available_backends],
            "gpu_device_name": self.gpu_device_name,
            "vram_bytes_total": self.vram_bytes_total,
            "vram_bytes_free": self.vram_bytes_free,
            "hardware_encoders": self.hardware_encoders,
            "hardware_decoders": self.hardware_decoders,
            "supports_fp16": self.supports_fp16,
            "supports_bf16": self.supports_bf16,
        }

# ==============================================================================
# 3. Resource & Dependency Requirements
# ==============================================================================

@dataclass
class ResourceRequirements:
    """Resource constraints and minimum limits for Video Studio operation."""
    min_ram_mb: int = 4096
    recommended_ram_mb: int = 16384
    min_disk_free_mb: int = 10240
    requires_gpu: bool = False
    max_concurrent_renders: int = 2
    max_memory_percent: float = 80.0

@dataclass
class VideoStudioCapabilities:
    """Flags describing what functional capabilities are ready or permitted."""
    editing: bool = False
    motion: bool = False
    vfx: bool = False
    tracking: bool = False
    audio: bool = False
    color: bool = False
    captions: bool = False
    ai: bool = False
    recording: bool = False
    rendering: bool = False
    export: bool = False
    collaboration: bool = False
    extensions: bool = False

    def to_dict(self) -> Dict[str, bool]:
        return {
            "editing": self.editing,
            "motion": self.motion,
            "vfx": self.vfx,
            "tracking": self.tracking,
            "audio": self.audio,
            "color": self.color,
            "captions": self.captions,
            "ai": self.ai,
            "recording": self.recording,
            "rendering": self.rendering,
            "export": self.export,
            "collaboration": self.collaboration,
            "extensions": self.extensions,
        }

# ==============================================================================
# 4. Central Feature Contract & Metadata
# ==============================================================================

@dataclass
class VideoStudioMetadata:
    """Stable feature metadata descriptor."""
    feature_id: str = "omnia.feature.video_studio"
    display_name: str = "OMNIA Video Studio"
    version: str = "0.1.0"
    author: str = "OMNIA Core Architecture"
    description: str = (
        "Professional-grade modular video editing, compositing, motion graphics, "
        "and AI-assisted post-production environment for OMNIA."
    )
    supported_platforms: List[str] = field(default_factory=lambda: ["windows", "linux", "macos"])
    documentation_url: str = "docs/architecture/video_studio_module0.md"

@dataclass
class VideoStudioFeatureContract:
    """Central feature contract defining status, capabilities, and dependencies."""
    metadata: VideoStudioMetadata = field(default_factory=VideoStudioMetadata)
    state: VideoStudioState = VideoStudioState.DISCOVERED
    is_enabled: bool = False
    is_available: bool = True
    is_experimental: bool = False
    dependencies: List[str] = field(default_factory=lambda: ["core.config", "core.events"])
    required_capabilities: List[str] = field(default_factory=list)
    resource_requirements: ResourceRequirements = field(default_factory=ResourceRequirements)
    compute_capabilities: ComputeCapabilities = field(default_factory=ComputeCapabilities)
    active_capabilities: VideoStudioCapabilities = field(default_factory=VideoStudioCapabilities)
    error_message: Optional[str] = None
    last_state_change_ts: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.metadata.feature_id,
            "display_name": self.metadata.display_name,
            "version": self.metadata.version,
            "state": self.state.value,
            "is_enabled": self.is_enabled,
            "is_available": self.is_available,
            "is_experimental": self.is_experimental,
            "dependencies": self.dependencies,
            "required_capabilities": self.required_capabilities,
            "compute": self.compute_capabilities.to_dict(),
            "capabilities": self.active_capabilities.to_dict(),
            "error_message": self.error_message,
            "last_state_change_ts": self.last_state_change_ts,
        }

# ==============================================================================
# 5. Error Isolation Hierarchy
# ==============================================================================

class VideoStudioError(Exception):
    """Base error for all isolated Video Studio subsystem failures."""
    def __init__(self, message: str, code: str = "VIDEO_STUDIO_GENERIC", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}
        self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_class": self.__class__.__name__,
            "code": self.code,
            "message": str(self),
            "details": self.details,
            "timestamp": self.timestamp,
        }

class MediaError(VideoStudioError):
    """Errors encountered during media container inspection, parsing, or loading."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="MEDIA_ERROR", details=details)

class CodecError(VideoStudioError):
    """Errors related to unsupported, invalid, or missing video/audio codecs."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="CODEC_ERROR", details=details)

class DecodeError(CodecError):
    """Errors occurring during packet decoding or frame decompression."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details=details)
        self.code = "DECODE_ERROR"

class EncodeError(CodecError):
    """Errors occurring during frame compression or stream encoding."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, details=details)
        self.code = "ENCODE_ERROR"

class RenderError(VideoStudioError):
    """Errors occurring during timeline composition, effect graph evaluation, or rendering."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="RENDER_ERROR", details=details)

class GPUError(VideoStudioError):
    """Errors related to GPU acceleration, context allocation, or VRAM exhaustion."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="GPU_ERROR", details=details)

class AIProcessingError(VideoStudioError):
    """Errors in AI inference, model execution, transcription, or segmentation."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="AI_PROCESSING_ERROR", details=details)

class StorageError(VideoStudioError):
    """Errors in media caching, proxy persistence, or asset disk operations."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="STORAGE_ERROR", details=details)

class ExportError(VideoStudioError):
    """Errors encountered during final file packaging, multiplexing, or delivery."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="EXPORT_ERROR", details=details)
