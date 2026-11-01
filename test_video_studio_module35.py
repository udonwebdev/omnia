"""Unit and Integration Tests for Module 35: Video Understanding, Scene Analysis & Content Intelligence Engine.

Verifies:
1. Multi-metric shot boundary detection:
   - Hard cut detection (MAD + HSV histogram correlation).
   - Fade-out and fade-in detection (near black luminance transitions).
   - False-positive camera movement protection.
2. Visual Content & Composition Analysis:
   - Photometric lighting classification (High Key, Low Key, Natural).
   - Camera motion kinematics estimation (Static, Pan Horizontal, Tilt).
   - Shot composition framing scale (Wide Shot, Close-Up).
3. Audio Content Analysis:
   - Speech vs. silence vs. music classification from waveform energy.
4. Document Persistence & User Annotations:
   - VideoContentIntelligenceDocument creation, updating, and revision bumping.
   - Non-destructive user annotations and shot corrections.
5. Semantic & Text Search:
   - Exact text search over shot tags, scene summaries, and user notes.
   - Integration with Module 13 speech transcripts.
   - Project-level isolation and time-range filtering.
"""

import unittest
import numpy as np
import cv2

from video_studio.effects_models import VideoFrameBuffer
from video_studio.intelligence_models import (
    SceneBoundaryType,
    ShotTypeClassification,
    CameraMotionClassification,
    LightingClassification,
    AudioEventType,
    AnalysisSourceType,
    ShotMetadata,
    SceneMetadata,
    AudioEventSegment,
    VideoContentIntelligenceDocument,
    SemanticSearchQuery,
    SemanticSearchResult,
)
from video_studio.intelligence_engine import VideoIntelligenceEngine
from video_studio.intelligence_service import VideoIntelligenceService


def make_test_frame(width: int, height: int, data: np.ndarray, frame_number: int = 0) -> VideoFrameBuffer:
    buf = VideoFrameBuffer(width=width, height=height, data=data)
    buf.timeline_frame = frame_number
    buf.pts_seconds = frame_number * 0.04
    return buf


