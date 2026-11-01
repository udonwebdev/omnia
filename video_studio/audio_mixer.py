"""OMNIA Video Studio — Multitrack Audio Mixer & Processing Engine (Module 9).

Coordinates:
- Multi-channel timeline audio mixing across tracks and clips.
- Clip-level gain, enable/disable, and trimming awareness.
- Track-level gain, pan, mute, and solo policy.
- Bus summing, submix routing, and Master output chain.
- Volume and pan automation integration with Module 8 (AnimationService & Evaluator).
- Real-time and offline sample rendering with peak & RMS metering.
"""

from typing import Dict, Any, List, Optional, Tuple, Set
import math
import uuid
import numpy as np

from video_studio.timeline_models import (
    VideoSequence,
    TimelineTrackModel,
    TimelineTrackType,
    TimelineItemModel,
    TimelineItemType,
)
from video_studio.audio_models import (
    AudioBuffer,
    AudioBus,
    AudioBusType,
    AudioChannelLayout,
    AudioRoutingGraph,
    AudioMeterSnapshot,
    SampleTime,
    PanningLaw,
)
from video_studio.audio_dsp import (
    IAudioProcessor,
    GainProcessor,
    PanningProcessor,
    ParametricEqualizerProcessor,
    CompressorProcessor,
    ProcessorChain,
)
from video_studio.playback_decoder import MediaDecoderPool, decoder_pool
from video_studio.media_storage import media_storage_manager
from video_studio.animation_service import animation_service, AnimationService
from video_studio.animation_evaluator import animation_evaluator, AnimationEvaluator

