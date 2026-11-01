"""OMNIA Video Studio — Shared Services Contracts & Interfaces (Module 0).

Establishes stable abstract contracts for:
1. Storage Engine
2. Job Queue & Processing Engine
3. GPU / Compute Acceleration Engine
4. AI Runtime Provider Interface
5. Resource Limiter & Governance

These interfaces ensure Video Studio consumes OMNIA Core infrastructure without coupling
or circular dependencies.
"""

from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable
import time

# ==============================================================================
# 1. Shared Storage Contract
# ==============================================================================

class MediaAssetCategory(str, Enum):
    SOURCE_MEDIA = "SOURCE_MEDIA"
    PROXY = "PROXY"
    PROJECT_METADATA = "PROJECT_METADATA"
    TIMELINE = "TIMELINE"
    THUMBNAIL = "THUMBNAIL"
    WAVEFORM = "WAVEFORM"
    GENERATED_ASSET = "GENERATED_ASSET"
    CACHE = "CACHE"
    EXPORT = "EXPORT"
    AUTOSAVE = "AUTOSAVE"
    PROJECT_ARCHIVE = "PROJECT_ARCHIVE"

@dataclass
class StorageDescriptor:
    asset_id: str
    project_id: str
    category: MediaAssetCategory
    file_path: str
    size_bytes: int = 0
    content_hash_sha256: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

class IVideoStorageContract(ABC):
    """Abstract interface defining required storage operations for Video Studio."""

    @abstractmethod
    def resolve_path(self, category: MediaAssetCategory, filename: str, project_id: Optional[str] = None) -> str:
        """Resolves a sandboxed filesystem path within approved project storage directories."""
        pass

    @abstractmethod
    def register_asset(self, descriptor: StorageDescriptor) -> bool:
        """Registers a stored media/cache asset into persistent metadata."""
        pass

    @abstractmethod
    def get_asset(self, asset_id: str) -> Optional[StorageDescriptor]:
        """Retrieves asset descriptor by ID."""
        pass

    @abstractmethod
    def purge_cache(self, older_than_sec: float) -> int:
        """Reclaims disk space by purging temporary waveform and render cache files."""
        pass

# ==============================================================================
# 2. Shared Job Processing Contract
# ==============================================================================

class VideoJobType(str, Enum):
    INGEST = "INGEST"
    PROXY_GENERATION = "PROXY_GENERATION"
    TRANSCODING = "TRANSCODING"
    ANALYSIS = "ANALYSIS"
    TRACKING = "TRACKING"
    RENDERING = "RENDERING"
    EXPORT = "EXPORT"
    TRANSCRIPTION = "TRANSCRIPTION"
    AI_GENERATION = "AI_GENERATION"
    AUDIO_PROCESSING = "AUDIO_PROCESSING"
    COLOR_PROCESSING = "COLOR_PROCESSING"

class VideoJobStatus(str, Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PAUSED = "PAUSED"

@dataclass
class VideoJobDescriptor:
    job_id: str
    job_type: VideoJobType
    project_id: str
    priority: int = 50  # 1-100, higher = higher priority
    status: VideoJobStatus = VideoJobStatus.PENDING
    progress_pct: float = 0.0
    parameters: Dict[str, Any] = field(default_factory=dict)
    resource_quota: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error_message: Optional[str] = None

class IVideoJobEngineContract(ABC):
    """Abstract contract for scheduling and managing asynchronous media tasks."""

    @abstractmethod
    def submit_job(self, descriptor: VideoJobDescriptor) -> str:
        """Queues a new video job for execution."""
        pass

    @abstractmethod
    def get_job(self, job_id: str) -> Optional[VideoJobDescriptor]:
        """Polls or inspects current job status and progress percentage."""
        pass

    @abstractmethod
    def cancel_job(self, job_id: str, reason: str = "") -> bool:
        """Cancels an active or pending job cleanly."""
        pass

    @abstractmethod
    def list_jobs(self, project_id: Optional[str] = None, status: Optional[VideoJobStatus] = None) -> List[VideoJobDescriptor]:
        """Lists jobs filtered by project or status."""
        pass

# ==============================================================================
# 3. Shared GPU / Compute Contract
# ==============================================================================

class IVideoComputeContract(ABC):
    """Abstract interface defining compute acceleration queries and allocations."""

    @abstractmethod
    def probe_compute_hardware(self) -> Dict[str, Any]:
        """Discovers host GPU/NPU/CPU capabilities and reports hardware acceleration availability."""
        pass

    @abstractmethod
    def acquire_compute_context(self, job_id: str, estimated_vram_mb: int) -> bool:
        """Reserves a GPU compute execution slot and VRAM allocation."""
        pass

    @abstractmethod
    def release_compute_context(self, job_id: str) -> None:
        """Releases GPU allocation upon job completion or failure."""
        pass

# ==============================================================================
# 4. Shared AI Runtime Contract
# ==============================================================================

class VideoAICapabilityType(str, Enum):
    TRANSCRIPTION = "TRANSCRIPTION"
    OBJECT_DETECTION = "OBJECT_DETECTION"
    FACE_DETECTION = "FACE_DETECTION"
    TRACKING = "TRACKING"
    SEGMENTATION = "SEGMENTATION"
    DEPTH_ESTIMATION = "DEPTH_ESTIMATION"
    VOICE_ISOLATION = "VOICE_ISOLATION"
    VOICE_SYNTHESIS = "VOICE_SYNTHESIS"
    DUBBING = "DUBBING"
    GENERATIVE_VIDEO = "GENERATIVE_VIDEO"
    SCRIPT_GENERATION = "SCRIPT_GENERATION"

@dataclass
class VideoAIRequest:
    request_id: str
    capability: VideoAICapabilityType
    model_family: Optional[str] = None
    input_uri: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)

@dataclass
class VideoAIResponse:
    request_id: str
    capability: VideoAICapabilityType
    success: bool
    result_data: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    error_message: Optional[str] = None

class IVideoAIRuntimeContract(ABC):
    """Abstract decoupled contract for AI inferencing requested by Video Studio."""

    @abstractmethod
    def has_capability(self, capability: VideoAICapabilityType) -> bool:
        """Queries whether a particular AI capability has a registered provider."""
        pass

    @abstractmethod
    def execute_ai_task(self, request: VideoAIRequest) -> VideoAIResponse:
        """Executes an AI inferencing request asynchronously without binding to a single model provider."""
        pass

# ==============================================================================
# 5. Shared Resource & Governance Limiter Contract
# ==============================================================================

from typing import Dict, Any, List, Optional, Callable, Tuple

class IVideoResourceGovernanceContract(ABC):
    """Abstract contract enforcing CPU, RAM, disk, and process execution limits."""

    @abstractmethod
    def check_headroom(self) -> Tuple[bool, str]:
        """Returns (has_sufficient_resources: bool, reason: str)."""
        pass

    @abstractmethod
    def enforce_limits(self) -> None:
        """Enforces process priority capping and memory ceiling restraints."""
        pass