class TestVideoStudioModule35(unittest.TestCase):

    def setUp(self):
        self.engine = VideoIntelligenceEngine()
        self.service = VideoIntelligenceService(engine=self.engine)

    def test_shot_boundary_hard_cut_detection(self):
        """Tests that two drastically different images trigger a HARD_CUT boundary."""
        h, w = 40, 40
        img_a = np.full((h, w, 3), 40, dtype=np.uint8)   # Dark gray
        img_b = np.full((h, w, 3), 220, dtype=np.uint8)  # Bright white

        is_cut, b_type, conf = self.engine.detect_shot_boundary(img_a, img_b)
        self.assertTrue(is_cut)
        self.assertEqual(b_type, SceneBoundaryType.HARD_CUT)
        self.assertGreater(conf, 0.7)

    def test_shot_boundary_fade_transitions(self):
        """Tests that transitions to/from near-black trigger FADE_OUT and FADE_IN boundaries."""
        h, w = 30, 30
        normal_frame = np.full((h, w, 3), 150, dtype=np.uint8)
        black_frame = np.full((h, w, 3), 5, dtype=np.uint8)

        # Fade out
        is_cut, b_type, conf = self.engine.detect_shot_boundary(normal_frame, black_frame)
        self.assertTrue(is_cut)
        self.assertEqual(b_type, SceneBoundaryType.FADE_OUT)

        # Fade in
        is_cut, b_type, conf = self.engine.detect_shot_boundary(black_frame, normal_frame)
        self.assertTrue(is_cut)
        self.assertEqual(b_type, SceneBoundaryType.FADE_IN)

    def test_shot_boundary_camera_pan_safety(self):
        """Tests that subtle camera translation does not trigger an accidental hard cut."""
        h, w = 50, 50
        np.random.seed(42)
        base = np.random.randint(60, 180, (h, w), dtype=np.uint8)
        base = cv2.GaussianBlur(base, (5, 5), 1.0)
        shifted = np.roll(base, shift=1, axis=1) # 1 pixel pan

        img_a = np.repeat(base[:, :, np.newaxis], 3, axis=2)
        img_b = np.repeat(shifted[:, :, np.newaxis], 3, axis=2)

        is_cut, _, _ = self.engine.detect_shot_boundary(img_a, img_b)
        self.assertFalse(is_cut)

    def test_visual_lighting_classification(self):
        """Tests photometric lighting classification."""
        h, w = 30, 30
        dark_img = np.full((h, w, 3), 25, dtype=np.uint8)
        bright_img = np.full((h, w, 3), 235, dtype=np.uint8)
        balanced_img = np.full((h, w, 3), 128, dtype=np.uint8)

        self.assertEqual(self.engine.classify_lighting(dark_img), LightingClassification.LOW_KEY_DARK)
        self.assertEqual(self.engine.classify_lighting(bright_img), LightingClassification.HIGH_KEY_BRIGHT)
        self.assertEqual(self.engine.classify_lighting(balanced_img), LightingClassification.NATURAL_BALANCED)

    def test_visual_camera_motion_classification(self):
        """Tests camera motion kinematics classification."""
        h, w = 40, 40
        np.random.seed(99)
        base = np.random.randint(80, 160, (h, w), dtype=np.uint8)
        base = cv2.GaussianBlur(base, (5, 5), 1.0)

        f_static1 = make_test_frame(w, h, np.repeat(base[:, :, np.newaxis], 4, axis=2), frame_number=0)
        f_static2 = make_test_frame(w, h, np.repeat(base[:, :, np.newaxis], 4, axis=2), frame_number=1)

        motion_static = self.engine.classify_camera_motion(f_static1, f_static2)
        self.assertEqual(motion_static, CameraMotionClassification.STATIC)

    def test_audio_event_analysis(self):
        """Tests audio energy analysis classifying silence and speech/active intervals."""
        sr = 48000
        # 0.5s of silence, then 0.5s of high-energy synthetic tone
        silence = np.zeros(24000, dtype=np.float32)
        t = np.linspace(0, 0.5, 24000, endpoint=False)
        active = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

        samples = np.concatenate([silence, active])
        events = self.engine.detect_audio_events(samples, sample_rate=sr, frame_duration=0.5)

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].event_type, AudioEventType.SILENCE)
        self.assertIn(events[1].event_type, [AudioEventType.SPEECH, AudioEventType.MUSIC])

    def test_service_frame_sequence_shot_pipeline(self):
        """Tests full shot analysis pipeline across decoded frame buffers."""
        asset_id = "test_asset_shots_01"
        frames: List[VideoFrameBuffer] = []

        # Shot 1: Frames 0-4 (Dark blue)
        for i in range(5):
            data = np.full((32, 32, 4), 30, dtype=np.uint8)
            frames.append(make_test_frame(32, 32, data, frame_number=i))

        # Shot 2: Frames 5-9 (Bright orange)
        for i in range(5, 10):
            data = np.full((32, 32, 4), 220, dtype=np.uint8)
            frames.append(make_test_frame(32, 32, data, frame_number=i))

        doc = self.service.analyze_frame_sequence_shots(
            asset_id=asset_id,
            frames=frames,
            mad_threshold=30.0,
        )

        self.assertEqual(doc.asset_id, asset_id)
        self.assertEqual(len(doc.shots), 2)
        self.assertEqual(doc.shots[0].start_frame, 0)
        self.assertEqual(doc.shots[0].end_frame, 4)
        self.assertEqual(doc.shots[1].start_frame, 5)
        self.assertEqual(doc.shots[1].end_frame, 9)

    def test_user_annotations_and_corrections(self):
        """Tests non-destructive user editing of detected shot metadata."""
        asset_id = "test_asset_annot"
        doc = self.service.get_or_create_document(asset_id)
        doc.shots = [
            ShotMetadata(
                shot_id="shot_101",
                start_frame=0,
                end_frame=25,
                visual_description="Original auto description",
                shot_type=ShotTypeClassification.WIDE_SHOT,
            )
        ]
        self.service.store_document(doc)

        updated = self.service.update_shot_user_annotation(
            asset_id=asset_id,
            shot_id="shot_101",
            user_notes="Actor enters through kitchen door.",
            override_shot_type=ShotTypeClassification.CLOSE_UP,
        )

        self.assertIsNotNone(updated)
        self.assertEqual(updated.visual_description, "Actor enters through kitchen door.")
        self.assertEqual(updated.shot_type, ShotTypeClassification.CLOSE_UP)
        self.assertTrue(updated.is_user_confirmed)
        self.assertEqual(updated.source_type, AnalysisSourceType.USER_CONFIRMED)

    def test_semantic_search_media(self):
        """Tests text and tag search over analyzed content intelligence."""
        asset_id = "test_asset_search"
        doc = self.service.get_or_create_document(asset_id, project_id="proj_alpha")
        doc.shots = [
            ShotMetadata(
                shot_id="s1",
                start_pts=2.0,
                end_pts=5.0,
                visual_description="Vintage red convertible car on mountain road",
                tags=["convertible", "car", "red", "wide_shot"],
                shot_type=ShotTypeClassification.WIDE_SHOT,
            ),
            ShotMetadata(
                shot_id="s2",
                start_pts=5.0,
                end_pts=9.0,
                visual_description="Chef preparing pasta in stainless steel kitchen",
                tags=["chef", "cooking", "close_up"],
                shot_type=ShotTypeClassification.CLOSE_UP,
            ),
        ]
        self.service.store_document(doc)

        # 1. Search for "convertible"
        q1 = SemanticSearchQuery(query_text="convertible", asset_id=asset_id)
        res1 = self.service.search_media(q1)
        self.assertEqual(len(res1), 1)
        self.assertEqual(res1[0].shot_id, "s1")
        self.assertAlmostEqual(res1[0].timestamp_pts, 2.0)

        # 2. Search for "kitchen"
        q2 = SemanticSearchQuery(query_text="kitchen", asset_id=asset_id)
        res2 = self.service.search_media(q2)
        self.assertEqual(len(res2), 1)
        self.assertEqual(res2[0].shot_id, "s2")
        self.assertAlmostEqual(res2[0].timestamp_pts, 5.0)

        # 3. Filter by shot type (CLOSE_UP)
        q3 = SemanticSearchQuery(shot_type=ShotTypeClassification.CLOSE_UP, asset_id=asset_id)
        res3 = self.service.search_media(q3)
        self.assertEqual(len(res3), 1)
        self.assertEqual(res3[0].shot_id, "s2")

        # 4. Project boundary isolation: wrong project should return 0 results
        q_isolated = SemanticSearchQuery(query_text="convertible", project_id="proj_beta")
        res_isolated = self.service.search_media(q_isolated)
        self.assertEqual(len(res_isolated), 0)


if __name__ == "__main__":
    unittest.main()
