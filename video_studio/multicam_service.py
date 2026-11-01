"""OMNIA Video Studio — Multicamera Editing, Angle Switching & Timeline Flattening Service (Module 20).

Coordinates:
- MulticamSequence lifecycle (creation, angle management, persistence).
- Camera synchronization analysis and manual offset trimming/nudging.
- Synchronized multi-angle grid preview and active angle decoding.
- Live angle-switching recording, undo/redo, and decision range resolution.
- Flattening multicamera decisions into standard TimelineTrack and TimelineItem clips.
- Module 1 Capability Registry integration.
"""

import os
import time
import uuid
import logging
from typing import Dict, Any, List, Optional, Tuple

import cv2
import numpy as np

from video_studio.multicam_models import (
    CameraAngle,
    AngleSwitchDecision,
    SyncMethod,
    MulticamAudioPolicy,
    MulticamSequence,
    AngleSyncResult,
    MulticamFlattenResult,
)
from video_studio.multicam_sync_engine import multicam_sync_engine, MulticamSyncEngine
from video_studio.media_models import MediaAsset
from video_studio.media_library import media_library_registry, ProjectMediaLibrary
from video_studio.timeline_models import (
    VideoSequence,
    TimelineTrackModel,
    TimelineItemModel,
    TimelineTrackType,
    TimelineItemType,
    TimelineRange,
    SourceRange,
)
from video_studio.timeline_service import timeline_service
from video_studio.playback_decoder import decoder_pool
from video_studio.playback_models import DecodedVideoFrame
from video_studio.registry import video_studio_capability_registry
from video_studio.registry_models import (
    VideoStudioCategory,
    ImplementationState,
    VideoStudioCapabilityDescriptor,
)

logger = logging.getLogger("omnia.video_studio.multicam_service")


