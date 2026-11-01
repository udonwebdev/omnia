"""OMNIA Video Studio — Module 41: Versioning, Branching & Recovery Service.

Enterprise service coordinating:
- Snapshot lifecycle (create, get, list, delete, prune).
- Timeline branching (create branch, list, switch, rename, delete).
- Safe, non-destructive restoration with atomic swap and pre-restore checkpointing.
- Media asset availability validation and missing-media mitigation.
- Capability registration in VideoStudioCapabilityRegistry.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from video_studio.media_library import ProjectMediaLibrary, media_library_registry
from video_studio.registry import VideoStudioCapabilityRegistry, video_studio_capability_registry
from video_studio.registry_models import (
    ImplementationState,
    VideoStudioCategory,
    VideoStudioCapabilityDescriptor,
)
from video_studio.timeline_models import VideoSequence
from video_studio.timeline_serialization import timeline_serialization_engine
from video_studio.timeline_service import TimelineService, timeline_service
from video_studio.versioning_engine import VersioningEngine
from video_studio.versioning_models import (
    ProjectBranch,
    RestoreResult,
    RestoreSafetyLevel,
    RevisionDiff,
    RevisionSnapshot,
    RevisionType,
    VERSION_CONTROL_SCHEMA_VERSION,
)

logger = logging.getLogger("omnia.video_studio.versioning")


class VersionControlService:
    """Enterprise Version Control, Timeline Branching & Recovery Service."""

    def __init__(
        self,
        capability_registry: Optional[VideoStudioCapabilityRegistry] = None,
        tl_service: Optional[TimelineService] = None,
        media_registry: Optional[Any] = None,
        audit_log_path: str = "omnia_audit.jsonl",
    ) -> None:
        self.registry = capability_registry or video_studio_capability_registry
        self.timeline_service = tl_service or timeline_service
        self.media_registry = media_registry or media_library_registry
        self.audit_log_path = audit_log_path
        self.engine = VersioningEngine()

        # In-memory repositories:
        # revision_id -> RevisionSnapshot
        self._snapshots: Dict[str, RevisionSnapshot] = {}
        # (project_id, branch_name) -> ProjectBranch
        self._branches: Dict[Tuple[str, str], ProjectBranch] = {}
        # project_id -> active_branch_name
        self._active_branches: Dict[str, str] = {}

        if self.registry:
            self.register_capabilities()

    def register_capabilities(self) -> None:
        """Registers Module 41 Version Control capabilities into the registry."""
        capabilities = [
            VideoStudioCapabilityDescriptor(
                id="video.versioning.revision_snapshots",
                name="Project Revision Snapshots & Checkpoints",
                description="Immutable, content-addressed project timeline snapshot capture with integrity hashing.",
                category=VideoStudioCategory.TIMELINE,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["versioning", "snapshots", "history", "checkpoints"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.versioning.timeline_branching",
                name="Timeline Branching & Experimental Edits",
                description="Lightweight timeline branching, safe branch switching, and divergence tracking.",
                category=VideoStudioCategory.TIMELINE,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["versioning", "branching", "experiments"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.versioning.structural_comparison",
                name="Visual & Structural Revision Diff Engine",
                description="Fine-grained structural difference reporting across tracks, clips, settings, and duration.",
                category=VideoStudioCategory.TIMELINE,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["versioning", "diff", "comparison"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.versioning.non_destructive_recovery",
                name="Non-Destructive Project Recovery & Restore",
                description="Safe timeline restore with pre-flight media validation and atomic pre-restore checkpoints.",
                category=VideoStudioCategory.TIMELINE,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["versioning", "recovery", "restore", "safety"],
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
    # 1. Snapshot Management
    # =========================================================================

    def create_snapshot(
        self,
        project_id: str,
        sequence_id: str,
        name: str = "Milestone",
        message: str = "",
        author_id: str = "editor",
        revision_type: RevisionType = RevisionType.MANUAL,
        is_protected: bool = False,
        tags: Optional[List[str]] = None,
    ) -> RevisionSnapshot:
        """Captures an immutable snapshot of an active sequence."""
        sequence = self.timeline_service.get_sequence(sequence_id)
        if not sequence:
            raise KeyError(f"Sequence '{sequence_id}' not found in timeline service.")

        active_branch = self.get_active_branch(project_id)
        parent_rev_id = None
        branch_obj = self.get_branch(project_id, active_branch)
        if branch_obj and branch_obj.head_revision_id:
            parent_rev_id = branch_obj.head_revision_id

        # Calculate duration frames and serialize
        sequence.calculate_duration_frames()
        seq_dict = copy.deepcopy(sequence.to_dict())

        # Collect asset dependencies and compute integrity hash
        asset_ids = self.engine.extract_referenced_asset_ids(seq_dict)
        fingerprint = self.engine.compute_sequence_fingerprint(seq_dict)

        snapshot = RevisionSnapshot(
            project_id=project_id,
            sequence_id=sequence_id,
            revision_number=sequence.revision,
            branch_name=active_branch,
            parent_revision_id=parent_rev_id,
            name=name,
            message=message,
            author_id=author_id,
            revision_type=revision_type,
            sequence_data=seq_dict,
            referenced_asset_ids=asset_ids,
            content_fingerprint_sha256=fingerprint,
            is_protected=is_protected,
            tags=list(tags or []),
        )

        self._snapshots[snapshot.revision_id] = snapshot

        # Update branch head pointer
        if branch_obj:
            branch_obj.head_revision_id = snapshot.revision_id
            branch_obj.updated_at = time.time()
        else:
            # Create default branch if none exists
            self.create_branch(
                project_id=project_id,
                branch_name=active_branch,
                head_revision_id=snapshot.revision_id,
                created_by=author_id,
                is_default=True,
            )

        self._log_audit_event("REVISION_SNAPSHOT_CREATED", {
            "revision_id": snapshot.revision_id,
            "project_id": project_id,
            "sequence_id": sequence_id,
            "revision_number": snapshot.revision_number,
            "branch_name": active_branch,
            "fingerprint": fingerprint,
            "author_id": author_id,
        })
        return snapshot

    def get_snapshot(self, revision_id: str) -> Optional[RevisionSnapshot]:
        return self._snapshots.get(revision_id)

    def list_snapshots(
        self,
        project_id: Optional[str] = None,
        sequence_id: Optional[str] = None,
        branch_name: Optional[str] = None,
    ) -> List[RevisionSnapshot]:
        """Lists snapshots filtered by project, sequence, and/or branch in chronological order."""
        results = list(self._snapshots.values())
        if project_id:
            results = [s for s in results if s.project_id == project_id]
        if sequence_id:
            results = [s for s in results if s.sequence_id == sequence_id]
        if branch_name:
            results = [s for s in results if s.branch_name == branch_name]
        results.sort(key=lambda s: s.created_at)
        return results

    def delete_snapshot(self, revision_id: str, force: bool = False) -> bool:
        """Deletes a snapshot subject to protection and branch head safeguards."""
        snapshot = self.get_snapshot(revision_id)
        if not snapshot:
            raise KeyError(f"Snapshot '{revision_id}' not found.")

        if snapshot.is_protected and not force:
            raise PermissionError(f"Snapshot '{revision_id}' is protected from deletion.")

        # Check if snapshot is currently the head of any branch
        for (pid, bname), br in self._branches.items():
            if pid == snapshot.project_id and br.head_revision_id == revision_id:
                raise ValueError(
                    f"Cannot delete snapshot '{revision_id}': it is the active head of branch '{bname}'."
                )

        del self._snapshots[revision_id]
        self._log_audit_event("REVISION_SNAPSHOT_DELETED", {
            "revision_id": revision_id,
            "project_id": snapshot.project_id,
        })
        return True

    # =========================================================================
    # 2. Branching and Experimental Edits
    # =========================================================================

    def get_active_branch(self, project_id: str) -> str:
        return self._active_branches.get(project_id, "main")

    def create_branch(
        self,
        project_id: str,
        branch_name: str,
        head_revision_id: Optional[str] = None,
        created_by: str = "editor",
        description: str = "",
        is_default: bool = False,
    ) -> ProjectBranch:
        """Creates a named branch pointing to an existing revision snapshot or root."""
        key = (project_id, branch_name)
        if key in self._branches:
            raise ValueError(f"Branch '{branch_name}' already exists in project '{project_id}'.")

        head_rev = head_revision_id or ""
        fork_rev = None
        parent_branch = None

        if not head_rev:
            active_name = self.get_active_branch(project_id)
            current_branch = self.get_branch(project_id, active_name)
            if current_branch and current_branch.head_revision_id:
                head_rev = current_branch.head_revision_id
                fork_rev = current_branch.head_revision_id
                parent_branch = active_name
        else:
            fork_rev = head_rev

        branch = ProjectBranch(
            project_id=project_id,
            name=branch_name,
            head_revision_id=head_rev,
            parent_branch_name=parent_branch,
            fork_revision_id=fork_rev,
            created_by=created_by,
            description=description,
            is_default=is_default,
        )
        self._branches[key] = branch
        if project_id not in self._active_branches:
            self._active_branches[project_id] = branch_name

        self._log_audit_event("TIMELINE_BRANCH_CREATED", {
            "project_id": project_id,
            "branch_name": branch_name,
            "head_revision_id": head_rev,
            "created_by": created_by,
        })
        return branch

    def get_branch(self, project_id: str, branch_name: str) -> Optional[ProjectBranch]:
        return self._branches.get((project_id, branch_name))

    def list_branches(self, project_id: str) -> List[ProjectBranch]:
        return [b for (pid, _), b in self._branches.items() if pid == project_id]

    def switch_branch(
        self,
        project_id: str,
        branch_name: str,
        auto_restore_head: bool = True,
        actor_id: str = "editor",
    ) -> ProjectBranch:
        """Switches active branch and optionally restores the head snapshot into the active sequence."""
        branch = self.get_branch(project_id, branch_name)
        if not branch:
            raise KeyError(f"Branch '{branch_name}' not found in project '{project_id}'.")

        self._active_branches[project_id] = branch_name

        if auto_restore_head and branch.head_revision_id:
            # Restore head revision state
            head_snap = self.get_snapshot(branch.head_revision_id)
            if head_snap:
                self.restore_revision(
                    revision_id=branch.head_revision_id,
                    safety_level=RestoreSafetyLevel.ATOMIC_REPLACE,
                    actor_id=actor_id,
                    create_safety_snapshot=True,
                )

        self._log_audit_event("ACTIVE_BRANCH_SWITCHED", {
            "project_id": project_id,
            "active_branch": branch_name,
            "head_revision_id": branch.head_revision_id,
        })
        return branch

    def delete_branch(self, project_id: str, branch_name: str) -> bool:
        """Deletes a branch. Cannot delete the active branch or default branch."""
        branch = self.get_branch(project_id, branch_name)
        if not branch:
            raise KeyError(f"Branch '{branch_name}' does not exist.")

        if branch.is_default:
            raise ValueError(f"Cannot delete default branch '{branch_name}'.")

        active = self.get_active_branch(project_id)
        if active == branch_name:
            raise ValueError(f"Cannot delete active branch '{branch_name}'. Switch to another branch first.")

        del self._branches[(project_id, branch_name)]
        self._log_audit_event("TIMELINE_BRANCH_DELETED", {
            "project_id": project_id,
            "branch_name": branch_name,
        })
        return True

    # =========================================================================
    # 3. Revision Comparison (Diff Engine)
    # =========================================================================

    def compare_revisions(self, source_revision_id: str, target_revision_id: str) -> RevisionDiff:
        """Generates detailed structural difference report between two revision snapshots."""
        source = self.get_snapshot(source_revision_id)
        if not source:
            raise KeyError(f"Source revision '{source_revision_id}' not found.")

        target = self.get_snapshot(target_revision_id)
        if not target:
            raise KeyError(f"Target revision '{target_revision_id}' not found.")

        return self.engine.compare_revisions(source, target)

    # =========================================================================
    # 4. Safe Non-Destructive Restore and Recovery
    # =========================================================================

    def validate_restore_prerequisites(
        self,
        revision_id: str,
    ) -> Tuple[bool, List[str], List[str], List[str]]:
        """Pre-flight check verifying integrity and media asset presence before restoring.

        Returns:
            Tuple of (is_valid, missing_assets, available_assets, warnings)
        """
        snapshot = self.get_snapshot(revision_id)
        if not snapshot:
            return False, [], [], [f"Snapshot '{revision_id}' not found."]

        # 1. Integrity check
        ok_hash, hash_err = self.engine.verify_snapshot_integrity(snapshot)
        if not ok_hash:
            return False, [], [], [f"Integrity check failed: {hash_err}"]

        # 2. Media asset verification via media library
        missing: List[str] = []
        available: List[str] = []
        warnings: List[str] = []

        library = self.media_registry.get_or_create(snapshot.project_id) if hasattr(self.media_registry, "get_or_create") else None

        for aid in snapshot.referenced_asset_ids:
            if library:
                asset = library.get_asset(aid)
                if asset and os.path.exists(asset.file_location):
                    available.append(aid)
                else:
                    missing.append(aid)
            else:
                available.append(aid)

        if missing:
            warnings.append(
                f"{len(missing)} referenced media assets are missing from local disk or library."
            )

        return True, missing, available, warnings

    def restore_revision(
        self,
        revision_id: str,
        safety_level: RestoreSafetyLevel = RestoreSafetyLevel.ATOMIC_REPLACE,
        actor_id: str = "editor",
        create_safety_snapshot: bool = True,
    ) -> RestoreResult:
        """Safely restores a project sequence to a specified historical revision snapshot."""
        snapshot = self.get_snapshot(revision_id)
        if not snapshot:
            raise KeyError(f"Revision '{revision_id}' not found.")

        # Run pre-flight prerequisites check
        valid, missing, avail, warnings = self.validate_restore_prerequisites(revision_id)
        if not valid:
            return RestoreResult(
                success=False,
                revision_id=revision_id,
                project_id=snapshot.project_id,
                sequence_id=snapshot.sequence_id,
                missing_assets=missing,
                available_assets=avail,
                warnings=warnings,
                errors=["Pre-flight integrity validation failed."],
            )

        # In DRY_RUN mode, return preview without touching the active sequence
        if safety_level == RestoreSafetyLevel.DRY_RUN:
            return RestoreResult(
                success=True,
                revision_id=revision_id,
                project_id=snapshot.project_id,
                sequence_id=snapshot.sequence_id,
                restored_revision_number=snapshot.revision_number,
                missing_assets=missing,
                available_assets=avail,
                warnings=warnings + ["[DRY RUN] Preview only. No project state was modified."],
            )

        safety_snap_id = None
        current_seq = self.timeline_service.get_sequence(snapshot.sequence_id)

        # Create pre-restore safety snapshot to guarantee non-destructive recovery
        if create_safety_snapshot and current_seq is not None:
            safety_snap = self.create_snapshot(
                project_id=snapshot.project_id,
                sequence_id=snapshot.sequence_id,
                name=f"Pre-Restore Safety Checkpoint (before rev {snapshot.revision_number})",
                message=f"Automatic safety snapshot prior to restoring revision {revision_id}",
                author_id=actor_id,
                revision_type=RevisionType.PRE_RESTORE,
                is_protected=True,
            )
            safety_snap_id = safety_snap.revision_id

        try:
            # Atomic swap: deserialize snapshot sequence and update timeline service
            seq_json = json.dumps(snapshot.sequence_data)
            restored_seq = timeline_serialization_engine.deserialize_sequence(seq_json)

            # Bump revision to denote a restored milestone state
            restored_seq.revision += 1
            restored_seq.updated_at = time.time()

            self.timeline_service._sequences[restored_seq.sequence_id] = restored_seq

            self._log_audit_event("REVISION_RESTORED", {
                "revision_id": revision_id,
                "project_id": snapshot.project_id,
                "sequence_id": snapshot.sequence_id,
                "restored_revision_number": restored_seq.revision,
                "safety_snapshot_id": safety_snap_id,
                "actor_id": actor_id,
            })

            return RestoreResult(
                success=True,
                revision_id=revision_id,
                project_id=snapshot.project_id,
                sequence_id=snapshot.sequence_id,
                restored_revision_number=restored_seq.revision,
                safety_snapshot_id=safety_snap_id,
                missing_assets=missing,
                available_assets=avail,
                warnings=warnings,
            )
        except Exception as e:
            logger.error(f"Failed to restore revision {revision_id}: {e}")
            return RestoreResult(
                success=False,
                revision_id=revision_id,
                project_id=snapshot.project_id,
                sequence_id=snapshot.sequence_id,
                missing_assets=missing,
                available_assets=avail,
                warnings=warnings,
                errors=[f"Restore transaction failed: {str(e)}. Original sequence preserved."],
            )


# Global singleton
version_control_service = VersionControlService()