class MultitrackAudioMixer:
    """Core multitrack mixing engine for OMNIA Video Studio."""

    def __init__(
        self,
        decoders: Optional[MediaDecoderPool] = None,
        anim_service: Optional[AnimationService] = None,
        anim_eval: Optional[AnimationEvaluator] = None,
    ):
        self.decoders = decoders or decoder_pool
        self.animation_service = anim_service or animation_service
        self.animation_evaluator = anim_eval or animation_evaluator

        # Routing and bus states
        self.routing_graphs: Dict[str, AudioRoutingGraph] = {} # sequence_id -> graph
        self.master_buses: Dict[str, AudioBus] = {} # sequence_id -> master bus
        self.track_chains: Dict[str, ProcessorChain] = {} # track_id -> ProcessorChain
        self.bus_chains: Dict[str, ProcessorChain] = {} # bus_id -> ProcessorChain

        # Peak & RMS Meter Snapshots cache
        self.track_meters: Dict[str, AudioMeterSnapshot] = {}
        self.bus_meters: Dict[str, AudioMeterSnapshot] = {}
        self.master_meters: Dict[str, AudioMeterSnapshot] = {}

    def get_or_create_routing(self, sequence: VideoSequence) -> AudioRoutingGraph:
        """Retrieves or initializes the audio routing graph and buses for a sequence."""
        if sequence.sequence_id not in self.routing_graphs:
            graph = AudioRoutingGraph()
            # Default Master Bus
            master = AudioBus(
                bus_id=f"master_{sequence.sequence_id}",
                name="Master Out",
                bus_type=AudioBusType.MASTER,
                layout=AudioChannelLayout.STEREO,
                gain_db=0.0,
                pan=0.0,
            )
            graph.add_bus(master)
            self.master_buses[sequence.sequence_id] = master
            self.routing_graphs[sequence.sequence_id] = graph

            # Route all existing audio tracks to Master by default
            for track in sequence.tracks:
                if track.track_type == TimelineTrackType.AUDIO:
                    graph.route_track(track.track_id, master.bus_id)
                    if track.track_id not in self.track_chains:
                        self.track_chains[track.track_id] = ProcessorChain()

        return self.routing_graphs[sequence.sequence_id]

    def render_audio_slice(
        self,
        sequence: VideoSequence,
        start_frame: int,
        duration_frames: int,
        sample_rate: int = 48000,
        output_channels: int = 2,
    ) -> AudioBuffer:
        """Renders and mixes an audio slice across all tracks, buses, and master output.
        
        Evaluates:
        1. Sample-accurate timeline ranges.
        2. Audio clips on each active track.
        3. Solo/Mute policy: If any track has is_solo=True, only soloed tracks are mixed.
        4. Module 8 automation (Gain & Pan).
        5. Clip, Track, and Bus DSP chains.
        6. Bus graph summing and cycle-free downmix.
        7. Peak and RMS meters.
        """
        graph = self.get_or_create_routing(sequence)
        fps = sequence.settings.frame_rate if hasattr(sequence, "settings") and sequence.settings else 24.0

        # Exact integer sample calculations
        start_sample = int(round((start_frame * sample_rate) / fps))
        end_sample = int(round(((start_frame + duration_frames) * sample_rate) / fps))
        total_samples = max(0, end_sample - start_sample)

        master_buf = AudioBuffer.silence(total_samples, channels=output_channels, sample_rate=sample_rate, start_sample=start_sample)
        if total_samples == 0:
            return master_buf

        # Collect audio tracks
        audio_tracks = [t for t in sequence.tracks if t.track_type == TimelineTrackType.AUDIO and t.is_enabled]
        any_solo = any(t.is_solo for t in audio_tracks)

        # Map to hold temporary accumulated buffers per bus: bus_id -> AudioBuffer
        bus_accumulators: Dict[str, AudioBuffer] = {}
        for bus_id in graph.buses:
            bus_accumulators[bus_id] = AudioBuffer.silence(total_samples, channels=output_channels, sample_rate=sample_rate, start_sample=start_sample)

        # Process each audio track
        for track in audio_tracks:
            # Solo / Mute policy
            if track.is_muted:
                continue
            if any_solo and not track.is_solo:
                continue

            track_buf = AudioBuffer.silence(total_samples, channels=output_channels, sample_rate=sample_rate, start_sample=start_sample)

            # Find clips overlapping the requested range
            end_frame = start_frame + duration_frames
            for clip in track.items:
                if not clip.is_enabled:
                    continue
                c_start = clip.timeline_range.start_frame
                c_end = clip.timeline_range.end_frame

                if c_start >= end_frame or c_end <= start_frame:
                    continue # No overlap

                # Overlap frames
                overlap_start_frame = max(start_frame, c_start)
                overlap_end_frame = min(end_frame, c_end)

                # Sample offsets within the output slice
                clip_slice_start_sample = int(round(((overlap_start_frame - start_frame) * sample_rate) / fps))
                clip_slice_end_sample = int(round(((overlap_end_frame - start_frame) * sample_rate) / fps))
                overlap_samples = clip_slice_end_sample - clip_slice_start_sample

                if overlap_samples <= 0:
                    continue

                # Source offset in frames
                source_frame_offset = overlap_start_frame - c_start
                source_in_frame = clip.source_range.in_frame + int(source_frame_offset * clip.speed)

                # Retrieve and decode audio from media asset
                file_path = media_storage_manager.resolve_asset_path(clip.source_reference_id)
                decoder = self.decoders.get_decoder(clip.source_reference_id, file_path)

                dec_block = decoder.decode_audio_block(
                    timeline_frame=overlap_start_frame,
                    source_frame=source_in_frame,
                    sample_rate=sample_rate,
                    channels=output_channels,
                )

                # Decode into AudioBuffer
                if dec_block.buffer_bytes:
                    raw_buf = AudioBuffer.from_int16_bytes(
                        dec_block.buffer_bytes,
                        channels=dec_block.channels,
                        sample_rate=sample_rate,
                        start_sample=clip_slice_start_sample,
                    )
                else:
                    raw_buf = AudioBuffer.silence(overlap_samples, channels=output_channels, sample_rate=sample_rate)

                # Resize or pad buffer if needed to match overlap_samples
                if raw_buf.samples < overlap_samples:
                    padded = np.zeros((output_channels, overlap_samples), dtype=np.float32)
                    padded[:, :raw_buf.samples] = raw_buf.data
                    raw_buf.data = padded
                elif raw_buf.samples > overlap_samples:
                    raw_buf.data = raw_buf.data[:, :overlap_samples]

                # Module 15: Audio Speed Processing & Time Remapping
                from video_studio.speed_service import speed_service
                remap_doc = speed_service.get_remap_document(clip.item_id)
                speed = clip.speed if clip.speed != 0 else 1.0
                if remap_doc:
                    speed = remap_doc.constant_speed if not remap_doc.is_reverse else -remap_doc.constant_speed
                    raw_buf = speed_service.engine.process_audio_speed(raw_buf, speed, remap_doc.audio_speed_mode)
                elif abs(speed - 1.0) > 1e-4:
                    from video_studio.speed_models import AudioSpeedMode
                    raw_buf = speed_service.engine.process_audio_speed(raw_buf, speed, AudioSpeedMode.RESAMPLE_PITCH)

                # Ensure buffer length still matches overlap_samples after speed processing
                if raw_buf.samples < overlap_samples:
                    padded = np.zeros((output_channels, overlap_samples), dtype=np.float32)
                    padded[:, :raw_buf.samples] = raw_buf.data
                    raw_buf.data = padded
                elif raw_buf.samples > overlap_samples:
                    raw_buf.data = raw_buf.data[:, :overlap_samples]

                # Clip Gain & Clip Automation
                clip_gain_db = clip.metadata.get("gain_db", 0.0)
                # Check Module 8 automation for clip gain
                clip_gain_prop = self.animation_service.get_property(f"{clip.item_id}_gain")
                if clip_gain_prop:
                    clip_gain_db = float(self.animation_evaluator.evaluate(clip_gain_prop, overlap_start_frame))

                clip_gain_linear = 0.0 if clip_gain_db <= -120.0 else (10.0 ** (clip_gain_db / 20.0))
                raw_buf.apply_gain(clip_gain_linear)

                # Apply Module 12 Audio Transitions (Fade In, Fade Out, Crossfade)
                from video_studio.transitions_service import transitions_service
                from video_studio.transitions_models import TransitionType, CrossfadeCurve

                # Check if this clip has an active transition during this overlap slice
                for tr in transitions_service.get_transitions_for_sequence(sequence.sequence_id):
                    if not tr.is_enabled or tr.track_id != track.track_id:
                        continue
                    if not (tr.outgoing_clip_id == clip.item_id or tr.incoming_clip_id == clip.item_id):
                        continue

                    # If transition overlaps this clip's current slice
                    if tr.intersects_range(overlap_start_frame, overlap_end_frame) if hasattr(tr, "intersects_range") else (tr.start_frame < overlap_end_frame and tr.end_frame > overlap_start_frame):
                        # Apply sample-accurate transition gain curve across raw_buf
                        for i in range(overlap_samples):
                            s_frame = overlap_start_frame + int((i / sample_rate) * fps)
                            p = tr.get_progress(s_frame)

                            # Determine gain factor based on outgoing vs incoming and transition type
                            if tr.outgoing_clip_id == clip.item_id:
                                # Outgoing clip fades down (from 1 to 0)
                                if tr.crossfade_curve == CrossfadeCurve.EQUAL_POWER:
                                    gain_factor = math.cos(p * (math.pi / 2.0))
                                else:  # LINEAR
                                    gain_factor = 1.0 - p
                            else:
                                # Incoming clip fades up (from 0 to 1)
                                if tr.crossfade_curve == CrossfadeCurve.EQUAL_POWER:
                                    gain_factor = math.sin(p * (math.pi / 2.0))
                                else:  # LINEAR
                                    gain_factor = p

                            raw_buf.data[:, i] *= gain_factor

                # Sum into track buffer at precise offset
                track_buf.data[:, clip_slice_start_sample:clip_slice_end_sample] += raw_buf.data

            # Track Gain & Pan (with Automation)
            track_gain_db = track.metadata.get("gain_db", 0.0)
            track_pan = track.metadata.get("pan", 0.0)

            # Check Module 8 automation for track gain and pan
            t_gain_prop = self.animation_service.get_property(f"{track.track_id}_gain")
            if t_gain_prop:
                track_gain_db = float(self.animation_evaluator.evaluate(t_gain_prop, start_frame))
            t_pan_prop = self.animation_service.get_property(f"{track.track_id}_pan")
            if t_pan_prop:
                track_pan = float(self.animation_evaluator.evaluate(t_pan_prop, start_frame))

            track_gain_linear = 0.0 if track_gain_db <= -120.0 else (10.0 ** (track_gain_db / 20.0))
            track_buf.apply_gain(track_gain_linear)
            track_buf.apply_panning(track_pan)

            # Process Track DSP Chain
            if track.track_id in self.track_chains:
                track_buf = self.track_chains[track.track_id].process(track_buf)

            # Calculate and store Track Meter
            self.track_meters[track.track_id] = AudioMeterSnapshot.calculate(track_buf)

            # Route track into its designated bus
            target_bus_id = graph.track_routes.get(track.track_id, f"master_{sequence.sequence_id}")
            if target_bus_id in bus_accumulators:
                track_buf.mix_into(bus_accumulators[target_bus_id])

        # Process and resolve Bus Routing Graph (Submixes to Master)
        master_bus_id = f"master_{sequence.sequence_id}"
        # Order buses: non-master first, then master
        submix_buses = [b for b in graph.buses.values() if b.bus_id != master_bus_id]

        for bus in submix_buses:
            if bus.is_muted:
                continue
            b_buf = bus_accumulators[bus.bus_id]
            b_buf.apply_gain(bus.gain_linear)
            b_buf.apply_panning(bus.pan)

            # Process Bus DSP Chain
            if bus.bus_id in self.bus_chains:
                b_buf = self.bus_chains[bus.bus_id].process(b_buf)

            self.bus_meters[bus.bus_id] = AudioMeterSnapshot.calculate(b_buf)

            # Route bus into target bus or Master
            dest_bus_id = bus.target_bus_id or master_bus_id
            if dest_bus_id in bus_accumulators:
                b_buf.mix_into(bus_accumulators[dest_bus_id])

        # Process Master Bus
        if master_bus_id in bus_accumulators:
            master_bus = graph.buses.get(master_bus_id)
            master_buf = bus_accumulators[master_bus_id]
            if master_bus and not master_bus.is_muted:
                master_buf.apply_gain(master_bus.gain_linear)
                master_buf.apply_panning(master_bus.pan)

            if master_bus_id in self.bus_chains:
                master_buf = self.bus_chains[master_bus_id].process(master_buf)

            self.master_meters[sequence.sequence_id] = AudioMeterSnapshot.calculate(master_buf)

        return master_buf


# Global singleton
multitrack_audio_mixer = MultitrackAudioMixer()
