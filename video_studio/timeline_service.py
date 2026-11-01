"""OMNIA Video Studio — Sequence & Timeline Service (Module 4).

Central service managing project sequences, tracks, non-destructive clip placements,
transaction execution, history stacks, and optimistic concurrency.
"""

import time
import uuid
import logging
from typing import Dict, Any, List, Optional, Tuple

from video_studio.timeline_models import (
    VideoSequence,
    SequenceSettings,
    TimelineTrackModel,
    TimelineItemModel,
    TimelineMarker,
    TimelineRegion,
    TimelineRange,
    SourceRange,
    TimelineTrackType,
    TimelineItemType,
    TimelineItemState,
    MarkerCategory,
    RegionCategory,
    LinkGroup,
    SyncGroup,
)
from video_studio.timeline_validation import timeline_validation_engine, TimelineValidationError
from video_studio.timeline_query import timeline_query_engine
from video_studio.timeline_commands import (
    TimelineCommand,
    TimelineTransaction,
    TimelineHistoryManager,
    TimelineOpType,
)
from video_studio.timeline_serialization import timeline_serialization_engine

logger = logging.getLogger("Omnia.VideoStudio.TimelineService")

class TimelineService:
    """Manages active sequences, transactions, and editing history across projects."""

    def __init__(self):
        self._sequences: Dict[str, VideoSequence] = {}
        self._history_managers: Dict[str, TimelineHistoryManager] = {}

    def create_sequence(
        self,
        project_id: str,
        name: str,
        settings: Optional[SequenceSettings] = None,
        create_default_tracks: bool = True,
    ) -> VideoSequence:
        """Creates a new canonical sequence in a project."""
        seq_id = f"seq_{uuid.uuid4().hex[:10]}"
        seq = VideoSequence(
            sequence_id=seq_id,
            project_id=project_id,
            name=name.strip() or "Untitled Sequence",
            settings=settings or SequenceSettings(),
        )

        if create_default_tracks:
            # Standard video and audio tracks
            v1 = TimelineTrackModel(
                track_id=f"track_v1_{uuid.uuid4().hex[:6]}",
                sequence_id=seq_id,
                name="V1",
                track_type=TimelineTrackType.VIDEO,
                index=0,
            )
            v2 = TimelineTrackModel(
                track_id=f"track_v2_{uuid.uuid4().hex[:6]}",
                sequence_id=seq_id,
                name="V2",
                track_type=TimelineTrackType.VIDEO,
                index=1,
            )
            a1 = TimelineTrackModel(
                track_id=f"track_a1_{uuid.uuid4().hex[:6]}",
                sequence_id=seq_id,
                name="A1",
                track_type=TimelineTrackType.AUDIO,
                index=2,
            )
            a2 = TimelineTrackModel(
                track_id=f"track_a2_{uuid.uuid4().hex[:6]}",
                sequence_id=seq_id,
                name="A2",
                track_type=TimelineTrackType.AUDIO,
                index=3,
            )
            seq.tracks.extend([v1, v2, a1, a2])

        self._sequences[seq_id] = seq
        self._history_managers[seq_id] = TimelineHistoryManager(seq)
        return seq

    def get_sequence(self, sequence_id: str) -> Optional[VideoSequence]:
        return self._sequences.get(sequence_id)

    def list_sequences(self, project_id: Optional[str] = None) -> List[VideoSequence]:
        if project_id:
            return [s for s in self._sequences.values() if s.project_id == project_id]
        return list(self._sequences.values())

    def delete_sequence(self, sequence_id: str) -> bool:
        if sequence_id in self._sequences:
            del self._sequences[sequence_id]
            if sequence_id in self._history_managers:
                del self._history_managers[sequence_id]
            timeline_query_engine.invalidate_index(sequence_id)
            return True
        return False

    def add_track(
        self,
        sequence_id: str,
        name: str,
        track_type: TimelineTrackType = TimelineTrackType.VIDEO,
    ) -> Optional[TimelineTrackModel]:
        """Appends a new track to the sequence."""
        seq = self.get_sequence(sequence_id)
        if not seq:
            return None

        track_id = f"track_{uuid.uuid4().hex[:8]}"
        track = TimelineTrackModel(
            track_id=track_id,
            sequence_id=sequence_id,
            name=name,
            track_type=track_type,
            index=len(seq.tracks),
        )
        seq.tracks.append(track)
        seq.revision += 1
        seq.updated_at = time.time()
        timeline_query_engine.invalidate_index(sequence_id)
        return track

    def add_clip(
        self,
        sequence_id: str,
        track_id: str,
        asset_id: str,
        name: str = "Clip",
        start_frame: int = 0,
        duration_frames: int = 24,
        source_in_frame: int = 0,
        speed: float = 1.0,
    ) -> Optional[TimelineItemModel]:
        """Places a non-destructive media clip on a track."""
        seq = self.get_sequence(sequence_id)
        if not seq:
            return None

        track = next((t for t in seq.tracks if t.track_id == track_id), None)
        if not track or track.is_locked:
            return None

        item_id = f"clip_{uuid.uuid4().hex[:10]}"
        item = TimelineItemModel(
            item_id=item_id,
            track_id=track_id,
            sequence_id=sequence_id,
            source_reference_id=asset_id,
            name=name,
            item_type=TimelineItemType.MEDIA_CLIP,
            timeline_range=TimelineRange(start_frame=start_frame, duration_frames=duration_frames),
            source_range=SourceRange(in_frame=source_in_frame, duration_frames=duration_frames),
            speed=speed,
        )

        track.items.append(item)
        seq.calculate_duration_frames()
        seq.revision += 1
        seq.updated_at = time.time()
        timeline_query_engine.invalidate_index(sequence_id)
        return item

    def link_items(self, sequence_id: str, item_ids: List[str]) -> Optional[LinkGroup]:
        """Binds two or more timeline items together in a LinkGroup."""
        seq = self.get_sequence(sequence_id)
        if not seq or len(item_ids) < 2:
            return None

        lg_id = f"link_{uuid.uuid4().hex[:8]}"
        lg = LinkGroup(link_group_id=lg_id, sequence_id=sequence_id, item_ids=set(item_ids))
        seq.link_groups[lg_id] = lg

        # Update items
        for track in seq.tracks:
            for item in track.items:
                if item.item_id in lg.item_ids:
                    item.link_group_id = lg_id

        seq.revision += 1
        seq.updated_at = time.time()
        return lg

    def add_marker(
        self,
        sequence_id: str,
        frame: int,
        name: str = "Marker",
        category: MarkerCategory = MarkerCategory.GENERAL,
        color_hex: str = "#00f0ff",
    ) -> Optional[TimelineMarker]:
        seq = self.get_sequence(sequence_id)
        if not seq:
            return None

        m_id = f"marker_{uuid.uuid4().hex[:8]}"
        marker = TimelineMarker(
            marker_id=m_id,
            sequence_id=sequence_id,
            frame=frame,
            name=name,
            category=category,
            color_hex=color_hex,
        )
        seq.markers.append(marker)
        seq.revision += 1
        seq.updated_at = time.time()
        return marker

    def undo(self, sequence_id: str) -> bool:
        hm = self._history_managers.get(sequence_id)
        if not hm:
            return False
        ok = hm.undo()
        if ok:
            timeline_query_engine.invalidate_index(sequence_id)
        return ok

    def redo(self, sequence_id: str) -> bool:
        hm = self._history_managers.get(sequence_id)
        if not hm:
            return False
        ok = hm.redo()
        if ok:
            timeline_query_engine.invalidate_index(sequence_id)
        return ok

    def validate(self, sequence_id: str) -> Tuple[bool, List[str]]:
        seq = self.get_sequence(sequence_id)
        if not seq:
            return False, [f"Sequence {sequence_id} not found."]
        return timeline_validation_engine.validate_sequence(seq, self._sequences)

# Global singleton
timeline_service = TimelineService()
