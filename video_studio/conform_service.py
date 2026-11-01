"""OMNIA Video Studio — Module 43: Media Conform, Offline Editing & High-Resolution Relink Service.

Enterprise service managing:
- Proxy generation jobs and profiles (540p, 720p, 1080p).
- Two-way proxy-to-source mapping records (`ProxyMappingRecord`).
- Playback mode switching (ORIGINAL vs PROXY) preserving in/out points, effects, and timeline synchronization.
- Online conform preflight auditing and transactional timeline relinking with rollback snapshots.
- Final export validation ensuring original high-res media is conformed before master renders.
- Capability registration in VideoStudioCapabilityRegistry.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from video_studio.conform_engine import ConformEngine
from video_studio.conform_models import (
    ConformCompatibilityGrade,
    ConformPreflightReport,
    ConformTransactionResult,
    MediaRepresentationMode,
    ProxyMappingRecord,
    ProxyProfile,
)
from video_studio.media_library import ProjectMediaLibrary, media_library_registry
from video_studio.media_models import AssetLifecycleStatus, AssetMediaType, MediaAsset
from video_studio.provenance_engine import compute_file_sha256_chunked
from video_studio.registry import VideoStudioCapabilityRegistry, video_studio_capability_registry
from video_studio.registry_models import (
    ImplementationState,
    VideoStudioCategory,
    VideoStudioCapabilityDescriptor,
)
from video_studio.timeline_models import VideoSequence
from video_studio.timeline_service import TimelineService, timeline_service

logger = logging.getLogger("omnia.video_studio.conform")


class ConformService:
    """Enterprise Media Conform, Offline Editing & High-Resolution Online Relink Service."""

    def __init__(
        self,
        capability_registry: Optional[VideoStudioCapabilityRegistry] = None,
        tl_service: Optional[TimelineService] = None,
        media_registry: Optional[Any] = None,
        versioning_svc: Optional[Any] = None,
        audit_log_path: str = "omnia_audit.jsonl",
    ) -> None:
        self.registry = capability_registry or video_studio_capability_registry
        self.timeline_service = tl_service or timeline_service
        self.media_registry = media_registry or media_library_registry
        self.versioning_service = versioning_svc
        self.audit_log_path = audit_log_path
        self.engine = ConformEngine()

        # In-memory proxy mappings:
        # mapping_id -> ProxyMappingRecord
        self._mappings: Dict[str, ProxyMappingRecord] = {}
        # (project_id, original_asset_id) -> mapping_id
        self._orig_to_mapping: Dict[Tuple[str, str], str] = {}
        # (project_id, proxy_asset_id) -> mapping_id
        self._proxy_to_mapping: Dict[Tuple[str, str], str] = {}

        # Reusable Proxy Profiles
        self._profiles: Dict[str, ProxyProfile] = {}
        self._init_built_in_profiles()

        # Active representation mode per sequence: sequence_id -> MediaRepresentationMode
        self._sequence_modes: Dict[str, MediaRepresentationMode] = {}

        if self.registry:
            self.register_capabilities()

    def _init_built_in_profiles(self) -> None:
        """Initializes standard offline editing proxy presets."""
        p_720p = ProxyProfile(
            profile_id="proxy_720p_standard",
            name="720p Standard Offline Proxy",
            target_width=1280,
            target_height=720,
            bitrate_kbps=2500,
        )
        p_540p = ProxyProfile(
            profile_id="proxy_540p_light",
            name="540p Lightweight Offline Proxy",
            target_width=960,
            target_height=540,
            bitrate_kbps=1200,
        )
        p_1080p = ProxyProfile(
            profile_id="proxy_1080p_prores",
            name="1080p High-Quality Offline Proxy",
            target_width=1920,
            target_height=1080,
            bitrate_kbps=5000,
        )
        self._profiles[p_720p.profile_id] = p_720p
        self._profiles[p_540p.profile_id] = p_540p
        self._profiles[p_1080p.profile_id] = p_1080p

    def register_capabilities(self) -> None:
        """Registers Module 43 Conform capabilities into the registry."""
        capabilities = [
            VideoStudioCapabilityDescriptor(
                id="video.conform.offline_proxy_workflow",
                name="Offline Proxy Editing & Source Binding",
                description="Preserves frame-accurate identity and timecode mapping between proxies and original media.",
                category=VideoStudioCategory.MEDIA,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["conform", "proxy", "offline", "workflow"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.conform.representation_switching",
                name="Seamless Media Representation Switching",
                description="Non-destructive instant toggle between proxy and original sources during timeline playback.",
                category=VideoStudioCategory.TIMELINE,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["playback", "proxy_switching", "representation"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.conform.online_relink_engine",
                name="High-Resolution Online Conform Engine",
                description="Preflight audit and transactional conform swapping from proxies back to original media.",
                category=VideoStudioCategory.MEDIA,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["conform", "online_relink", "master_render"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.conform.render_validation_gate",
                name="Final Quality Render Conform Validation Gate",
                description="Enforces strict pre-render check preventing proxy media from leaking into master exports.",
                category=VideoStudioCategory.EXPORT,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["export", "validation", "master_render", "safety_gate"],
            ),
        ]
        for cap in capabilities:
            if not self.registry.get(cap.id):
                self.registry.register(cap, auth_token="core")

    def _log_audit_event(self, event_type: str, details: Dict[str, Any]) -> None:
        payload = {
            "event_type": event_type,
            "timestamp": time.time(),
            "details": details,
        }
        try:
            with open(self.audit_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload) + "\n")
        except Exception as e:
            logger.warning(f"Failed to append to audit log {self.audit_log_path}: {e}")

    # =========================================================================
    # 1. Proxy Mapping & Generation Records
    # =========================================================================

    def register_proxy_mapping(
        self,
        project_id: str,
        original_asset_id: str,
        proxy_asset_id: str,
        profile_id: str = "proxy_720p_standard",
    ) -> ProxyMappingRecord:
        """Registers an authoritative binding between original source and its generated proxy."""
        library = self.media_registry.get_or_create(project_id) if hasattr(self.media_registry, "get_or_create") else None
        if not library:
            raise KeyError(f"Project '{project_id}' media library not found.")

        orig = library.get_asset(original_asset_id)
        proxy = library.get_asset(proxy_asset_id)
        if not orig:
            raise KeyError(f"Original asset '{original_asset_id}' not found.")
        if not proxy:
            raise KeyError(f"Proxy asset '{proxy_asset_id}' not found.")

        mapping = ProxyMappingRecord(
            project_id=project_id,
            original_asset_id=original_asset_id,
            proxy_asset_id=proxy_asset_id,
            original_fingerprint_sha256=orig.content_hash_sha256 or "",
            proxy_fingerprint_sha256=proxy.content_hash_sha256 or "",
            profile_id=profile_id,
            original_file_path=orig.file_location,
            original_width=orig.width or 1920,
            original_height=orig.height or 1080,
            original_fps=orig.frame_rate or 24.0,
            original_total_frames=orig.total_frames,
            original_duration_seconds=orig.duration_seconds,
            original_audio_channels=orig.audio_channels or 2,
            proxy_file_path=proxy.file_location,
            proxy_width=proxy.width or 1280,
            proxy_height=proxy.height or 720,
            proxy_fps=proxy.frame_rate or 24.0,
            proxy_total_frames=proxy.total_frames,
            proxy_duration_seconds=proxy.duration_seconds,
        )

        self._mappings[mapping.mapping_id] = mapping
        self._orig_to_mapping[(project_id, original_asset_id)] = mapping.mapping_id
        self._proxy_to_mapping[(project_id, proxy_asset_id)] = mapping.mapping_id

        self._log_audit_event("PROXY_MAPPING_REGISTERED", mapping.to_dict())
        return mapping

    def get_mapping_by_original(self, project_id: str, original_asset_id: str) -> Optional[ProxyMappingRecord]:
        mid = self._orig_to_mapping.get((project_id, original_asset_id))
        return self._mappings.get(mid) if mid else None

    def get_mapping_by_proxy(self, project_id: str, proxy_asset_id: str) -> Optional[ProxyMappingRecord]:
        mid = self._proxy_to_mapping.get((project_id, proxy_asset_id))
        return self._mappings.get(mid) if mid else None

    # =========================================================================
    # 2. Representation Mode & Playback Switching
    # =========================================================================

    def get_sequence_representation_mode(self, sequence_id: str) -> MediaRepresentationMode:
        return self._sequence_modes.get(sequence_id, MediaRepresentationMode.ORIGINAL)

    def switch_representation_mode(
        self,
        project_id: str,
        sequence_id: str,
        target_mode: MediaRepresentationMode,
    ) -> ConformTransactionResult:
        """Seamlessly switches active timeline playback between original source and proxies."""
        sequence = self.timeline_service.get_sequence(sequence_id)
        if not sequence:
            raise KeyError(f"Sequence '{sequence_id}' not found.")

        current_mode = self.get_sequence_representation_mode(sequence_id)
        if current_mode == target_mode:
            return ConformTransactionResult(
                success=True,
                project_id=project_id,
                sequence_id=sequence_id,
                target_mode=target_mode,
                conformed_clips_count=0,
                warnings=[f"Sequence '{sequence_id}' is already in {target_mode.value} representation mode."],
            )

        library = self.media_registry.get_or_create(project_id) if hasattr(self.media_registry, "get_or_create") else None
        assets: Dict[str, MediaAsset] = library._assets if library else {}

        # Build proxy mapping dict
        proxy_mappings = {m.proxy_asset_id: m for m in self._mappings.values() if m.project_id == project_id}
        orig_mappings = {m.original_asset_id: m for m in self._mappings.values() if m.project_id == project_id}

        updated_count = 0
        for track in sequence.tracks:
            for item in track.items:
                curr_ref = item.source_reference_id
                if target_mode == MediaRepresentationMode.PROXY:
                    m = orig_mappings.get(curr_ref)
                    if m:
                        item.source_reference_id = m.proxy_asset_id
                        updated_count += 1
                elif target_mode == MediaRepresentationMode.ORIGINAL:
                    m = proxy_mappings.get(curr_ref)
                    if m:
                        item.source_reference_id = m.original_asset_id
                        updated_count += 1

        sequence.updated_at = time.time()
        self._sequence_modes[sequence_id] = target_mode

        self._log_audit_event("REPRESENTATION_MODE_SWITCHED", {
            "project_id": project_id,
            "sequence_id": sequence_id,
            "target_mode": target_mode.value,
            "updated_clips": updated_count,
        })

        return ConformTransactionResult(
            success=True,
            project_id=project_id,
            sequence_id=sequence_id,
            target_mode=target_mode,
            conformed_clips_count=updated_count,
        )

    # =========================================================================
    # 3. Online Conform Preflight & Execution
    # =========================================================================

    def run_conform_preflight(
        self,
        project_id: str,
        sequence_id: str,
    ) -> ConformPreflightReport:
        """Audits all sequence clips against original source files before full-quality conform."""
        sequence = self.timeline_service.get_sequence(sequence_id)
        if not sequence:
            raise KeyError(f"Sequence '{sequence_id}' not found.")

        library = self.media_registry.get_or_create(project_id) if hasattr(self.media_registry, "get_or_create") else None
        assets: Dict[str, MediaAsset] = library._assets if library else {}
        proxy_mappings = {m.proxy_asset_id: m for m in self._mappings.values() if m.project_id == project_id}

        return self.engine.generate_preflight_report(
            project_id=project_id,
            sequence=sequence,
            mappings=proxy_mappings,
            assets=assets,
            target_mode=MediaRepresentationMode.ORIGINAL,
        )

    def execute_online_conform(
        self,
        project_id: str,
        sequence_id: str,
        create_rollback_checkpoint: bool = True,
        actor_id: str = "editor",
    ) -> ConformTransactionResult:
        """Executes full online conform, reverting all proxy clips back to high-resolution sources."""
        # Step 1: Preflight validation
        report = self.run_conform_preflight(project_id, sequence_id)
        if not report.is_ready_for_online_render:
            return ConformTransactionResult(
                success=False,
                project_id=project_id,
                sequence_id=sequence_id,
                target_mode=MediaRepresentationMode.ORIGINAL,
                errors=[
                    f"Online conform blocked: {report.blocking_issues_count} blocking issue(s) detected. Run preflight for details."
                ],
            )

        # Step 2: Rollback snapshot via Module 41 Versioning
        rollback_snap_id = None
        if create_rollback_checkpoint and self.versioning_service:
            snap = self.versioning_service.create_snapshot(
                project_id=project_id,
                sequence_id=sequence_id,
                name="Pre-Conform Safety Checkpoint",
                message=f"Automatic safety checkpoint prior to online conform by {actor_id}",
                author_id=actor_id,
                is_protected=True,
            )
            rollback_snap_id = snap.revision_id

        # Step 3: Switch representation to ORIGINAL
        res = self.switch_representation_mode(
            project_id=project_id,
            sequence_id=sequence_id,
            target_mode=MediaRepresentationMode.ORIGINAL,
        )
        res.rollback_snapshot_id = rollback_snap_id

        self._log_audit_event("ONLINE_CONFORM_EXECUTED", {
            "project_id": project_id,
            "sequence_id": sequence_id,
            "rollback_snapshot_id": rollback_snap_id,
            "conformed_clips": res.conformed_clips_count,
        })
        return res

    # =========================================================================
    # 4. Render Validation Gate
    # =========================================================================

    def validate_export_conform_readiness(
        self,
        project_id: str,
        sequence_id: str,
        allow_proxy_draft: bool = False,
    ) -> Tuple[bool, List[str]]:
        """Safety gate: prevents final quality rendering if proxy media remains or source media is missing."""
        mode = self.get_sequence_representation_mode(sequence_id)
        if mode == MediaRepresentationMode.PROXY and not allow_proxy_draft:
            return False, [
                "Export rejected: Project is currently in PROXY representation mode. Final export requires online conform."
            ]

        preflight = self.run_conform_preflight(project_id, sequence_id)
        if not preflight.is_ready_for_online_render and not allow_proxy_draft:
            errs = [f"Conform issue: {i.message}" for i in preflight.issues if i.grade == ConformCompatibilityGrade.BLOCKING]
            return False, errs

        return True, []


# Global singleton
conform_service = ConformService()
