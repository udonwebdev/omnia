"""OMNIA Video Studio — Project Packaging, Media Archiving & Portable Workflow Models (Module 38).

Defines authoritative domain models for:
- PackageType: PORTABLE_PROJECT, ARCHIVE_MASTER, PROXIES_ONLY, METADATA_ONLY
- PackageStatus: CREATED, VERIFIED, EXTRACTED, CORRUPTED, INCOMPLETE
- ArchiveFormat: ZIP_UNCOMPRESSED (STORE), ZIP_DEFLATED, TAR_GZ, DIRECTORY_BUNDLE
- DependencyCategory:
  * PROJECT_DOCUMENTS (Sequence & timeline project structures)
  * ORIGINAL_MEDIA (Source raw footage and master files)
  * PROXY_MEDIA (Lightweight editing proxies)
  * AUDIO_ASSETS (Music stems, voiceover, sfx)
  * CAPTIONS_SUBTITLES (Sidecar SRT/VTT/WebVTT, transcript documents)
  * GRAPHICS_TITLES (Motion graphics, title overlays, SVG/PNG assets)
  * MASKS_SEGMENTATION (Segmentation layers, rotoscope shapes)
  * COLOR_LUTS (Color look-up tables and grading presets)
  * GENERATED_MEDIA (Rendered freeze frames, synthesized intermediates)
  * EXPORTS (Final master deliverables)
- PackagedFileEntry: Relativized file entry with stable asset ID, SHA-256 checksum, size, and category
- PackageManifest: Versioned canonical manifest describing project snapshot, included dependencies, exclusions, and compatibility
- ExtractionPolicy: SAFE_NO_OVERWRITE, OVERWRITE_EXISTING, EXTRACT_WITH_NEW_IDS
- ExtractionResult: Outcome of extracting package (success, extracted file count, restored assets, relinked count, warnings, errors)
- ProjectSnapshot: Named historical snapshot checkpoint of project state
"""

import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set


PACKAGE_FORMAT_VERSION = "video-studio.package.v1"


class PackageType(str, Enum):
    """Scope of media and metadata collected into the package."""
    PORTABLE_PROJECT = "PORTABLE_PROJECT"         # Project + trimmed or full source media + graphics/captions for handoff
    ARCHIVE_MASTER = "ARCHIVE_MASTER"             # Complete preservation archive (all original media, audio, LUTs, exports)
    PROXIES_ONLY = "PROXIES_ONLY"                 # Project + proxies for remote/low-bandwidth laptop offline editing
    METADATA_ONLY = "METADATA_ONLY"               # Lightweight project files and transcripts only (no heavy video media)


class ArchiveFormat(str, Enum):
    """Physical archive encapsulation format."""
    ZIP_STORE = "ZIP_STORE"                       # Standard uncompressed zip (fast streaming, zero re-compression overhead)
    ZIP_DEFLATED = "ZIP_DEFLATED"                 # Standard deflated zip
    DIRECTORY_BUNDLE = "DIRECTORY_BUNDLE"         # Standalone portable directory structure (.vspackage folder)


class DependencyCategory(str, Enum):
    """Categorization of dependency files included in the package."""
    PROJECT_DOCUMENTS = "PROJECT_DOCUMENTS"
    ORIGINAL_MEDIA = "ORIGINAL_MEDIA"
    PROXY_MEDIA = "PROXY_MEDIA"
    AUDIO_ASSETS = "AUDIO_ASSETS"
    CAPTIONS_SUBTITLES = "CAPTIONS_SUBTITLES"
    GRAPHICS_TITLES = "GRAPHICS_TITLES"
    MASKS_SEGMENTATION = "MASKS_SEGMENTATION"
    COLOR_LUTS = "COLOR_LUTS"
    GENERATED_MEDIA = "GENERATED_MEDIA"
    EXPORTS = "EXPORTS"


class ExtractionPolicy(str, Enum):
    """Collision and overwriting safety policy during package extraction."""
    SAFE_NO_OVERWRITE = "SAFE_NO_OVERWRITE"       # Rejects extraction if target paths or project IDs exist
    OVERWRITE_EXISTING = "OVERWRITE_EXISTING"     # Overwrites target files with explicit user authorization
    EXTRACT_WITH_NEW_IDS = "EXTRACT_WITH_NEW_IDS" # Duplicates project & assets with brand new UUIDs to prevent collision


