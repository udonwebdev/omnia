"""OMNIA Video Studio — Timeline Playback Engine & Real-Time Viewer (Module 7).

Orchestrates real-time timeline playback, multi-track visual/audio evaluation,
frame-accurate clock stepping, seeking, pause, stop, and A/V synchronization.
"""

from typing import Dict, Any, List, Optional, Tuple
import time
import uuid
import logging

from video_studio.playback_models import (
    PlaybackState,
    PlaybackQuality,
    DecodedVideoFrame,
    DecodedAudioBlock,
    PlaybackMetrics,
    PlaybackSession,
)
from video_studio.playback_decoder import (
    IMediaDecoder,
    SoftwareMediaDecoder,
    MediaDecoderPool,
    decoder_pool,
)
from video_studio.timeline_models import (
    VideoSequence,
    TimelineTrackModel,
    TimelineItemModel,
    TimelineTrackType,
    TimelineItemType,
    TimelineItemState,
)
from video_studio.timeline_query import TimelineQueryEngine, timeline_query_engine
from video_studio.media_storage import media_storage_manager

logger = logging.getLogger("Omnia.VideoStudio.Playback")

class TimelinePlaybackEngine:
    """Manages active playback sessions, timeline evaluation, and frame delivery."""

    def __init__(
        self,
        query_engine: Optional[TimelineQueryEngine] = None,
        decoder_pool_inst: Optional[MediaDecoderPool] = None,
    ):
        self.query_engine = query_engine or timeline_query_engine
        self.decoders = decoder_pool_inst or decoder_pool
        self._sessions: Dict[str, PlaybackSession] = {}
        self._active_sequences: Dict[str, VideoSequence] = {}
        self._last_frames: Dict[str, DecodedVideoFrame] = {}

    def create_session(
        self,
        sequence: VideoSequence,
        project_id: str,
        quality: PlaybackQuality = PlaybackQuality.FULL,
    ) -> PlaybackSession:
        """Initializes a new playback session bound to a sequence."""
        session_id = f"play_{uuid.uuid4().hex[:12]}"
        session = PlaybackSession(
            session_id=session_id,
            project_id=project_id,
            sequence_id=sequence.sequence_id,
            state=PlaybackState.READY,
            current_frame=0,
            quality=quality,
        )
        self._sessions[session_id] = session
        self._active_sequences[session_id] = sequence
        return session

    def get_session(self, session_id: str) -> Optional[PlaybackSession]:
        return self._sessions.get(session_id)

    def destroy_session(self, session_id: str) -> bool:
        if session_id in self._sessions:
            session = self._sessions[session_id]
            session.state = PlaybackState.STOPPED
            del self._sessions[session_id]
            if session_id in self._active_sequences:
                del self._active_sequences[session_id]
            if session_id in self._last_frames:
                del self._last_frames[session_id]
            return True
        return False

    def evaluate_timeline(
        self,
        sequence: VideoSequence,
        frame: int,
    ) -> Tuple[List[TimelineItemModel], List[TimelineItemModel]]:
        """Evaluates active video and audio clips at frame."""
        items = self.query_engine.get_items_at_time(sequence, frame)

        active_video: List[TimelineItemModel] = []
        active_audio: List[TimelineItemModel] = []

        track_map = {t.track_id: t for t in sequence.tracks}

        for item in items:
            track = track_map.get(item.track_id)
            if not track or not track.is_enabled:
                continue

            # Check track types
            if track.track_type in (TimelineTrackType.VIDEO, TimelineTrackType.ADJUSTMENT, TimelineTrackType.OVERLAY):
                if track.is_visible and item.is_enabled:
                    active_video.append(item)
            elif track.track_type == TimelineTrackType.AUDIO:
                if not track.is_muted and item.is_enabled:
                    active_audio.append(item)

        # Sort video by track index descending (highest track on top)
        active_video.sort(key=lambda x: track_map[x.track_id].index, reverse=True)
        return active_video, active_audio

    def render_frame(
        self,
        session_id: str,
        frame: Optional[int] = None,
    ) -> DecodedVideoFrame:
        """Renders/decodes the frame at the requested position or current playhead."""
        session = self._sessions.get(session_id)
        if not session:
            raise RuntimeError(f"Playback session '{session_id}' not found.")

        sequence = self._active_sequences.get(session_id)
        if not sequence:
            raise RuntimeError(f"Sequence for session '{session_id}' not found.")

        target_frame = session.current_frame if frame is None else frame
        active_video, _ = self.evaluate_timeline(sequence, target_frame)

        width = sequence.settings.width
        height = sequence.settings.height

        if not active_video:
            # Empty gap frame
            gap_frame = DecodedVideoFrame(
                frame_id=str(uuid.uuid4()),
                asset_id="gap",
                timeline_frame=target_frame,
                source_frame=0,
                pts_seconds=target_frame / max(1.0, sequence.settings.frame_rate),
                duration_seconds=1.0 / max(1.0, sequence.settings.frame_rate),
                width=width,
                height=height,
                pixel_format="RGBA",
                is_gap=True,
                buffer_bytes=b"\x00\x00\x00\xff" * min(width * height, 256),
            )
            self._last_frames[session_id] = gap_frame
            session.metrics.frames_rendered += 1
            return gap_frame

        # Check if sequence has active motion graphics, subtitles, transitions, multiple active clips, or explicit compositing/effects
        from video_studio.transitions_service import transitions_service
        from video_studio.captions_service import captions_service
        from video_studio.motion_graphics_service import motion_graphics_service
        has_graphics = bool(motion_graphics_service.list_compositions_for_sequence(sequence.sequence_id))
        has_subtitles = bool(captions_service.list_documents_for_sequence(sequence.sequence_id))
        has_transition = bool(transitions_service.get_transitions_for_sequence(sequence.sequence_id))
        has_multilayer = len(active_video) > 1
        has_effects = any(
            bool(c.effects) or (c.metadata and (c.metadata.get("opacity", 1.0) < 1.0 or c.metadata.get("blend_mode")))
            for c in active_video
        )

        if has_graphics or has_subtitles or has_transition or has_multilayer or has_effects:
            try:
                from video_studio.compositor import multilayer_compositor
                comp_buf = multilayer_compositor.composite_sequence_frame(
                    sequence=sequence,
                    target_frame=target_frame,
                    canvas_width=width,
                    canvas_height=height,
                )
                composite_frame = DecodedVideoFrame(
                    frame_id=str(uuid.uuid4()),
                    asset_id="composited",
                    timeline_frame=target_frame,
                    source_frame=target_frame,
                    pts_seconds=target_frame / max(1.0, sequence.settings.frame_rate if sequence.settings else 24.0),
                    duration_seconds=1.0 / max(1.0, sequence.settings.frame_rate if sequence.settings else 24.0),
                    width=width,
                    height=height,
                    pixel_format="RGBA",
                    is_offline=False,
                    is_gap=False,
                    buffer_bytes=comp_buf.to_bytes(),
                )
                self._last_frames[session_id] = composite_frame
                session.metrics.frames_rendered += 1
                return composite_frame
            except Exception as e:
                logger.debug(f"Direct compositor note, falling back to top clip: {e}")

        # Decode topmost video clip directly
        top_clip = active_video[0]
        # Calculate source media frame mapping with Module 15 Speed Remap Engine
        from video_studio.speed_service import speed_service
        remap_doc = speed_service.get_remap_document(top_clip.item_id)
        source_frame_f = speed_service.engine.map_sequence_frame_to_source(remap_doc, top_clip, target_frame)
        source_frame = int(round(source_frame_f))

        # Module 18: Resolve playback source path (Original vs Proxy)
        file_path = media_storage_manager.resolve_asset_path(top_clip.source_reference_id)
        try:
            from video_studio.proxy_service import proxy_service
            from video_studio.proxy_models import PlaybackSourceMode
            from video_studio.media_library import media_library_registry
            pml = media_library_registry.get_or_create(session.project_id)
            asset = pml.get_asset(top_clip.source_reference_id)
            if asset:
                p_mode = PlaybackSourceMode.PREFER_PROXY if session.quality == PlaybackQuality.PROXY_PREFER else PlaybackSourceMode(session.source_mode)
                resolved_path, is_proxy = proxy_service.resolve_source_for_playback(asset, p_mode)
                file_path = resolved_path
        except Exception as e:
            logger.debug(f"Proxy resolution note, defaulting to storage path: {e}")

        dec = self.decoders.get_decoder(top_clip.source_reference_id, file_path)

        t0 = time.time()
        dec_frame = dec.decode_video_frame(
            timeline_frame=target_frame,
            source_frame=source_frame,
            width=width,
            height=height,
            quality=session.quality,
        )
        dec_time_ms = (time.time() - t0) * 1000.0

        session.metrics.frames_rendered += 1
        session.metrics.average_decode_time_ms = dec_time_ms
        self._last_frames[session_id] = dec_frame
        return dec_frame

    def play(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.state = PlaybackState.PLAYING
        session.updated_at = time.time()
        return True

    def pause(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.state = PlaybackState.PAUSED
        session.updated_at = time.time()
        return True

    def stop(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.state = PlaybackState.STOPPED
        session.current_frame = 0
        session.updated_at = time.time()
        return True

    def seek(self, session_id: str, target_frame: int) -> DecodedVideoFrame:
        session = self._sessions.get(session_id)
        if not session:
            raise RuntimeError(f"Playback session '{session_id}' not found.")

        sequence = self._active_sequences.get(session_id)
        if not sequence:
            raise RuntimeError("Sequence not bound.")

        t0 = time.time()
        session.state = PlaybackState.SEEKING
        clamped_frame = max(0, min(target_frame, sequence.duration_frames))
        session.current_frame = clamped_frame

        frame = self.render_frame(session_id, clamped_frame)
        session.state = PlaybackState.PAUSED
        seek_latency = (time.time() - t0) * 1000.0

        session.metrics.seek_count += 1
        session.metrics.last_seek_latency_ms = seek_latency
        session.updated_at = time.time()
        return frame

    def step_frame(self, session_id: str, step_delta: int = 1) -> DecodedVideoFrame:
        session = self._sessions.get(session_id)
        if not session:
            raise RuntimeError(f"Playback session '{session_id}' not found.")
        new_frame = session.current_frame + step_delta
        return self.seek(session_id, new_frame)

    def render_audio(
        self,
        session_id: str,
        duration_frames: int = 1,
        sample_rate: int = 48000,
        channels: int = 2,
    ) -> Any:
        """Renders synchronized audio for the current playhead frame."""
        session = self._sessions.get(session_id)
        if not session:
            raise RuntimeError(f"Playback session '{session_id}' not found.")
        sequence = self._active_sequences.get(session_id)
        if not sequence:
            raise RuntimeError(f"Sequence for session '{session_id}' not found.")

        from video_studio.audio_service import audio_engine_service
        return audio_engine_service.render_timeline_audio(
            sequence=sequence,
            start_frame=session.current_frame,
            duration_frames=duration_frames,
            sample_rate=sample_rate,
            channels=channels,
        )

    def set_quality(self, session_id: str, quality: PlaybackQuality) -> bool:
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.quality = quality
        session.updated_at = time.time()
        return True

# Global playback engine singleton
playback_engine = TimelinePlaybackEngine()