class MulticamService:
    """Central service managing multicamera sequences, angle sync, switching, and flattening."""

    def __init__(self, sync_engine: Optional[MulticamSyncEngine] = None):
        self.sync_engine = sync_engine or multicam_sync_engine
        self.sequences: Dict[str, MulticamSequence] = {}
        # History stacks for undo/redo of angle switching decisions: {multicam_id: [decisions_snapshot]}
        self._undo_stacks: Dict[str, List[List[AngleSwitchDecision]]] = {}
        self._redo_stacks: Dict[str, List[List[AngleSwitchDecision]]] = {}
        self._register_capabilities()

    def _register_capabilities(self) -> None:
        """Registers Module 20 Multicamera capabilities into the global registry."""
        caps = [
            VideoStudioCapabilityDescriptor(
                id="video.multicam.sequence",
                name="Multicamera Sequence Model",
                description="Persistent multicamera container synchronizing multiple recording angles",
                category=VideoStudioCategory.EDITING,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["multicam", "angles", "sequence"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.multicam.sync",
                name="Camera Synchronization Engine",
                description="Timecode and audio waveform cross-correlation alignment across camera sources",
                category=VideoStudioCategory.EDITING,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["sync", "timecode", "waveform_correlation"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.multicam.switching",
                name="Live Angle Switching & Decision Engine",
                description="Real-time angle cut recording, timeline decision tracking, and undo/redo",
                category=VideoStudioCategory.EDITING,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["angle_switch", "live_cut", "decisions"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.multicam.flattening",
                name="Multicamera Timeline Flattening",
                description="Bakes multicamera cut decisions into standard timeline clips and tracks",
                category=VideoStudioCategory.TIMELINE,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["flatten", "bake", "timeline_items"],
            ),
        ]
        for cap in caps:
            try:
                video_studio_capability_registry.register(cap, auth_token="core")
            except Exception as e:
                logger.debug(f"Capability '{cap.id}' note: {e}")

    # --------------------------------------------------------------------------
    # Multicam Sequence Lifecycle
    # --------------------------------------------------------------------------

    def create_multicam_sequence(
        self,
        project_id: str,
        name: str,
        asset_ids: List[str],
        audio_policy: MulticamAudioPolicy = MulticamAudioPolicy.LOCKED_MASTER,
        sync_method: SyncMethod = SyncMethod.TIMECODE,
        frame_rate: float = 24.0,
    ) -> MulticamSequence:
        """Initializes a new multicamera sequence with camera angles derived from media assets."""
        pml = media_library_registry.get_or_create(project_id)
        multicam_id = f"mc_{uuid.uuid4().hex[:10]}"
        angles: List[CameraAngle] = []
        max_duration = 0

        for idx, aid in enumerate(asset_ids):
            asset = pml.get_asset(aid)
            label = f"CAM {chr(65 + idx)}" if idx < 26 else f"CAM {idx + 1}"
            display_name = asset.original_name if asset else f"Angle {idx + 1}"
            dur = asset.total_frames if asset and asset.total_frames else (
                int(round((asset.duration_seconds or 10.0) * frame_rate)) if asset else 240
            )
            max_duration = max(max_duration, dur)

            angle = CameraAngle(
                angle_id=f"ang_{uuid.uuid4().hex[:8]}",
                asset_id=aid,
                camera_label=label,
                display_name=display_name,
                sync_offset_frames=0,
                in_point_frame=0,
                out_point_frame=dur,
            )
            angles.append(angle)

        # Run initial synchronization
        if angles and sync_method != SyncMethod.MANUAL_OFFSET:
            sync_results = self.sync_engine.synchronize_angles(
                project_id=project_id,
                angles=angles,
                method=sync_method,
            )
            for res in sync_results:
                angle = next((a for a in angles if a.angle_id == res.angle_id), None)
                if angle:
                    angle.sync_offset_frames = res.calculated_offset_frames

        # Create initial default decision spanning the sequence on CAM A
        initial_decisions: List[AngleSwitchDecision] = []
        if angles and max_duration > 0:
            initial_decisions.append(AngleSwitchDecision(
                decision_id=f"dec_{uuid.uuid4().hex[:8]}",
                multicam_id=multicam_id,
                start_frame=0,
                end_frame=max_duration,
                active_angle_id=angles[0].angle_id,
            ))

        mc_seq = MulticamSequence(
            multicam_id=multicam_id,
            project_id=project_id,
            name=name,
            angles=angles,
            decisions=initial_decisions,
            audio_policy=audio_policy,
            master_audio_angle_id=angles[0].angle_id if angles else None,
            frame_rate=frame_rate,
            duration_frames=max_duration,
        )
        self.sequences[multicam_id] = mc_seq
        self._undo_stacks[multicam_id] = []
        self._redo_stacks[multicam_id] = []
        return mc_seq

    def get_multicam_sequence(self, multicam_id: str) -> Optional[MulticamSequence]:
        return self.sequences.get(multicam_id)

    # --------------------------------------------------------------------------
    # Angle Management & Sync Nudging
    # --------------------------------------------------------------------------

    def add_angle(self, multicam_id: str, asset_id: str, label: Optional[str] = None) -> CameraAngle:
        seq = self.sequences.get(multicam_id)
        if not seq:
            raise ValueError(f"Multicam sequence '{multicam_id}' not found.")

        pml = media_library_registry.get_or_create(seq.project_id)
        asset = pml.get_asset(asset_id)
        idx = len(seq.angles)
        camera_label = label or (f"CAM {chr(65 + idx)}" if idx < 26 else f"CAM {idx + 1}")
        display_name = asset.original_name if asset else f"Angle {idx + 1}"

        angle = CameraAngle(
            angle_id=f"ang_{uuid.uuid4().hex[:8]}",
            asset_id=asset_id,
            camera_label=camera_label,
            display_name=display_name,
        )
        seq.angles.append(angle)
        seq.version += 1
        seq.updated_at = time.time()
        return angle

    def nudge_angle_sync(self, multicam_id: str, angle_id: str, delta_frames: int) -> CameraAngle:
        """Adjusts an angle's synchronization offset by an exact delta in integer frames."""
        seq = self.sequences.get(multicam_id)
        if not seq:
            raise ValueError(f"Multicam sequence '{multicam_id}' not found.")

        angle = seq.get_angle(angle_id)
        if not angle:
            raise ValueError(f"Angle '{angle_id}' not found in multicam sequence.")

        angle.sync_offset_frames += delta_frames
        seq.version += 1
        seq.updated_at = time.time()
        return angle

    # --------------------------------------------------------------------------
    # Live Angle Switching Decisions
    # --------------------------------------------------------------------------

    def switch_angle_at_frame(
        self,
        multicam_id: str,
        frame: int,
        new_angle_id: str,
        end_frame: Optional[int] = None,
    ) -> List[AngleSwitchDecision]:
        """Records an angle switch at sequence time `frame`. Modifies decisions non-destructively."""
        seq = self.sequences.get(multicam_id)
        if not seq:
            raise ValueError(f"Multicam sequence '{multicam_id}' not found.")

        angle = seq.get_angle(new_angle_id)
        if not angle:
            raise ValueError(f"Target angle '{new_angle_id}' does not exist.")

        # Save snapshot for undo
        self._save_undo_snapshot(seq)

        frame = max(0, min(frame, seq.duration_frames))
        target_end = end_frame if end_frame is not None else seq.duration_frames

        # Re-partition existing decisions to insert the new cut
        new_decisions: List[AngleSwitchDecision] = []
        for d in seq.decisions:
            if d.end_frame <= frame:
                # Fully before cut
                new_decisions.append(d)
            elif d.start_frame >= target_end:
                # Fully after cut
                new_decisions.append(d)
            else:
                # Intersects with cut range
                if d.start_frame < frame:
                    # Keep prefix of previous angle
                    new_decisions.append(AngleSwitchDecision(
                        decision_id=f"dec_{uuid.uuid4().hex[:8]}",
                        multicam_id=multicam_id,
                        start_frame=d.start_frame,
                        end_frame=frame,
                        active_angle_id=d.active_angle_id,
                        audio_angle_id=d.audio_angle_id,
                    ))
                if d.end_frame > target_end:
                    # Keep suffix of previous angle
                    new_decisions.append(AngleSwitchDecision(
                        decision_id=f"dec_{uuid.uuid4().hex[:8]}",
                        multicam_id=multicam_id,
                        start_frame=target_end,
                        end_frame=d.end_frame,
                        active_angle_id=d.active_angle_id,
                        audio_angle_id=d.audio_angle_id,
                    ))

        # Insert new active angle segment
        new_decisions.append(AngleSwitchDecision(
            decision_id=f"dec_{uuid.uuid4().hex[:8]}",
            multicam_id=multicam_id,
            start_frame=frame,
            end_frame=target_end,
            active_angle_id=new_angle_id,
        ))

        # Sort and merge adjacent identical decisions
        new_decisions.sort(key=lambda x: x.start_frame)
        merged: List[AngleSwitchDecision] = []
        for d in new_decisions:
            if merged and merged[-1].active_angle_id == d.active_angle_id and merged[-1].end_frame == d.start_frame:
                merged[-1].end_frame = d.end_frame
            else:
                merged.append(d)

        seq.decisions = merged
        seq.version += 1
        seq.updated_at = time.time()
        return seq.decisions

    def undo_decision(self, multicam_id: str) -> bool:
        seq = self.sequences.get(multicam_id)
        if not seq or not self._undo_stacks.get(multicam_id):
            return False

        current_state = [AngleSwitchDecision(**d.__dict__) for d in seq.decisions]
        self._redo_stacks[multicam_id].append(current_state)

        prev_state = self._undo_stacks[multicam_id].pop()
        seq.decisions = prev_state
        seq.version += 1
        return True

    def redo_decision(self, multicam_id: str) -> bool:
        seq = self.sequences.get(multicam_id)
        if not seq or not self._redo_stacks.get(multicam_id):
            return False

        current_state = [AngleSwitchDecision(**d.__dict__) for d in seq.decisions]
        self._undo_stacks[multicam_id].append(current_state)

        next_state = self._redo_stacks[multicam_id].pop()
        seq.decisions = next_state
        seq.version += 1
        return True

    def _save_undo_snapshot(self, seq: MulticamSequence) -> None:
        if seq.multicam_id not in self._undo_stacks:
            self._undo_stacks[seq.multicam_id] = []
        snapshot = [AngleSwitchDecision(**d.__dict__) for d in seq.decisions]
        self._undo_stacks[seq.multicam_id].append(snapshot)
        self._redo_stacks[seq.multicam_id] = [] # clear redo on new action

    # --------------------------------------------------------------------------
    # Multicamera Preview Frame Rendering
    # --------------------------------------------------------------------------

    def render_multicam_frame(
        self,
        multicam_id: str,
        frame: int,
        grid_width: int = 1920,
        grid_height: int = 1080,
    ) -> DecodedVideoFrame:
        """Renders a multi-angle grid preview (up to 4 angles) showing synchronous playback."""
        seq = self.sequences.get(multicam_id)
        if not seq:
            raise ValueError(f"Multicam sequence '{multicam_id}' not found.")

        pml = media_library_registry.get_or_create(seq.project_id)
        enabled_angles = [a for a in seq.angles if a.is_enabled]
        n_angles = len(enabled_angles)
        canvas = np.zeros((grid_height, grid_width, 4), dtype=np.uint8)
        canvas[:, :, 3] = 255 # opaque black

        if n_angles == 0:
            return DecodedVideoFrame(
                frame_id=str(uuid.uuid4()),
                asset_id="multicam_empty",
                timeline_frame=frame,
                source_frame=frame,
                pts_seconds=frame / max(1.0, seq.frame_rate),
                duration_seconds=1.0 / max(1.0, seq.frame_rate),
                width=grid_width,
                height=grid_height,
                buffer_bytes=canvas.tobytes(),
            )

        active_dec = seq.get_active_decision_at(frame)
        active_angle_id = active_dec.active_angle_id if active_dec else (enabled_angles[0].angle_id if enabled_angles else None)

        # 2x2 grid calculation for up to 4 angles
        cols = 2 if n_angles > 1 else 1
        rows = 2 if n_angles > 2 else 1
        tile_w = grid_width // cols
        tile_h = grid_height // rows

        for idx, angle in enumerate(enabled_angles[:4]):
            asset = pml.get_asset(angle.asset_id)
            if not asset:
                continue

            # Calculate synchronized source frame: sequence_frame - angle.sync_offset
            src_frame = max(0, frame - angle.sync_offset_frames)
            file_path = asset.proxy_location if (asset.proxy_location and os.path.exists(asset.proxy_location)) else asset.file_location

            decoder = decoder_pool.get_decoder(asset.asset_id, file_path)
            dec_frame = decoder.decode_video_frame(
                timeline_frame=frame,
                source_frame=src_frame,
                width=tile_w,
                height=tile_h,
            )

            # Draw tile on grid
            r = idx // cols
            c = idx % cols
            y_start = r * tile_h
            x_start = c * tile_w

            if dec_frame.buffer_bytes:
                expected_size = dec_frame.height * dec_frame.width * 4
                if len(dec_frame.buffer_bytes) == expected_size:
                    tile_data = np.frombuffer(dec_frame.buffer_bytes, dtype=np.uint8).reshape((dec_frame.height, dec_frame.width, 4))
                else:
                    # Lightweight test pattern buffer fallback
                    tile_data = np.full((tile_h, tile_w, 4), (0, 240, 255, 255), dtype=np.uint8)

                if tile_data.shape[0] != tile_h or tile_data.shape[1] != tile_w:
                    tile_data = cv2.resize(tile_data, (tile_w, tile_h))
                canvas[y_start:y_start + tile_h, x_start:x_start + tile_w] = tile_data

            # Draw green active border if this angle is currently cut live
            if angle.angle_id == active_angle_id:
                cv2.rectangle(
                    canvas,
                    (x_start + 4, y_start + 4),
                    (x_start + tile_w - 4, y_start + tile_h - 4),
                    (0, 255, 0, 255),
                    6,
                )

            # Draw camera label overlay
            cv2.putText(
                canvas,
                angle.camera_label,
                (x_start + 20, y_start + 45),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (255, 255, 255, 255),
                2,
            )

        return DecodedVideoFrame(
            frame_id=str(uuid.uuid4()),
            asset_id="multicam_grid",
            timeline_frame=frame,
            source_frame=frame,
            pts_seconds=frame / max(1.0, seq.frame_rate),
            duration_seconds=1.0 / max(1.0, seq.frame_rate),
            width=grid_width,
            height=grid_height,
            buffer_bytes=canvas.tobytes(),
        )

    # --------------------------------------------------------------------------
    # Timeline Flattening
    # --------------------------------------------------------------------------

    def flatten_to_sequence(
        self,
        multicam_id: str,
        target_sequence: VideoSequence,
    ) -> MulticamFlattenResult:
        """Bakes multicamera angle switch decisions into real TimelineItem clips on the target sequence."""
        seq = self.sequences.get(multicam_id)
        if not seq:
            return MulticamFlattenResult(
                multicam_id=multicam_id,
                target_sequence_id=target_sequence.sequence_id,
                video_track_id="",
                audio_track_id="",
                is_success=False,
                error_message=f"Multicam sequence '{multicam_id}' not found.",
            )

        pml = media_library_registry.get_or_create(seq.project_id)

        # Find or create dedicated Video and Audio tracks
        v_track = next((t for t in target_sequence.tracks if t.track_type == TimelineTrackType.VIDEO), None)
        if not v_track:
            v_track = TimelineTrackModel(
                track_id=f"tr_v_{uuid.uuid4().hex[:6]}",
                sequence_id=target_sequence.sequence_id,
                name="Multicam Video",
                track_type=TimelineTrackType.VIDEO,
            )
            target_sequence.tracks.append(v_track)

        a_track = next((t for t in target_sequence.tracks if t.track_type == TimelineTrackType.AUDIO), None)
        if not a_track:
            a_track = TimelineTrackModel(
                track_id=f"tr_a_{uuid.uuid4().hex[:6]}",
                sequence_id=target_sequence.sequence_id,
                name="Multicam Audio",
                track_type=TimelineTrackType.AUDIO,
            )
            target_sequence.tracks.append(a_track)

        created_clip_ids = []
        for dec in seq.decisions:
            angle = seq.get_angle(dec.active_angle_id)
            if not angle:
                continue

            asset = pml.get_asset(angle.asset_id)
            clip_dur = dec.end_frame - dec.start_frame
            src_in = max(0, dec.start_frame - angle.sync_offset_frames)

            clip_id = f"clip_{uuid.uuid4().hex[:8]}"
            item = TimelineItemModel(
                item_id=clip_id,
                track_id=v_track.track_id,
                sequence_id=target_sequence.sequence_id,
                name=f"{angle.camera_label} - {angle.display_name}",
                item_type=TimelineItemType.MEDIA_CLIP,
                source_reference_id=angle.asset_id,
                timeline_range=TimelineRange(start_frame=dec.start_frame, duration_frames=clip_dur),
                source_range=SourceRange(in_frame=src_in, duration_frames=clip_dur),
            )
            v_track.items.append(item)
            created_clip_ids.append(clip_id)

        # Handle locked master audio track
        master_angle = seq.get_angle(seq.master_audio_angle_id) if seq.master_audio_angle_id else (seq.angles[0] if seq.angles else None)
        if master_angle:
            a_clip_id = f"clip_audio_{uuid.uuid4().hex[:8]}"
            src_in_a = max(0, 0 - master_angle.sync_offset_frames)
            a_item = TimelineItemModel(
                item_id=a_clip_id,
                track_id=a_track.track_id,
                sequence_id=target_sequence.sequence_id,
                name=f"Master Audio ({master_angle.camera_label})",
                item_type=TimelineItemType.MEDIA_CLIP,
                source_reference_id=master_angle.asset_id,
                timeline_range=TimelineRange(start_frame=0, duration_frames=seq.duration_frames),
                source_range=SourceRange(in_frame=src_in_a, duration_frames=seq.duration_frames),
            )
            a_track.items.append(a_item)
            created_clip_ids.append(a_clip_id)

        target_sequence.duration_frames = max(target_sequence.duration_frames, seq.duration_frames)
        target_sequence.revision += 1

        return MulticamFlattenResult(
            multicam_id=multicam_id,
            target_sequence_id=target_sequence.sequence_id,
            video_track_id=v_track.track_id,
            audio_track_id=a_track.track_id,
            created_clip_ids=created_clip_ids,
            total_segments_flattened=len(seq.decisions),
            is_success=True,
        )


# Global singleton
multicam_service = MulticamService()
