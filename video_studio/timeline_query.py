"""OMNIA Video Studio — Timeline Indexing & Query Engine (Module 4).

Provides fast point and interval lookups without O(N) full-sequence scans:
- get_items_at_time(frame)
- get_items_in_range(start_frame, end_frame)
- get_items_intersecting_range(start_frame, end_frame)
- get_markers_at_time(frame)
- get_markers_in_range(start_frame, end_frame)
- get_regions_in_range(start_frame, end_frame)
- get_linked_items(item_id)
- get_sync_group(sync_group_id)
- get_nested_sequences(sequence_id)
Maintains interval buckets for timeline scalability over thousands of placed clips.
"""

from typing import Dict, Any, List, Optional, Set
import bisect
import logging

from video_studio.timeline_models import (
    VideoSequence,
    TimelineTrackModel,
    TimelineItemModel,
    TimelineMarker,
    TimelineRegion,
    TimelineItemType,
)

logger = logging.getLogger("Omnia.VideoStudio.Query")

class TimelineSpatialIndex:
    """Interval index for a single sequence, bucketed into frame chunks."""

    def __init__(self, bucket_size_frames: int = 240):  # 10 second chunks at 24fps
        self.bucket_size = bucket_size_frames
        self._buckets: Dict[int, List[TimelineItemModel]] = {}
        self._item_by_id: Dict[str, TimelineItemModel] = {}
        self._items_by_track: Dict[str, List[TimelineItemModel]] = {}

    def build_index(self, sequence: VideoSequence) -> None:
        """Rebuilds the spatial index from scratch."""
        self._buckets.clear()
        self._item_by_id.clear()
        self._items_by_track.clear()

        for track in sequence.tracks:
            self._items_by_track[track.track_id] = []
            for item in track.items:
                self.index_item(item)

    def index_item(self, item: TimelineItemModel) -> None:
        """Indexes an individual item into appropriate frame interval buckets."""
        self._item_by_id[item.item_id] = item
        if item.track_id not in self._items_by_track:
            self._items_by_track[item.track_id] = []
        self._items_by_track[item.track_id].append(item)

        start_bucket = item.timeline_range.start_frame // self.bucket_size
        end_bucket = item.timeline_range.end_frame // self.bucket_size

        for b in range(start_bucket, end_bucket + 1):
            if b not in self._buckets:
                self._buckets[b] = []
            if item not in self._buckets[b]:
                self._buckets[b].append(item)

    def get_candidate_items(self, start_frame: int, end_frame: int) -> List[TimelineItemModel]:
        """Finds candidate items that might overlap [start_frame, end_frame]."""
        start_b = max(0, start_frame // self.bucket_size)
        end_b = max(0, end_frame // self.bucket_size)

        candidates: Dict[str, TimelineItemModel] = {}
        for b in range(start_b, end_b + 1):
            if b in self._buckets:
                for item in self._buckets[b]:
                    candidates[item.item_id] = item
        return list(candidates.values())

class TimelineQueryEngine:
    """Query service executing fast point, range, and relationship queries."""

    def __init__(self):
        self._indices: Dict[str, TimelineSpatialIndex] = {}

    def get_or_build_index(self, sequence: VideoSequence) -> TimelineSpatialIndex:
        if sequence.sequence_id not in self._indices:
            idx = TimelineSpatialIndex()
            idx.build_index(sequence)
            self._indices[sequence.sequence_id] = idx
        return self._indices[sequence.sequence_id]

    def invalidate_index(self, sequence_id: str) -> None:
        if sequence_id in self._indices:
            del self._indices[sequence_id]

    def get_items_at_time(self, sequence: VideoSequence, frame: int) -> List[TimelineItemModel]:
        """Returns all items active at a specific playhead frame position."""
        idx = self.get_or_build_index(sequence)
        candidates = idx.get_candidate_items(frame, frame + 1)
        return [it for it in candidates if it.timeline_range.contains_frame(frame)]

    def get_items_in_range(self, sequence: VideoSequence, start_frame: int, end_frame: int) -> List[TimelineItemModel]:
        """Returns items strictly contained within [start_frame, end_frame]."""
        idx = self.get_or_build_index(sequence)
        candidates = idx.get_candidate_items(start_frame, end_frame)
        return [
            it for it in candidates
            if it.timeline_range.start_frame >= start_frame and it.timeline_range.end_frame <= end_frame
        ]

    def get_items_intersecting_range(self, sequence: VideoSequence, start_frame: int, end_frame: int) -> List[TimelineItemModel]:
        """Returns items that overlap or intersect [start_frame, end_frame]."""
        idx = self.get_or_build_index(sequence)
        candidates = idx.get_candidate_items(start_frame, end_frame)
        return [it for it in candidates if it.timeline_range.intersects(start_frame, end_frame)]

    def get_markers_at_time(self, sequence: VideoSequence, frame: int) -> List[TimelineMarker]:
        return [m for m in sequence.markers if m.frame <= frame <= (m.frame + m.duration_frames)]

    def get_markers_in_range(self, sequence: VideoSequence, start_frame: int, end_frame: int) -> List[TimelineMarker]:
        return [m for m in sequence.markers if start_frame <= m.frame <= end_frame]

    def get_regions_in_range(self, sequence: VideoSequence, start_frame: int, end_frame: int) -> List[TimelineRegion]:
        return [
            r for r in sequence.regions
            if not (r.end_frame <= start_frame or r.start_frame >= end_frame)
        ]

    def get_linked_items(self, sequence: VideoSequence, item_id: str) -> List[TimelineItemModel]:
        """Finds items bound via LinkGroup to the requested item."""
        target_group = None
        for lg in sequence.link_groups.values():
            if item_id in lg.item_ids:
                target_group = lg
                break

        if not target_group:
            return []

        idx = self.get_or_build_index(sequence)
        res = []
        for other_id in target_group.item_ids:
            if other_id != item_id and other_id in idx._item_by_id:
                res.append(idx._item_by_id[other_id])
        return res

    def get_sync_group_items(self, sequence: VideoSequence, sync_group_id: str) -> List[TimelineItemModel]:
        sg = sequence.sync_groups.get(sync_group_id)
        if not sg:
            return []
        idx = self.get_or_build_index(sequence)
        return [idx._item_by_id[i_id] for i_id in sg.item_ids if i_id in idx._item_by_id]

    def get_nested_sequences(self, sequence: VideoSequence) -> List[TimelineItemModel]:
        """Returns all items in this sequence that reference another sequence."""
        res = []
        for track in sequence.tracks:
            for item in track.items:
                if item.item_type == TimelineItemType.NESTED_SEQUENCE:
                    res.append(item)
        return res

# Global singleton
timeline_query_engine = TimelineQueryEngine()
