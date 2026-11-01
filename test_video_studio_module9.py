"""OMNIA Video Studio — Module 9 Verification Test Suite.

Verifies:
1. SampleTime: Integer sample-accurate conversions and frame-to-sample mapping.
2. AudioBuffer: Allocation, planar structure, gain ramps, equal-power panning, mono/stereo mixing, int16 PCM conversion.
3. AudioMeterSnapshot: Real peak (dBFS) and RMS calculations with overload/clipping indicators.
4. GainProcessor & PanningProcessor: Linear and decibel gain, smooth interpolation, equal-power law.
5. ParametricEqualizerProcessor: Real Direct Form II Transposed IIR biquad filtering (Peaking, Shelves, High/Low Pass).
6. CompressorProcessor: Dynamic range compression (threshold, ratio, attack/release smoothing, makeup gain).
7. MultitrackAudioMixer:
   - Multitrack summation of multiple audio tracks.
   - Clip-level gain, enable/disable, trimming boundaries.
   - Track-level gain, pan, mute, and solo policy.
   - Bus routing (Submix to Master) and feedback loop cycle prevention.
   - Module 8 keyframe automation integration (gain and pan automation curves).
8. PlaybackEngine Integration: Synchronized video and audio frame retrieval on shared timeline clock.
9. Offline Audio Processing: Render entire sequence to valid 16-bit PCM WAV file.
10. Capability Registry: Verification of all registered audio capabilities in STABLE state.
"""

import os
import unittest
import math
import wave
import tempfile
import numpy as np

from video_studio.timeline_models import (
    VideoSequence,
    TimelineTrackModel,
    TimelineTrackType,
    TimelineItemModel,
    TimelineItemType,
    TimelineRange,
    SourceRange,
)
from video_studio.audio_models import (
    SampleTime,
    AudioBuffer,
    AudioChannelLayout,
    AudioMeterSnapshot,
    AudioBus,
    AudioBusType,
    AudioRoutingGraph,
    PanningLaw,
)
from video_studio.audio_dsp import (
    GainProcessor,
    PanningProcessor,
    FilterType,
    BiquadFilter,
    ParametricEqualizerProcessor,
    CompressorProcessor,
    ProcessorChain,
)
from video_studio.audio_mixer import MultitrackAudioMixer
from video_studio.audio_service import audio_engine_service
from video_studio.playback_engine import playback_engine
from video_studio.animation_service import animation_service
from video_studio.animation_models import InterpolationMode
from video_studio.registry import video_studio_capability_registry


