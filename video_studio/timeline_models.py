"""OMNIA Video Studio — Sequence & Timeline Domain Models (Module 4).

Establishes the canonical non-destructive sequence and timeline representation:
- Explicit separation of Source Media Time and Sequence Timeline Time
- Precise integer frames, RationalTime durations, and SMPTE Timecode
- Sequences, Sequence Settings, and Schema Versioning ("video-studio.timeline.v1")
- Multi-type Tracks (VIDEO, AUDIO, SUBTITLE, CAPTION, ADJUSTMENT, OVERLAY, EFFECT, CONTROL)
- Timeline Items (MEDIA_CLIP, NESTED_SEQUENCE, ADJUSTMENT_LAYER, GENERATED_GRAPHIC, GAP)
- Explicit SourceRange and TimelineRange with intersection/containment logic
- Linked Media, Sync Groups, Markers, and Regions
- Concurrency revisions and optimistic locking foundations
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set, Tuple
import time
import uuid

from video_studio.media_models import RationalTime, SMPTETimecode

TIMELINE_SCHEMA_VERSION = "video-studio.timeline.v1"

# ==============================================================================
# 1. Core Timeline Enums
# ==============================================================================

class TimelineTrackType(str, Enum):
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    SUBTITLE = "SUBTITLE"
    CAPTION = "CAPTION"
    ADJUSTMENT = "ADJUSTMENT"
    OVERLAY = "OVERLAY"
    EFFECT = "EFFECT"
    CONTROL = "CONTROL"

class TimelineItemType(str, Enum):
    MEDIA_CLIP = "MEDIA_CLIP"
    NESTED_SEQUENCE = "NESTED_SEQUENCE"
    ADJUSTMENT_LAYER = "ADJUSTMENT_LAYER"
    GENERATED_GRAPHIC = "GENERATED_GRAPHIC"
    GAP = "GAP"

class TimelineItemState(str, Enum):
    READY = "READY"
    OFFLINE = "OFFLINE"
    MISSING = "MISSING"
    INVALID = "INVALID"
    DISABLED = "DISABLED"

class MarkerCategory(str, Enum):
    GENERAL = "GENERAL"
    EDIT = "EDIT"
    BEAT = "BEAT"
    CHAPTER = "CHAPTER"
    WARNING = "WARNING"
    TODO = "TODO"
    SYNC = "SYNC"
    NOTE = "NOTE"

class RegionCategory(str, Enum):
    SELECTION = "SELECTION"
    CHAPTER = "CHAPTER"
    EXPORT_RANGE = "EXPORT_RANGE"
    REVIEW = "REVIEW"
    ANALYSIS = "ANALYSIS"

# ==============================================================================
# 2. Precise Range Abstractions (SourceRange & TimelineRange)
# ==============================================================================

@dataclass
class SourceRange:
    """Represents a non-destructive slice of the original source media."""
    in_frame: int = 0
    duration_frames: int = 24

    @property
    def out_frame(self) -> int:
        return self.in_frame + self.duration_frames

    def validate(self) -> Tuple[bool, str]:
        if self.in_frame < 0:
            return False, f"Source in_frame cannot be negative: {self.in_frame}"
        if self.duration_frames <= 0:
            return False, f"Source duration_frames must be positive: {self.duration_frames}"
        return True, "Valid"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "in_frame": self.in_frame,
            "out_frame": self.out_frame,
            "duration_frames": self.duration_frames,
        }

@dataclass
class TimelineRange:
    """Represents the placement of an item on the sequence timeline."""
    start_frame: int = 0
    duration_frames: int = 24

    @property
    def end_frame(self) -> int:
        return self.start_frame + self.duration_frames

    def contains_frame(self, frame: int) -> bool:
        return self.start_frame <= frame < self.end_frame

    def overlaps_with(self, other: "TimelineRange") -> bool:
        return not (self.end_frame <= other.start_frame or self.start_frame >= other.end_frame)

    def intersects(self, start: int, end: int) -> bool:
        return not (self.end_frame <= start or self.start_frame >= end)

    def validate(self) -> Tuple[bool, str]:
        if self.start_frame < 0:
            return False, f"Timeline start_frame cannot be negative: {self.start_frame}"
        if self.duration_frames <= 0:
            return False, f"Timeline duration_frames must be positive: {self.duration_frames}"
        return True, "Valid"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "duration_frames": self.duration_frames,
        }

# ==============================================================================
# 3. Sequence Settings Model
# ==============================================================================

@dataclass
class SequenceSettings:
    """Authoritative technical configuration for a video sequence."""
    width: int = 1920
    height: int = 1080
    frame_rate: float = 24.0
    timebase_numerator: int = 1
    timebase_denominator: int = 24
    pixel_aspect_ratio: str = "1:1"
    color_space: str = "Rec.709"
    transfer_characteristics: str = "bt709"
    audio_sample_rate: int = 48000
    audio_channels: int = 2
    audio_channel_layout: str = "stereo"
    start_timecode: str = "00:00:00:00"
    is_drop_frame: bool = False
    display_timecode_format: str = "SMPTE_NDF"
    proxy_policy: str = "PREFER_ORIGINAL"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "frame_rate": self.frame_rate,
            "timebase": f"{self.timebase_numerator}/{self.timebase_denominator}",
            "pixel_aspect_ratio": self.pixel_aspect_ratio,
            "color_space": self.color_space,
            "transfer_characteristics": self.transfer_characteristics,
            "audio_sample_rate": self.audio_sample_rate,
            "audio_channels": self.audio_channels,
            "audio_channel_layout": self.audio_channel_layout,
            "start_timecode": self.start_timecode,
            "is_drop_frame": self.is_drop_frame,
            "display_timecode_format": self.display_timecode_format,
            "proxy_policy": self.proxy_policy,
        }

# ==============================================================================
# 4. Markers & Regions
# ==============================================================================

@dataclass
class TimelineMarker:
    marker_id: str
    sequence_id: str
    frame: int
    duration_frames: int = 0  # 0 for cue point, >0 for spanning marker
    name: str = "Marker"
    comment: str = ""
    category: MarkerCategory = MarkerCategory.GENERAL
    color_hex: str = "#00f0ff"
    creator: str = "user"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "marker_id": self.marker_id,
            "sequence_id": self.sequence_id,
            "frame": self.frame,
            "duration_frames": self.duration_frames,
            "name": self.name,
            "comment": self.comment,
            "category": self.category.value,
            "color_hex": self.color_hex,
            "creator": self.creator,
            "metadata": self.metadata,
        }

@dataclass
class TimelineRegion:
    region_id: str
    sequence_id: str
    start_frame: int
    end_frame: int
    name: str = "Region"
    description: str = ""
    category: RegionCategory = RegionCategory.SELECTION
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_frames(self) -> int:
        return max(0, self.end_frame - self.start_frame)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "region_id": self.region_id,
            "sequence_id": self.sequence_id,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "duration_frames": self.duration_frames,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "metadata": self.metadata,
        }

# ==============================================================================
# 5. Timeline Item (Non-Destructive Media Placement)
# ==============================================================================

@dataclass
class TimelineItemModel:
    """Canonical model for an individual item placed on a track."""
    item_id: str
    track_id: str
    sequence_id: str
    source_reference_id: str  # Asset ID, or Sequence ID if nested
    name: str = "Clip"
    item_type: TimelineItemType = TimelineItemType.MEDIA_CLIP
    state: TimelineItemState = TimelineItemState.READY
    timeline_range: TimelineRange = field(default_factory=TimelineRange)
    source_range: SourceRange = field(default_factory=SourceRange)
    speed: float = 1.0
    is_enabled: bool = True
    link_group_id: Optional[str] = None
    sync_group_id: Optional[str] = None
    effects: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    revision: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "track_id": self.track_id,
            "sequence_id": self.sequence_id,
            "source_reference_id": self.source_reference_id,
            "name": self.name,
            "item_type": self.item_type.value,
            "state": self.state.value,
            "timeline_range": self.timeline_range.to_dict(),
            "source_range": self.source_range.to_dict(),
            "speed": self.speed,
            "is_enabled": self.is_enabled,
            "link_group_id": self.link_group_id,
            "sync_group_id": self.sync_group_id,
            "effects_count": len(self.effects),
            "revision": self.revision,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

# ==============================================================================
# 6. Timeline Track Model
# ==============================================================================

@dataclass
class TimelineTrackModel:
    """Canonical model for a track holding timeline items."""
    track_id: str
    sequence_id: str
    name: str
    track_type: TimelineTrackType
    index: int = 0
    is_enabled: bool = True
    is_locked: bool = False
    is_muted: bool = False
    is_solo: bool = False
    is_visible: bool = True
    is_armed: bool = False
    sync_locked: bool = True
    items: List[TimelineItemModel] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "track_id": self.track_id,
            "sequence_id": self.sequence_id,
            "name": self.name,
            "track_type": self.track_type.value,
            "index": self.index,
            "is_enabled": self.is_enabled,
            "is_locked": self.is_locked,
            "is_muted": self.is_muted,
            "is_solo": self.is_solo,
            "is_visible": self.is_visible,
            "is_armed": self.is_armed,
            "sync_locked": self.sync_locked,
            "items_count": len(self.items),
            "items": [it.to_dict() for it in self.items],
        }

# ==============================================================================
# 7. Link Groups & Sync Groups
# ==============================================================================

@dataclass
class LinkGroup:
    """Binds video and audio items together so edits affect both synchronously."""
    link_group_id: str
    sequence_id: str
    item_ids: Set[str] = field(default_factory=set)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "link_group_id": self.link_group_id,
            "sequence_id": self.sequence_id,
            "item_ids": list(self.item_ids),
        }

@dataclass
class SyncGroup:
    """Synchronizes multiple items or cameras across tracks."""
    sync_group_id: str
    sequence_id: str
    name: str = "Sync Group"
    item_ids: Set[str] = field(default_factory=set)
    sync_point_frame: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sync_group_id": self.sync_group_id,
            "sequence_id": self.sequence_id,
            "name": self.name,
            "item_ids": list(self.item_ids),
            "sync_point_frame": self.sync_point_frame,
        }

# ==============================================================================
# 8. Canonical Sequence Model
# ==============================================================================

@dataclass
class VideoSequence:
    """Authoritative non-destructive sequence model."""
    sequence_id: str
    project_id: str
    name: str
    description: str = ""
    settings: SequenceSettings = field(default_factory=SequenceSettings)
    tracks: List[TimelineTrackModel] = field(default_factory=list)
    markers: List[TimelineMarker] = field(default_factory=list)
    regions: List[TimelineRegion] = field(default_factory=list)
    link_groups: Dict[str, LinkGroup] = field(default_factory=dict)
    sync_groups: Dict[str, SyncGroup] = field(default_factory=dict)
    duration_frames: int = 0
    revision: int = 1
    schema_version: str = TIMELINE_SCHEMA_VERSION
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def calculate_duration_frames(self) -> int:
        """Calculates total sequence duration across all tracks and items."""
        max_frame = 0
        for track in self.tracks:
            for item in track.items:
                if item.timeline_range.end_frame > max_frame:
                    max_frame = item.timeline_range.end_frame
        self.duration_frames = max_frame
        return max_frame

    def get_linked_items(self, item_id: str) -> List[str]:
        """Returns list of all item IDs linked to item_id."""
        for lg in self.link_groups.values():
            if item_id in lg.item_ids:
                return list(lg.item_ids)
        return []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sequence_id": self.sequence_id,
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "settings": self.settings.to_dict(),
            "tracks": [t.to_dict() for t in self.tracks],
            "markers": [m.to_dict() for m in self.markers],
            "regions": [r.to_dict() for r in self.regions],
            "link_groups": {k: v.to_dict() for k, v in self.link_groups.items()},
            "sync_groups": {k: v.to_dict() for k, v in self.sync_groups.items()},
            "duration_frames": self.duration_frames,
            "revision": self.revision,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