@dataclass
class PackagedFileEntry:
    """Descriptor for an individual file contained within the package."""
    asset_id: str                                 # Stable asset ID or document identifier
    relative_path: str                            # Relative archive storage path (e.g. "media/clip_01.mp4")
    category: DependencyCategory = DependencyCategory.ORIGINAL_MEDIA
    size_bytes: int = 0
    sha256_checksum: str = ""
    original_absolute_path: Optional[str] = None
    media_type: str = "video"                     # video, audio, image, subtitle, project_json
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "relative_path": self.relative_path,
            "category": self.category.value,
            "size_bytes": self.size_bytes,
            "sha256_checksum": self.sha256_checksum,
            "original_absolute_path": self.original_absolute_path,
            "media_type": self.media_type,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PackagedFileEntry":
        return cls(
            asset_id=data.get("asset_id", f"asset_{uuid.uuid4().hex[:8]}"),
            relative_path=data.get("relative_path", ""),
            category=DependencyCategory(data.get("category", DependencyCategory.ORIGINAL_MEDIA.value)),
            size_bytes=int(data.get("size_bytes", 0)),
            sha256_checksum=data.get("sha256_checksum", ""),
            original_absolute_path=data.get("original_absolute_path"),
            media_type=data.get("media_type", "video"),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class PackageManifest:
    """Master versioned manifest serialized into manifest.json at the package root."""
    package_id: str = field(default_factory=lambda: f"pkg_{uuid.uuid4().hex[:10]}")
    format_version: str = PACKAGE_FORMAT_VERSION
    omnia_version: str = "1.0.0"
    video_studio_module_version: int = 38
    project_id: str = "default_project"
    project_name: str = "Untitled Project"
    project_revision: int = 1
    package_type: PackageType = PackageType.PORTABLE_PROJECT
    created_at: float = field(default_factory=time.time)
    creator: str = "OMNIA Video Studio Archive Engine"
    description: str = ""
    
    # Entries and dependencies
    entries: List[PackagedFileEntry] = field(default_factory=list)
    excluded_dependencies: List[Dict[str, Any]] = field(default_factory=list) # {asset_id, reason, original_path}
    missing_dependencies: List[Dict[str, Any]] = field(default_factory=list)  # {asset_id, original_path, error}
    required_capabilities: List[str] = field(default_factory=list)
    
    # Integrity and stats
    total_uncompressed_bytes: int = 0
    file_count: int = 0
    package_checksum_sha256: Optional[str] = None

    def recalculate_totals(self) -> None:
        """Sums up entries count and bytes."""
        self.file_count = len(self.entries)
        self.total_uncompressed_bytes = sum(e.size_bytes for e in self.entries)

    def to_dict(self) -> Dict[str, Any]:
        self.recalculate_totals()
        return {
            "package_id": self.package_id,
            "format_version": self.format_version,
            "omnia_version": self.omnia_version,
            "video_studio_module_version": self.video_studio_module_version,
            "project_id": self.project_id,
            "project_name": self.project_name,
            "project_revision": self.project_revision,
            "package_type": self.package_type.value,
            "created_at": self.created_at,
            "creator": self.creator,
            "description": self.description,
            "total_uncompressed_bytes": self.total_uncompressed_bytes,
            "file_count": self.file_count,
            "package_checksum_sha256": self.package_checksum_sha256,
            "required_capabilities": list(self.required_capabilities),
            "entries": [e.to_dict() for e in self.entries],
            "excluded_dependencies": list(self.excluded_dependencies),
            "missing_dependencies": list(self.missing_dependencies),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PackageManifest":
        m = cls(
            package_id=data.get("package_id", f"pkg_{uuid.uuid4().hex[:10]}"),
            format_version=data.get("format_version", PACKAGE_FORMAT_VERSION),
            omnia_version=data.get("omnia_version", "1.0.0"),
            video_studio_module_version=int(data.get("video_studio_module_version", 38)),
            project_id=data.get("project_id", "default_project"),
            project_name=data.get("project_name", "Untitled Project"),
            project_revision=int(data.get("project_revision", 1)),
            package_type=PackageType(data.get("package_type", PackageType.PORTABLE_PROJECT.value)),
            created_at=float(data.get("created_at", time.time())),
            creator=data.get("creator", "OMNIA Video Studio"),
            description=data.get("description", ""),
            total_uncompressed_bytes=int(data.get("total_uncompressed_bytes", 0)),
            file_count=int(data.get("file_count", 0)),
            package_checksum_sha256=data.get("package_checksum_sha256"),
            required_capabilities=list(data.get("required_capabilities", [])),
            entries=[PackagedFileEntry.from_dict(e) for e in data.get("entries", [])],
            excluded_dependencies=list(data.get("excluded_dependencies", [])),
            missing_dependencies=list(data.get("missing_dependencies", [])),
        )
        return m


@dataclass
class ExtractionResult:
    """Outcome of package validation and restoration."""
    success: bool = True
    manifest: Optional[PackageManifest] = None
    destination_root: str = ""
    extracted_files_count: int = 0
    relinked_assets_count: int = 0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    restored_project_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "destination_root": self.destination_root,
            "extracted_files_count": self.extracted_files_count,
            "relinked_assets_count": self.relinked_assets_count,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "restored_project_id": self.restored_project_id,
        }


@dataclass
class ProjectSnapshot:
    """Named versioned snapshot record for a project."""
    snapshot_id: str = field(default_factory=lambda: f"snp_{uuid.uuid4().hex[:10]}")
    project_id: str = "default_project"
    name: str = "Snapshot"
    revision: int = 1
    archive_path: str = ""
    size_bytes: int = 0
    sha256_checksum: str = ""
    created_at: float = field(default_factory=time.time)
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "project_id": self.project_id,
            "name": self.name,
            "revision": self.revision,
            "archive_path": self.archive_path,
            "size_bytes": self.size_bytes,
            "sha256_checksum": self.sha256_checksum,
            "created_at": self.created_at,
            "description": self.description,
        }
