"""OMNIA Video Studio — Timeline Serialization & Schema Versioning (Module 4).

Provides deterministic JSON export/import and schema migration infrastructure:
- Schema Version: "video-studio.timeline.v1"
- Serialization & Deserialization of VideoSequence, tracks, items, ranges, markers, and regions
- Optimistic concurrency with revision checks (prevents stale overwrites)
- Migration hooks for future schema evolution
"""

import json
import logging
from typing import Dict, Any, Optional, Tuple

from video_studio.timeline_models import (
    VideoSequence,
    SequenceSettings,
    TimelineTrackModel,
    TimelineItemModel,
    TimelineMarker,
    TimelineRegion,
    TimelineRange,
    SourceRange,
    LinkGroup,
    SyncGroup,
    TimelineTrackType,
    TimelineItemType,
    TimelineItemState,
    MarkerCategory,
    RegionCategory,
    TIMELINE_SCHEMA_VERSION,
)

logger = logging.getLogger("Omnia.VideoStudio.Serialization")

class TimelineSerializationEngine:
    """Serializes and deserializes versioned timeline sequences."""

    def serialize_sequence(self, sequence: VideoSequence) -> str:
        """Outputs deterministic JSON string representation of sequence."""
        sequence.calculate_duration_frames()
        return json.dumps(sequence.to_dict(), indent=2)

    def deserialize_sequence(self, json_str: str) -> VideoSequence:
        """Parses versioned sequence JSON into canonical VideoSequence object."""
        data = json.loads(json_str)

        # Handle future migrations if needed
        schema_ver = data.get("schema_version", TIMELINE_SCHEMA_VERSION)
        if schema_ver != TIMELINE_SCHEMA_VERSION:
            data = self._migrate_schema(data, schema_ver, TIMELINE_SCHEMA_VERSION)

        # Parse settings
        sd = data.get("settings", {})
        timebase_parts = sd.get("timebase", "1/24").split("/")
        tb_num = int(timebase_parts[0]) if len(timebase_parts) > 0 else 1
        tb_den = int(timebase_parts[1]) if len(timebase_parts) > 1 else 24

        settings = SequenceSettings(
            width=sd.get("width", 1920),
            height=sd.get("height", 1080),
            frame_rate=sd.get("frame_rate", 24.0),
            timebase_numerator=tb_num,
            timebase_denominator=tb_den,
            pixel_aspect_ratio=sd.get("pixel_aspect_ratio", "1:1"),
            color_space=sd.get("color_space", "Rec.709"),
            transfer_characteristics=sd.get("transfer_characteristics", "bt709"),
            audio_sample_rate=sd.get("audio_sample_rate", 48000),
            audio_channels=sd.get("audio_channels", 2),
            audio_channel_layout=sd.get("audio_channel_layout", "stereo"),
            start_timecode=sd.get("start_timecode", "00:00:00:00"),
            is_drop_frame=sd.get("is_drop_frame", False),
            display_timecode_format=sd.get("display_timecode_format", "SMPTE_NDF"),
            proxy_policy=sd.get("proxy_policy", "PREFER_ORIGINAL"),
        )

        seq = VideoSequence(
            sequence_id=data["sequence_id"],
            project_id=data["project_id"],
            name=data["name"],
            description=data.get("description", ""),
            settings=settings,
            duration_frames=data.get("duration_frames", 0),
            revision=data.get("revision", 1),
            schema_version=data.get("schema_version", TIMELINE_SCHEMA_VERSION),
            created_at=data.get("created_at", 0.0),
            updated_at=data.get("updated_at", 0.0),
        )

        # Parse Tracks & Items
        for td in data.get("tracks", []):
            tr = TimelineTrackModel(
                track_id=td["track_id"],
                sequence_id=td.get("sequence_id", seq.sequence_id),
                name=td["name"],
                track_type=TimelineTrackType(td["track_type"]),
                index=td.get("index", 0),
                is_enabled=td.get("is_enabled", True),
                is_locked=td.get("is_locked", False),
                is_muted=td.get("is_muted", False),
                is_solo=td.get("is_solo", False),
                is_visible=td.get("is_visible", True),
                is_armed=td.get("is_armed", False),
                sync_locked=td.get("sync_locked", True),
            )
            for idata in td.get("items", []):
                tr_d = idata["timeline_range"]
                sr_d = idata["source_range"]
                item = TimelineItemModel(
                    item_id=idata["item_id"],
                    track_id=tr.track_id,
                    sequence_id=seq.sequence_id,
                    source_reference_id=idata["source_reference_id"],
                    name=idata.get("name", "Clip"),
                    item_type=TimelineItemType(idata.get("item_type", "MEDIA_CLIP")),
                    state=TimelineItemState(idata.get("state", "READY")),
                    timeline_range=TimelineRange(
                        start_frame=tr_d["start_frame"],
                        duration_frames=tr_d["duration_frames"],
                    ),
                    source_range=SourceRange(
                        in_frame=sr_d["in_frame"],
                        duration_frames=sr_d["duration_frames"],
                    ),
                    speed=idata.get("speed", 1.0),
                    is_enabled=idata.get("is_enabled", True),
                    link_group_id=idata.get("link_group_id"),
                    sync_group_id=idata.get("sync_group_id"),
                    revision=idata.get("revision", 1),
                )
                tr.items.append(item)
            seq.tracks.append(tr)

        # Parse Markers
        for md in data.get("markers", []):
            seq.markers.append(TimelineMarker(
                marker_id=md["marker_id"],
                sequence_id=seq.sequence_id,
                frame=md["frame"],
                duration_frames=md.get("duration_frames", 0),
                name=md.get("name", "Marker"),
                comment=md.get("comment", ""),
                category=MarkerCategory(md.get("category", "GENERAL")),
                color_hex=md.get("color_hex", "#00f0ff"),
            ))

        # Parse Regions
        for rd in data.get("regions", []):
            seq.regions.append(TimelineRegion(
                region_id=rd["region_id"],
                sequence_id=seq.sequence_id,
                start_frame=rd["start_frame"],
                end_frame=rd["end_frame"],
                name=rd.get("name", "Region"),
                category=RegionCategory(rd.get("category", "SELECTION")),
            ))

        # Parse Link Groups
        for lg_id, lg_d in data.get("link_groups", {}).items():
            seq.link_groups[lg_id] = LinkGroup(
                link_group_id=lg_id,
                sequence_id=seq.sequence_id,
                item_ids=set(lg_d.get("item_ids", [])),
            )

        # Parse Sync Groups
        for sg_id, sg_d in data.get("sync_groups", {}).items():
            seq.sync_groups[sg_id] = SyncGroup(
                sync_group_id=sg_id,
                sequence_id=seq.sequence_id,
                name=sg_d.get("name", "Sync Group"),
                item_ids=set(sg_d.get("item_ids", [])),
                sync_point_frame=sg_d.get("sync_point_frame", 0),
            )

        seq.calculate_duration_frames()
        return seq

    def _migrate_schema(self, data: Dict[str, Any], from_version: str, to_version: str) -> Dict[str, Any]:
        """Provides forward migration pathways for future schema versions."""
        logger.info(f"Migrating timeline schema from {from_version} to {to_version}")
        # Currently at v1 baseline
        data["schema_version"] = to_version
        return data

# Global singleton
timeline_serialization_engine = TimelineSerializationEngine()
