"""OMNIA Video Studio — Module 41: Versioning & Revision Comparison Engine.

Algorithmic core for:
- Deterministic canonical hashing of sequence states (SHA-256 integrity fingerprint).
- Fine-grained structural diff calculation between two revisions (tracks, clips, settings, duration).
- Asset dependency extraction from serialized sequence data.
- Integrity verification of snapshots against corrupted or tampered payloads.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, List, Optional, Set, Tuple

from video_studio.versioning_models import (
    RevisionDiff,
    RevisionSnapshot,
    StructuralDiffItem,
)
from video_studio.timeline_models import VideoSequence
from video_studio.timeline_serialization import timeline_serialization_engine


def canonical_json_dump(data: Any) -> str:
    """Produces deterministic, sorted-key JSON string for content fingerprinting."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


class VersioningEngine:
    """Core domain logic for timeline snapshots, checksum verification, and structural comparisons."""

    @staticmethod
    def extract_referenced_asset_ids(sequence_data: Dict[str, Any]) -> List[str]:
        """Scans all tracks and items in a sequence payload to collect referenced media asset IDs."""
        asset_ids: Set[str] = set()
        tracks = sequence_data.get("tracks", [])
        for track in tracks:
            for item in track.get("items", []):
                ref_id = item.get("source_reference_id")
                if ref_id and isinstance(ref_id, str):
                    asset_ids.add(ref_id)
        return sorted(list(asset_ids))

    @staticmethod
    def compute_sequence_fingerprint(sequence_data: Dict[str, Any]) -> str:
        """Calculates deterministic SHA-256 integrity hash from canonical sequence state."""
        # Strip volatile fields (like updated_at) to ensure structural determinism
        clean_data = copy.deepcopy(sequence_data)
        clean_data.pop("updated_at", None)
        payload = canonical_json_dump(clean_data).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def verify_snapshot_integrity(snapshot: RevisionSnapshot) -> Tuple[bool, Optional[str]]:
        """Verifies if snapshot data matches its stored cryptographic fingerprint."""
        if not snapshot.content_fingerprint_sha256:
            return False, "Snapshot has no content fingerprint."

        recomputed = VersioningEngine.compute_sequence_fingerprint(snapshot.sequence_data)
        if recomputed != snapshot.content_fingerprint_sha256:
            return False, f"Fingerprint mismatch! Expected {snapshot.content_fingerprint_sha256}, got {recomputed}."

        return True, None

    @staticmethod
    def compare_revisions(source: RevisionSnapshot, target: RevisionSnapshot) -> RevisionDiff:
        """Computes a structural diff comparing tracks, clips, settings, and duration between source and target."""
        diff = RevisionDiff(
            source_revision_id=source.revision_id,
            target_revision_id=target.revision_id,
            source_revision_number=source.revision_number,
            target_revision_number=target.revision_number,
        )

        s_data = source.sequence_data
        t_data = target.sequence_data

        # 1. Compare duration
        s_dur = s_data.get("duration_frames", 0)
        t_dur = t_data.get("duration_frames", 0)
        diff.duration_delta_frames = t_dur - s_dur

        # 2. Compare Settings
        s_settings = s_data.get("settings", {})
        t_settings = t_data.get("settings", {})
        all_keys = set(s_settings.keys()).union(set(t_settings.keys()))
        for k in all_keys:
            if s_settings.get(k) != t_settings.get(k):
                diff.settings_changed[k] = {
                    "source": s_settings.get(k),
                    "target": t_settings.get(k),
                }
                diff.structural_changes.append(
                    StructuralDiffItem(
                        entity_type="setting",
                        entity_id=k,
                        change_type="MODIFIED",
                        summary=f"Setting '{k}' changed from {s_settings.get(k)} to {t_settings.get(k)}.",
                        details={"from": s_settings.get(k), "to": t_settings.get(k)},
                    )
                )

        # 3. Compare Tracks
        s_tracks = {t.get("track_id"): t for t in s_data.get("tracks", [])}
        t_tracks = {t.get("track_id"): t for t in t_data.get("tracks", [])}

        for tid, t_obj in t_tracks.items():
            if tid not in s_tracks:
                diff.tracks_added.append(tid)
                diff.structural_changes.append(
                    StructuralDiffItem(
                        entity_type="track",
                        entity_id=tid,
                        change_type="ADDED",
                        summary=f"Track '{t_obj.get('name', tid)}' ({t_obj.get('track_type')}) was added.",
                    )
                )

        for sid, s_obj in s_tracks.items():
            if sid not in t_tracks:
                diff.tracks_removed.append(sid)
                diff.structural_changes.append(
                    StructuralDiffItem(
                        entity_type="track",
                        entity_id=sid,
                        change_type="REMOVED",
                        summary=f"Track '{s_obj.get('name', sid)}' was removed.",
                    )
                )

        # 4. Compare Clips across tracks
        s_clips: Dict[str, Dict[str, Any]] = {}
        for trk in s_tracks.values():
            for item in trk.get("items", []):
                s_clips[item.get("item_id")] = item

        t_clips: Dict[str, Dict[str, Any]] = {}
        for trk in t_tracks.values():
            for item in trk.get("items", []):
                t_clips[item.get("item_id")] = item

        for cid, c_obj in t_clips.items():
            if cid not in s_clips:
                diff.clips_added.append(cid)
                diff.structural_changes.append(
                    StructuralDiffItem(
                        entity_type="clip",
                        entity_id=cid,
                        change_type="ADDED",
                        summary=f"Clip '{c_obj.get('name', cid)}' added to track '{c_obj.get('track_id')}'.",
                        details={"timeline_range": c_obj.get("timeline_range")},
                    )
                )
            else:
                # Compare timing and speed
                s_clip = s_clips[cid]
                timing_changed = s_clip.get("timeline_range") != c_obj.get("timeline_range")
                speed_changed = s_clip.get("speed") != c_obj.get("speed")
                if timing_changed or speed_changed:
                    diff.clips_modified.append(cid)
                    diff.structural_changes.append(
                        StructuralDiffItem(
                            entity_type="clip",
                            entity_id=cid,
                            change_type="MODIFIED",
                            summary=f"Clip '{c_obj.get('name', cid)}' timing or speed modified.",
                            details={
                                "from_range": s_clip.get("timeline_range"),
                                "to_range": c_obj.get("timeline_range"),
                                "from_speed": s_clip.get("speed"),
                                "to_speed": c_obj.get("speed"),
                            },
                        )
                    )

        for cid, c_obj in s_clips.items():
            if cid not in t_clips:
                diff.clips_removed.append(cid)
                diff.structural_changes.append(
                    StructuralDiffItem(
                        entity_type="clip",
                        entity_id=cid,
                        change_type="REMOVED",
                        summary=f"Clip '{c_obj.get('name', cid)}' was deleted.",
                    )
                )

        diff.is_identical = (
            len(diff.tracks_added) == 0
            and len(diff.tracks_removed) == 0
            and len(diff.clips_added) == 0
            and len(diff.clips_removed) == 0
            and len(diff.clips_modified) == 0
            and len(diff.settings_changed) == 0
            and diff.duration_delta_frames == 0
        )
        return diff