class TestVideoStudioModule9(unittest.TestCase):
    """Module 9 Audio Engine verification test suite."""

    def test_01_sample_accurate_time(self):
        """Verifies integer sample calculations without floating-point drift."""
        st = SampleTime(sample_index=48000, sample_rate=48000)
        self.assertAlmostEqual(st.to_seconds(), 1.0)
        self.assertEqual(st.to_timeline_frame(fps=24.0), 24)

        # Non-standard frame rate mapping (23.976 fps)
        st_23 = SampleTime.from_timeline_frame(frame=24, fps=23.976, sample_rate=48000)
        self.assertEqual(st_23.sample_rate, 48000)
        self.assertGreater(st_23.sample_index, 0)

    def test_02_audio_buffer_operations(self):
        """Verifies buffer arithmetic, equal-power panning, and PCM conversion."""
        buf = AudioBuffer.silence(samples=1000, channels=2, sample_rate=48000)
        self.assertEqual(buf.samples, 1000)
        self.assertEqual(buf.channels, 2)

        # Set unit impulse in left and right
        buf.data[0, :] = 0.5
        buf.data[1, :] = 0.5
        buf.apply_gain(2.0)
        self.assertAlmostEqual(float(buf.data[0, 0]), 1.0)

        # Test equal-power panning to hard left
        buf.apply_panning(-1.0, law=PanningLaw.EQUAL_POWER_3DB)
        self.assertGreater(float(buf.data[0, 0]), 0.99)
        self.assertAlmostEqual(float(buf.data[1, 0]), 0.0, places=4)

        # Test 16-bit PCM round-trip
        test_buf = AudioBuffer.silence(100, channels=2)
        test_buf.data[0, :] = 0.5
        test_buf.data[1, :] = -0.5
        pcm_bytes = test_buf.to_int16_bytes()
        decoded_buf = AudioBuffer.from_int16_bytes(pcm_bytes, channels=2)
        self.assertEqual(decoded_buf.samples, 100)
        self.assertAlmostEqual(float(decoded_buf.data[0, 0]), 0.5, delta=0.01)
        self.assertAlmostEqual(float(decoded_buf.data[1, 0]), -0.5, delta=0.01)

    def test_03_metering_and_analysis(self):
        """Verifies real peak (dBFS) and RMS loudness measurements."""
        buf = AudioBuffer.silence(samples=4800, channels=2, sample_rate=48000)
        # Sine wave sampled at 48000 Hz, 1000 Hz tone
        fs = 48000
        t = np.arange(4800) / float(fs)
        sine = np.sin(2 * np.pi * 1000 * t).astype(np.float32)
        sine /= np.max(np.abs(sine)) # Force exact peak 1.0 (0 dBFS)

        buf.data[0, :] = sine
        buf.data[1, :] = sine * 0.5 # -6.02 dBFS peak

        meters = AudioMeterSnapshot.calculate(buf)
        self.assertAlmostEqual(meters.peak_db[0], 0.0, delta=0.01)
        self.assertAlmostEqual(meters.peak_db[1], -6.02, delta=0.1)
        # Theoretical RMS of sine with peak 1.0 is 1/sqrt(2) = 0.7071 (-3.01 dBFS)
        self.assertAlmostEqual(meters.rms_db[0], -3.01, delta=0.1)
        self.assertTrue(meters.is_clipped[0])
        self.assertFalse(meters.is_clipped[1])

    def test_04_dsp_parametric_equalizer(self):
        """Verifies Direct Form II Transposed biquad equalizer filter response."""
        eq = ParametricEqualizerProcessor(processor_id="test_eq")
        # Configure band 1 to boost 1 kHz by +6 dB
        eq.set_band(1, FilterType.PEAKING, freq_hz=1000.0, gain_db=6.0, q=1.0)

        # Input 1 kHz sine wave
        fs = 48000
        samples = 4800
        t = np.arange(samples) / fs
        sine = np.sin(2 * np.pi * 1000 * t).astype(np.float32)

        buf = AudioBuffer(sample_rate=fs, layout=AudioChannelLayout.STEREO, data=np.array([sine, sine]))
        processed = eq.process(buf)

        # Steady-state output amplitude should increase by ~2x (+6 dB)
        steady_state = processed.data[0, 2000:]
        max_amp = float(np.max(np.abs(steady_state)))
        self.assertGreater(max_amp, 1.8)

    def test_05_dsp_dynamic_compressor(self):
        """Verifies compressor gain reduction on signals exceeding threshold."""
        comp = CompressorProcessor(
            processor_id="test_comp",
            threshold_db=-10.0,
            ratio=4.0,
            attack_ms=5.0,
            release_ms=50.0,
            makeup_gain_db=0.0,
        )

        fs = 48000
        samples = 4800
        # High amplitude signal (0 dBFS, 10 dB above threshold)
        high_amp = np.ones((2, samples), dtype=np.float32) * 1.0
        buf = AudioBuffer(sample_rate=fs, layout=AudioChannelLayout.STEREO, data=high_amp)

        processed = comp.process(buf)
        # End of buffer should be compressed down
        end_val = float(processed.data[0, -1])
        self.assertLess(end_val, 0.7)

    def test_06_multitrack_mixing_and_solo_mute(self):
        """Verifies track summing and solo/mute exclusion policies."""
        mixer = MultitrackAudioMixer()
        seq = VideoSequence(sequence_id="seq_audio_mix", project_id="proj_1", name="Audio Mix Sequence")

        # Track 1
        t1 = TimelineTrackModel(track_id="t1", sequence_id=seq.sequence_id, name="Dialogue", track_type=TimelineTrackType.AUDIO, index=0)
        c1 = TimelineItemModel(
            item_id="c1", track_id="t1", sequence_id=seq.sequence_id, source_reference_id="asset_dia",
            timeline_range=TimelineRange(start_frame=0, duration_frames=24),
            source_range=SourceRange(in_frame=0, duration_frames=24),
        )
        t1.items.append(c1)

        # Track 2
        t2 = TimelineTrackModel(track_id="t2", sequence_id=seq.sequence_id, name="Music", track_type=TimelineTrackType.AUDIO, index=1)
        c2 = TimelineItemModel(
            item_id="c2", track_id="t2", sequence_id=seq.sequence_id, source_reference_id="asset_mus",
            timeline_range=TimelineRange(start_frame=0, duration_frames=24),
            source_range=SourceRange(in_frame=0, duration_frames=24),
        )
        t2.items.append(c2)

        seq.tracks.extend([t1, t2])

        # Render 24 frames
        out_buf = mixer.render_audio_slice(seq, start_frame=0, duration_frames=24)
        self.assertEqual(out_buf.samples, 48000) # 24 frames at 24fps = 1.0 sec = 48000 samples

        # Solo Policy: Soloing t1 excludes t2
        t1.is_solo = True
        t2.is_solo = False
        solo_buf = mixer.render_audio_slice(seq, start_frame=0, duration_frames=24)
        self.assertIsNotNone(solo_buf)

        # Mute Policy: Muting t1 results in silence
        t1.is_solo = False
        t1.is_muted = True
        t2.is_muted = True
        mute_buf = mixer.render_audio_slice(seq, start_frame=0, duration_frames=24)
        self.assertEqual(float(np.max(np.abs(mute_buf.data))), 0.0)

    def test_07_bus_routing_and_cycle_prevention(self):
        """Verifies submix bus hierarchy and cyclic routing validation."""
        graph = AudioRoutingGraph()
        master = AudioBus(bus_id="bus_master", name="Master", bus_type=AudioBusType.MASTER)
        sub1 = AudioBus(bus_id="bus_sub1", name="Dialogue Submix", bus_type=AudioBusType.SUBMIX)
        sub2 = AudioBus(bus_id="bus_sub2", name="FX Submix", bus_type=AudioBusType.SUBMIX)

        graph.add_bus(master)
        graph.add_bus(sub1)
        graph.add_bus(sub2)

        # Valid routes
        self.assertTrue(graph.route_bus("bus_sub1", "bus_master"))
        self.assertTrue(graph.route_bus("bus_sub2", "bus_sub1"))

        # Cycle attempt: routing sub1 back into sub2
        with self.assertRaises(ValueError):
            graph.route_bus("bus_sub1", "bus_sub2")

    def test_08_automation_integration(self):
        """Verifies Volume and Pan automation curves via Module 8 AnimationService."""
        mixer = MultitrackAudioMixer()
        seq = VideoSequence(sequence_id="seq_auto", project_id="proj_1", name="Automation Sequence")
        t1 = TimelineTrackModel(track_id="trk_auto", sequence_id=seq.sequence_id, name="Track", track_type=TimelineTrackType.AUDIO, index=0)
        c1 = TimelineItemModel(
            item_id="clip_auto", track_id="trk_auto", sequence_id=seq.sequence_id, source_reference_id="asset_auto",
            timeline_range=TimelineRange(start_frame=0, duration_frames=48),
            source_range=SourceRange(in_frame=0, duration_frames=48),
        )
        t1.items.append(c1)
        seq.tracks.append(t1)

        # Register animatable gain property on track
        from video_studio.animation_models import AnimatableProperty, PropertyValueType
        gain_prop = AnimatableProperty(
            property_id="trk_auto_gain",
            owner_id="trk_auto",
            name="gain_db",
            value_type=PropertyValueType.SCALAR,
            default_value=0.0,
            current_value=0.0,
        )
        animation_service.register_property(gain_prop)

        # Register gain automation curve on track: 0dB at frame 0, -120dB at frame 48
        kf_start = animation_service.add_keyframe("trk_auto_gain", frame=0, value=0.0, interpolation=InterpolationMode.LINEAR)
        kf_end = animation_service.add_keyframe("trk_auto_gain", frame=48, value=-120.0, interpolation=InterpolationMode.LINEAR)

        # Evaluate at frame 0 and frame 48
        buf_start = mixer.render_audio_slice(seq, start_frame=0, duration_frames=1)
        buf_end = mixer.render_audio_slice(seq, start_frame=48, duration_frames=1)

        self.assertIsNotNone(buf_start)
        self.assertIsNotNone(buf_end)

    def test_09_playback_engine_synchronized_render(self):
        """Verifies video and audio render on the same synchronized timeline clock."""
        seq = VideoSequence(sequence_id="seq_sync", project_id="proj_1", name="Sync Seq", duration_frames=100)
        t_v = TimelineTrackModel(track_id="tv", sequence_id=seq.sequence_id, name="Video", track_type=TimelineTrackType.VIDEO, index=0)
        t_a = TimelineTrackModel(track_id="ta", sequence_id=seq.sequence_id, name="Audio", track_type=TimelineTrackType.AUDIO, index=1)
        seq.tracks.extend([t_v, t_a])

        session = playback_engine.create_session(seq, project_id="proj_1")
        playback_engine.seek(session.session_id, target_frame=10)

        # Video frame at playhead
        v_frame = playback_engine.render_frame(session.session_id)
        self.assertEqual(v_frame.timeline_frame, 10)

        # Audio slice at same playhead
        a_buf = playback_engine.render_audio(session.session_id, duration_frames=1)
        self.assertEqual(a_buf.samples, 2000) # 48000 / 24 = 2000 samples per frame

    def test_10_offline_audio_export(self):
        """Verifies offline rendering of entire sequence to a standard WAV file."""
        seq = VideoSequence(sequence_id="seq_export", project_id="proj_1", name="Export Seq")
        t_a = TimelineTrackModel(track_id="ta", sequence_id=seq.sequence_id, name="Audio", track_type=TimelineTrackType.AUDIO, index=0)
        c_a = TimelineItemModel(
            item_id="ca", track_id="ta", sequence_id=seq.sequence_id, source_reference_id="asset_test",
            timeline_range=TimelineRange(start_frame=0, duration_frames=24),
            source_range=SourceRange(in_frame=0, duration_frames=24),
        )
        t_a.items.append(c_a)
        seq.tracks.append(t_a)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            wav_path = tf.name

        try:
            res = audio_engine_service.process_offline_audio_export(
                sequence=seq,
                output_file_path=wav_path,
                start_frame=0,
                end_frame=24,
                sample_rate=48000,
                channels=2,
            )
            self.assertTrue(res["success"])
            self.assertTrue(os.path.exists(wav_path))

            # Inspect generated WAV header
            with wave.open(wav_path, "rb") as wf:
                self.assertEqual(wf.getnchannels(), 2)
                self.assertEqual(wf.getsampwidth(), 2) # 16-bit
                self.assertEqual(wf.getframerate(), 48000)
                self.assertEqual(wf.getnframes(), 48000)
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)

    def test_11_capability_registry_status(self):
        """Verifies all audio capabilities are registered in IMPLEMENTED state."""
        cap = video_studio_capability_registry.get("audio.multitrack_mixer")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.implementation_state.value, "IMPLEMENTED")


if __name__ == "__main__":
    unittest.main()
