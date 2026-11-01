"""OMNIA Video Studio — Project Packaging, Media Archiving & Portable Workflow Service (Module 38).

Coordinates:
- Package creation, validation, restoration, and snapshot lifecycle.
- Portable relinking: updates restored project media library and sequences to point to newly extracted media paths.
- Named ProjectSnapshot management (create, list, inspect, compare).
- Capability registration in VideoStudioCapabilityRegistry under VideoStudioCategory.MEDIA and VideoStudioCategory.COLLABORATION.
"""

import os
import time
import uuid
import copy
import json
import logging
from typing import Dict, Any, List, Optional, Tuple, Set

from video_studio.package_models import (
    PACKAGE_FORMAT_VERSION,
    PackageType,
    ArchiveFormat,
    DependencyCategory,
    ExtractionPolicy,
    PackagedFileEntry,
    PackageManifest,
    ExtractionResult,
    ProjectSnapshot,
)
from video_studio.package_engine import PackageEngine, package_engine, compute_sha256
from video_studio.media_models import MediaAsset, AssetMediaType
from video_studio.media_library import ProjectMediaLibrary, media_library_registry
from video_studio.timeline_models import VideoSequence
from video_studio.timeline_service import TimelineService, timeline_service
from video_studio.timeline_serialization import timeline_serialization_engine
from video_studio.registry import video_studio_capability_registry
from video_studio.registry_models import (
    VideoStudioCategory,
    ImplementationState,
    VideoStudioCapabilityDescriptor,
)

logger = logging.getLogger("Omnia.VideoStudio.PackageService")


