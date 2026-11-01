"""OMNIA Video Studio — Speed & Time Remapping Service (Module 15).

Manages:
- TimeRemapDocuments lifecycle, persistence, and association with timeline items.
- Transactional speed adjustments with optional ripple timeline editing.
- Variable speed ramp curves, control point additions/removals.
- Freeze frame insertion and management.
- Capabilities registration and health reporting for Module 1.
"""

from typing import Dict, Any, List, Optional, Tuple
import logging
import uuid
import time

from video_studio.speed_models import (
    TimeRemapDocument,
    SpeedCurvePoint,
    FreezeRegion,
    FrameInterpolationMode,
    AudioSpeedMode,
    SpeedCurveInterpolation,
)
from video_studio.speed_engine import speed_remap_engine, SpeedRemapEngine
from video_studio.timeline_models import VideoSequence, TimelineItemModel, TimelineRange
from video_studio.timeline_service import timeline_service, TimelineService

logger = logging.getLogger("omnia.video_studio.speed_service")

class SpeedService:
    """High-level service coordinating speed changes, ramps, and freezes."""

    def __init__(
        self,
        engine: Optional[SpeedRemapEngine] = None,
        tl_service: Optional[TimelineService] = None,
    ):
        self.engine = engine or speed_remap_engine
        self.timeline_service = tl_service or timeline_service
        # In-memory document storage: {item_id: TimeRemapDocument}
        self._documents: Dict[str, TimeRemapDocument] = {}

    # ==========================================================================
    # 1. Document Management & Retrieval
    # ==========================================================================

    def get_remap_document(self, item_id: str) -> Optional[TimeRemapDocument]:
        return self._documents.get(item_id)

    def set_remap_document(self, doc: TimeRemapDocument) -> TimeRemapDocument:
        doc.revision += 1
        doc.updated_at = time.time()
        self._documents[doc.item_id] = doc
        return doc

    def delete_remap_document(self, item_id: str) -> bool:
        if item_id in self._documents:
            del self._documents[item_id]
            return True
        return False

    # ==========================================================================
    # 2. Constant Speed Control & Timeline Duration Adjustment
    # ==========================================================================

    def apply_constant_speed(
        self,
        sequence_id: str,
        item_id: str,
        speed: float,
        is_reverse: bool = False,
        ripple: bool = False,
        audio_mode: AudioSpeedMode = AudioSpeedMode.RESAMPLE_PITCH,
        interpolation_mode: FrameInterpolationMode = FrameInterpolationMode.DUPLICATION,
    ) -> Tuple[bool, str, Optional[TimeRemapDocument]]:
        """Applies a constant speed multiplier to a clip, updating its duration and time remap document.

        Args:
            sequence_id: Active sequence ID.
            item_id: Clip to adjust.
            speed: Speed multiplier (e.g. 0.5 for 50%, 2.0 for 200%). Must be > 0.
            is_reverse: Whether to reverse playback.
            ripple: If True, adjust subsequent clips to close/expand gap on the track.
            audio_mode: Audio handling strategy.
            interpolation_mode: Frame interpolation mode.

        Returns:
            Tuple of (success, message, updated_document).
        """
        if speed <= 0:
            return False, f"Speed multiplier must be positive: {speed}", None

        sequence = self.timeline_service.get_sequence(sequence_id)
        if not sequence:
            return False, f"Sequence '{sequence_id}' not found.", None

        # Find target item
        target_item: Optional[TimelineItemModel] = None
        target_track = None
        for track in sequence.tracks:
            for item in track.items:
                if item.item_id == item_id:
                    target_item = item
                    target_track = track
                    break
            if target_item:
                break

        if not target_item or not target_track:
            return False, f"Timeline item '{item_id}' not found in sequence '{sequence_id}'.", None

        # Compute new timeline duration based on source range and new speed
        # New duration = source_duration / speed
        new_timeline_duration = max(1, int(round(target_item.source_range.duration_frames / speed)))
        duration_delta = new_timeline_duration - target_item.timeline_range.duration_frames

        # Retrieve or create TimeRemapDocument
        doc = self._documents.get(item_id)
        if not doc:
            doc = TimeRemapDocument(
                remap_id=f"remap_{uuid.uuid4().hex[:8]}",
                item_id=item_id,
                source_reference_id=target_item.source_reference_id,
            )

        doc.constant_speed = speed
        doc.is_reverse = is_reverse
        doc.is_variable = False
        doc.audio_speed_mode = audio_mode
        doc.interpolation_mode = interpolation_mode
        self.set_remap_document(doc)

        # Update item model properties directly
        target_item.speed = speed
        target_item.timeline_range.duration_frames = new_timeline_duration
        target_item.metadata["time_remap_id"] = doc.remap_id
        target_item.metadata["is_reverse"] = is_reverse
        target_item.revision += 1

        # Ripple subsequent items on the track if requested
        if ripple and duration_delta != 0:
            end_f = target_item.timeline_range.start_frame + target_item.timeline_range.duration_frames
            for itm in target_track.items:
                if itm.item_id != item_id and itm.timeline_range.start_frame >= target_item.timeline_range.start_frame:
                    itm.timeline_range.start_frame += duration_delta
                    itm.revision += 1

        return True, "Speed applied successfully.", doc

    # ==========================================================================
    # 3. Variable Speed Ramps
    # ==========================================================================

    def create_speed_ramp(
        self,
        item_id: str,
        points: List[Dict[str, Any]],
        interpolation_mode: FrameInterpolationMode = FrameInterpolationMode.BLENDING,
        audio_mode: AudioSpeedMode = AudioSpeedMode.RESAMPLE_PITCH,
    ) -> Tuple[bool, str, Optional[TimeRemapDocument]]:
        """Sets a variable speed ramp curve with discrete control points."""
        if not points:
            return False, "Speed ramp must contain at least one control point.", None

        doc = self._documents.get(item_id)
        if not doc:
            doc = TimeRemapDocument(
                remap_id=f"remap_{uuid.uuid4().hex[:8]}",
                item_id=item_id,
                source_reference_id="",
            )

        curve_points: List[SpeedCurvePoint] = []
        for p in points:
            curve_points.append(SpeedCurvePoint.from_dict(p))

        curve_points.sort(key=lambda x: x.sequence_frame)

        doc.is_variable = True
        doc.speed_points = curve_points
        doc.interpolation_mode = interpolation_mode
        doc.audio_speed_mode = audio_mode
        self.set_remap_document(doc)

        return True, "Variable speed ramp updated.", doc

    # ==========================================================================
    # 4. Freeze Frames
    # ==========================================================================

    def add_freeze_frame(
        self,
        sequence_id: str,
        item_id: str,
        playhead_frame: int,
        duration_frames: int = 24,
    ) -> Tuple[bool, str, Optional[FreezeRegion]]:
        """Inserts a freeze-frame interval at the given playhead position."""
        if duration_frames <= 0:
            return False, "Freeze duration must be positive.", None

        sequence = self.timeline_service.get_sequence(sequence_id)
        if not sequence:
            return False, f"Sequence '{sequence_id}' not found.", None

        target_item = None
        for track in sequence.tracks:
            for item in track.items:
                if item.item_id == item_id:
                    target_item = item
                    break
            if target_item:
                break

        if not target_item:
            return False, f"Item '{item_id}' not found.", None

        # Resolve the source frame at the current playhead
        doc = self._documents.get(item_id)
        source_frame_f = self.engine.map_sequence_frame_to_source(doc, target_item, playhead_frame)
        frozen_source_frame = int(round(source_frame_f))

        relative_timeline_frame = playhead_frame - target_item.timeline_range.start_frame
        freeze = FreezeRegion(
            region_id=f"fr_{uuid.uuid4().hex[:8]}",
            timeline_start_frame=relative_timeline_frame,
            duration_frames=duration_frames,
            frozen_source_frame=frozen_source_frame,
        )

        if not doc:
            doc = TimeRemapDocument(
                remap_id=f"remap_{uuid.uuid4().hex[:8]}",
                item_id=item_id,
                source_reference_id=target_item.source_reference_id,
            )

        doc.freeze_regions.append(freeze)
        self.set_remap_document(doc)

        return True, "Freeze frame added.", freeze

    def remove_freeze_frame(self, item_id: str, region_id: str) -> bool:
        doc = self._documents.get(item_id)
        if not doc:
            return False

        orig_len = len(doc.freeze_regions)
        doc.freeze_regions = [r for r in doc.freeze_regions if r.region_id != region_id]
        if len(doc.freeze_regions) < orig_len:
            self.set_remap_document(doc)
            return True
        return False

    def register_capabilities(self) -> None:
        """Registers Module 15 speed control capabilities into OMNIA Video Studio registry."""
        try:
            from video_studio.registry import video_studio_capability_registry
            from video_studio.registry_models import (
                VideoStudioCapabilityDescriptor,
                VideoStudioCategory,
                ImplementationState,
                CapabilityDependency,
            )
            caps = [
                VideoStudioCapabilityDescriptor(
                    id="video.speed.constant",
                    name="Constant Speed Remapping",
                    description="Forward, reverse, and fractional constant speed time remapping.",
                    category=VideoStudioCategory.MOTION,
                    implementation_state=ImplementationState.IMPLEMENTED,
                    tags=["speed", "time_remap", "slowmo"],
                ),
                VideoStudioCapabilityDescriptor(
                    id="video.speed.variable_ramping",
                    name="Variable Speed Ramping",
                    description="Continuous piecewise speed curves with numerical integration.",
                    category=VideoStudioCategory.MOTION,
                    implementation_state=ImplementationState.IMPLEMENTED,
                    tags=["speed", "ramp", "curve"],
                ),
                VideoStudioCapabilityDescriptor(
                    id="video.speed.freeze_frame",
                    name="Freeze Frame & Hold Engine",
                    description="Arbitrary hold intervals freezing decoded source frames.",
                    category=VideoStudioCategory.MOTION,
                    implementation_state=ImplementationState.IMPLEMENTED,
                    tags=["freeze", "hold"],
                ),
                VideoStudioCapabilityDescriptor(
                    id="video.speed.interpolation",
                    name="Frame Interpolation Engine",
                    description="Frame duplication, alpha blending, and motion interpolation.",
                    category=VideoStudioCategory.MOTION,
                    implementation_state=ImplementationState.IMPLEMENTED,
                    tags=["interpolation", "optical_flow", "blending"],
                ),
                VideoStudioCapabilityDescriptor(
                    id="video.speed.audio_processing",
                    name="Audio Speed Processing",
                    description="Tape-style pitch shift resampling, time-stretch pitch preservation, and mute.",
                    category=VideoStudioCategory.AUDIO,
                    implementation_state=ImplementationState.IMPLEMENTED,
                    tags=["audio", "speed", "wsola"],
                ),
            ]
            for c in caps:
                try:
                    video_studio_capability_registry.register(c, auth_token="core")
                except Exception as e:
                    logger.debug(f"Capability '{c.id}' registration note: {e}")
        except Exception as ex:
            logger.debug(f"Capabilities registry not available: {ex}")

# Global singleton
speed_service = SpeedService()
speed_service.register_capabilities()