class PackageService:
    """Central service managing project archives, portable packages, snapshots, and portable restoration."""

    def __init__(
        self,
        engine: Optional[PackageEngine] = None,
        tl_service: Optional[TimelineService] = None,
    ):
        self.engine = engine or package_engine
        self.timeline_service = tl_service or timeline_service

        # In-memory snapshot catalog: snapshot_id -> ProjectSnapshot
        self._snapshots: Dict[str, ProjectSnapshot] = {}

        self.register_capabilities()

    def register_capabilities(self) -> None:
        """Register Module 38 capabilities into VideoStudioCapabilityRegistry."""
        caps = [
            VideoStudioCapabilityDescriptor(
                id="video.packaging.portable_archive",
                name="Portable Project Packaging & Archiving",
                description="Bundles project documents, original media, audio, and graphics into a verified standalone package.",
                category=VideoStudioCategory.COLLABORATION,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["packaging", "archive", "export", "portable"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.packaging.integrity_verification",
                name="Cryptographic Package Verification",
                description="SHA-256 manifest-to-content validation, truncation detection, and zip bomb defense.",
                category=VideoStudioCategory.MEDIA,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["integrity", "checksum", "verification", "security"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.packaging.safe_restoration",
                name="Safe Project Restoration & Relinking",
                description="Path traversal-safe archive extraction and automated local asset relinking.",
                category=VideoStudioCategory.COLLABORATION,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["restoration", "relinking", "unzip", "import"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.packaging.project_snapshots",
                name="Project Snapshot Lifecycle Management",
                description="Creates and tracks named historical revision checkpoints with checksums.",
                category=VideoStudioCategory.MEDIA,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["snapshots", "revisions", "versioning"],
            ),
        ]
        for cap in caps:
            if video_studio_capability_registry.get(cap.id) is None:
                video_studio_capability_registry.register(cap, auth_token="core")
        logger.info("Registered Module 38 Packaging capabilities.")

    # -------------------------------------------------------------------------
    # 1. Package Creation
    # -------------------------------------------------------------------------

    def create_project_package(
        self,
        project_id: str,
        output_archive_path: str,
        project_name: str = "Project",
        package_type: PackageType = PackageType.PORTABLE_PROJECT,
        categories: Optional[Set[DependencyCategory]] = None,
        description: str = "",
    ) -> PackageManifest:
        """Discovers dependencies and bundles project into a verified portable archive."""
        library = media_library_registry.get_or_create(project_id)

        inc, miss, exc = self.engine.discover_dependencies(
            project_id=project_id,
            media_library=library,
            timeline_svc=self.timeline_service,
            package_type=package_type,
            categories=categories,
        )

        manifest = self.engine.create_package(
            output_path=output_archive_path,
            project_id=project_id,
            project_name=project_name,
            included_dependencies=inc,
            missing_dependencies=miss,
            excluded_dependencies=exc,
            package_type=package_type,
            description=description,
        )
        return manifest

    # -------------------------------------------------------------------------
    # 2. Package Inspection & Verification
    # -------------------------------------------------------------------------

    def inspect_package(self, package_path: str) -> Tuple[bool, List[str], Optional[PackageManifest]]:
        """Safely inspects an archive without extracting its contents."""
        return self.engine.verify_package(package_path)

    # -------------------------------------------------------------------------
    # 3. Restoration & Relinking
    # -------------------------------------------------------------------------

    def restore_project_package(
        self,
        package_path: str,
        destination_root: str,
        policy: ExtractionPolicy = ExtractionPolicy.SAFE_NO_OVERWRITE,
        dry_run: bool = False,
    ) -> ExtractionResult:
        """Extracts package contents safely and relinks all assets to their new extracted locations."""
        res = self.engine.extract_package(
            package_path=package_path,
            destination_root=destination_root,
            policy=policy,
            dry_run=dry_run,
        )

        if not res.success or dry_run or not res.manifest:
            return res

        manifest = res.manifest
        dest_abs = os.path.abspath(destination_root)
        library = media_library_registry.get_or_create(manifest.project_id)

        # Map entries and relink assets in ProjectMediaLibrary
        for entry in manifest.entries:
            extracted_abs = os.path.join(dest_abs, entry.relative_path)

            if entry.category in (DependencyCategory.ORIGINAL_MEDIA, DependencyCategory.AUDIO_ASSETS, DependencyCategory.GRAPHICS_TITLES):
                # Update existing or register restored asset
                existing_asset = library.get_asset(entry.asset_id)
                if existing_asset:
                    existing_asset.file_location = extracted_abs
                    existing_asset.content_hash_sha256 = entry.sha256_checksum
                    existing_asset.size_bytes = entry.size_bytes
                else:
                    mtype = AssetMediaType.VIDEO
                    if entry.category == DependencyCategory.AUDIO_ASSETS:
                        mtype = AssetMediaType.AUDIO
                    elif entry.category == DependencyCategory.GRAPHICS_TITLES:
                        mtype = AssetMediaType.IMAGE

                    new_asset = MediaAsset(
                        asset_id=entry.asset_id,
                        project_id=manifest.project_id,
                        file_location=extracted_abs,
                        original_name=os.path.basename(extracted_abs),
                        media_type=mtype,
                        size_bytes=entry.size_bytes,
                        content_hash_sha256=entry.sha256_checksum,
                    )
                    library.add_asset(new_asset)
                res.relinked_assets_count += 1

            elif entry.category == DependencyCategory.PROJECT_DOCUMENTS:
                # Restore sequence into TimelineService
                if os.path.exists(extracted_abs):
                    try:
                        with open(extracted_abs, "r", encoding="utf-8") as f:
                            seq_json = f.read()
                        seq = timeline_serialization_engine.deserialize_sequence(seq_json)
                        self.timeline_service._sequences[seq.sequence_id] = seq
                    except Exception as e:
                        res.warnings.append(f"Failed to load sequence '{entry.relative_path}': {str(e)}")

        return res

    # -------------------------------------------------------------------------
    # 4. Snapshot Management
    # -------------------------------------------------------------------------

    def create_snapshot(
        self,
        project_id: str,
        snapshot_name: str,
        archive_dir: str,
        description: str = "",
    ) -> ProjectSnapshot:
        """Captures a named historical snapshot package of the project."""
        snap_id = f"snp_{uuid.uuid4().hex[:10]}"
        snap_file = os.path.join(archive_dir, f"{project_id}_{snap_id}.zip")

        manifest = self.create_project_package(
            project_id=project_id,
            output_archive_path=snap_file,
            project_name=snapshot_name,
            package_type=PackageType.PORTABLE_PROJECT,
            description=description,
        )

        size = os.path.getsize(snap_file)
        checksum = compute_sha256(snap_file)

        snap = ProjectSnapshot(
            snapshot_id=snap_id,
            project_id=project_id,
            name=snapshot_name,
            revision=manifest.project_revision,
            archive_path=snap_file,
            size_bytes=size,
            sha256_checksum=checksum,
            description=description,
        )
        self._snapshots[snap.snapshot_id] = snap
        return snap

    def list_snapshots(self, project_id: Optional[str] = None) -> List[ProjectSnapshot]:
        if project_id:
            return [s for s in self._snapshots.values() if s.project_id == project_id]
        return list(self._snapshots.values())

    def get_snapshot(self, snapshot_id: str) -> Optional[ProjectSnapshot]:
        return self._snapshots.get(snapshot_id)


# Global singleton
package_service = PackageService()
