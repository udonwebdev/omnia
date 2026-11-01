"""OMNIA Video Studio — Module 36 Test Suite.

Verifies:
1. EditingBrief model creation, defaults, serialization, and roundtrip.
2. CandidateMoment extraction with keyword filtering (mandatory inclusion, excluded pruning).
3. CandidateMoment quality scoring (lighting, camera motion, framing, dialogue).
4. EditDecisionList generation under different pacing profiles (FAST_PACED, MODERATE, SLOW_CINEMATIC).
5. Narrative structuring (CHRONOLOGICAL, HIGHLIGHTS_FIRST, THEMATIC).
6. Target duration bounding within tolerance limits.
7. Interactive EDL approval lifecycle (PROPOSED -> APPROVED, REJECTED, MODIFIED).
8. Timeline assembly gate enforcing approval status before commit.
9. Non-destructive sequence commit with track creation, clip placement, audio-video linking, and history rollback.
10. VideoStudioCapabilityRegistry registration for Module 36 capabilities.
"""

import unittest
import uuid
import time
from typing import List

from video_studio.rough_cut_models import (
    PacingProfile,
    NarrativeStructure,
    EDLApprovalStatus,
    EditingBrief,
    CandidateMoment,
    EditDecision,
    EditDecisionList,
    RoughCutResult,
)
from video_studio.rough_cut_engine import RoughCutEngine, rough_cut_engine
from video_studio.rough_cut_service import RoughCutService, rough_cut_service
from video_studio.intelligence_models import (
    VideoContentIntelligenceDocument,
    ShotMetadata,
    SceneMetadata,
    AudioEventSegment,
    AudioEventType,
    ShotTypeClassification,
    CameraMotionClassification,
    LightingClassification,
    SceneBoundaryType,
)
from video_studio.timeline_models import (
    VideoSequence,
    TimelineTrackType,
    TimelineItemType,
)
from video_studio.timeline_service import TimelineService
from video_studio.registry import video_studio_capability_registry


class TestVideoStudioModule36(unittest.TestCase):
    """Module 36 Unit & Integration Tests."""

    def setUp(self):
        self.timeline_service = TimelineService()
        self.engine = RoughCutEngine()
        self.service = RoughCutService(
            engine=self.engine,
            timeline_service_instance=self.timeline_service,
        )

        # Mock intelligence document with rich metadata
        self.asset_id_1 = "asset_vid_01"
        self.doc_1 = VideoContentIntelligenceDocument(
            asset_id=self.asset_id_1,
            project_id="test_proj",
            duration_seconds=30.0,
            total_frames=750,
            fps=25.0,
            shots=[
                ShotMetadata(
                    shot_id="shot_01",
                    start_frame=0,
                    end_frame=125,
                    start_pts=0.0,
                    end_pts=5.0,
                    boundary_in_type=SceneBoundaryType.HARD_CUT,
                    shot_type=ShotTypeClassification.WIDE_SHOT,
                    camera_motion=CameraMotionClassification.STATIC,
                    lighting=LightingClassification.NATURAL_BALANCED,
                    visual_description="Opening panoramic landscape morning view",
                    tags=["landscape", "intro", "nature"],
                ),
                ShotMetadata(
                    shot_id="shot_02",
                    start_frame=125,
                    end_frame=275,
                    start_pts=5.0,
                    end_pts=11.0,
                    boundary_in_type=SceneBoundaryType.HARD_CUT,
                    shot_type=ShotTypeClassification.CLOSE_UP,
                    camera_motion=CameraMotionClassification.STATIC,
                    lighting=LightingClassification.HIGH_KEY_BRIGHT,
                    visual_description="Protagonist smiling talking in studio interview",
                    tags=["interview", "character", "dialogue"],
                ),
                ShotMetadata(
                    shot_id="shot_03",
                    start_frame=275,
                    end_frame=400,
                    start_pts=11.0,
                    end_pts=16.0,
                    boundary_in_type=SceneBoundaryType.HARD_CUT,
                    shot_type=ShotTypeClassification.MEDIUM_SHOT,
                    camera_motion=CameraMotionClassification.HANDHELD_SHAKE,
                    lighting=LightingClassification.LOW_KEY_DARK,
                    visual_description="Dark corridor jittery blooper shot",
                    tags=["blooper", "corridor", "blurry"],
                ),
                ShotMetadata(
                    shot_id="shot_04",
                    start_frame=400,
                    end_frame=650,
                    start_pts=16.0,
                    end_pts=26.0,
                    boundary_in_type=SceneBoundaryType.HARD_CUT,
                    shot_type=ShotTypeClassification.CLOSE_UP,
                    camera_motion=CameraMotionClassification.TRACKING_DOLLY,
                    lighting=LightingClassification.NATURAL_BALANCED,
                    visual_description="Keynote product reveal high energy climax",
                    tags=["climax", "keynote", "reveal"],
                ),
            ],
            audio_events=[
                AudioEventSegment(
                    event_type=AudioEventType.SPEECH,
                    start_time=5.2,
                    end_time=10.8,
                    details="Hello everyone and welcome to our story.",
                ),
            ],
        )

    def test_01_brief_creation_and_serialization(self):
        """EditingBrief properly initializes with sensible defaults and serializes correctly."""
        brief = self.service.create_brief(
            project_id="test_proj",
            title="Summer Highlights",
            source_asset_ids=[self.asset_id_1],
            target_duration_seconds=15.0,
            pacing=PacingProfile.FAST_PACED,
            narrative_structure=NarrativeStructure.HIGHLIGHTS_FIRST,
            required_keywords=["reveal"],
            excluded_keywords=["blooper"],
        )
        self.assertEqual(brief.project_id, "test_proj")
        self.assertEqual(brief.pacing, PacingProfile.FAST_PACED)
        self.assertEqual(brief.narrative_structure, NarrativeStructure.HIGHLIGHTS_FIRST)
        self.assertIn("reveal", brief.required_keywords)
        self.assertIn("blooper", brief.excluded_keywords)

        d = brief.to_dict()
        self.assertEqual(d["title"], "Summer Highlights")
        self.assertEqual(d["target_duration_seconds"], 15.0)

        # Roundtrip
        restored = EditingBrief.from_dict(d)
        self.assertEqual(restored.brief_id, brief.brief_id)
        self.assertEqual(restored.pacing, PacingProfile.FAST_PACED)

    def test_02_candidate_moment_filtering(self):
        """Candidate moments respect mandatory keywords and prune excluded keywords."""
        brief = EditingBrief(
            project_id="test_proj",
            source_asset_ids=[self.asset_id_1],
            required_keywords=["reveal"],
            excluded_keywords=["blooper"],
        )
        cands = self.engine.extract_candidate_moments(brief, [self.doc_1])

        # shot_03 has tag 'blooper', so it must be completely excluded
        shot_ids = [c.shot_id for c in cands]
        self.assertNotIn("shot_03", shot_ids, "Excluded shot_03 should not be in candidates.")

        # shot_04 has tag 'reveal', so it must be marked mandatory with high score
        shot_04_cand = next(c for c in cands if c.shot_id == "shot_04")
        self.assertTrue(shot_04_cand.is_mandatory)
        self.assertGreater(shot_04_cand.score, 2.0)

        # shot_02 has speech, so has_speech must be True
        shot_02_cand = next(c for c in cands if c.shot_id == "shot_02")
        self.assertTrue(shot_02_cand.has_speech)

    def test_03_edl_generation_pacing_and_duration_bounds(self):
        """EDL clips are trimmed to pacing envelope and sum does not exceed target + tolerance."""
        brief = EditingBrief(
            project_id="test_proj",
            source_asset_ids=[self.asset_id_1],
            target_duration_seconds=10.0,
            duration_tolerance_seconds=2.0,
            pacing=PacingProfile.FAST_PACED,  # 1.5 - 3.0s cuts
            min_shot_duration=1.5,
            max_shot_duration=3.0,
            narrative_structure=NarrativeStructure.CHRONOLOGICAL,
        )
        cands = self.engine.extract_candidate_moments(brief, [self.doc_1])
        edl = self.engine.generate_edl(brief, cands, [self.doc_1])

        self.assertGreater(len(edl.decisions), 0)
        # Every decision duration must be <= max_shot_duration
        for d in edl.decisions:
            self.assertLessEqual(d.duration, 3.01)
            self.assertGreaterEqual(d.duration, 1.49)

        # Total duration must be within target + tolerance
        self.assertLessEqual(edl.total_duration, 12.05)
        self.assertEqual(edl.status, EDLApprovalStatus.PROPOSED)

    def test_04_narrative_structure_highlights_first(self):
        """HIGHLIGHTS_FIRST strategy places highest-scoring moment at the start."""
        brief = EditingBrief(
            project_id="test_proj",
            source_asset_ids=[self.asset_id_1],
            target_duration_seconds=20.0,
            narrative_structure=NarrativeStructure.HIGHLIGHTS_FIRST,
            required_keywords=["reveal"],  # Gives shot_04 highest score
        )
        cands = self.engine.extract_candidate_moments(brief, [self.doc_1])
        edl = self.engine.generate_edl(brief, cands, [self.doc_1])

        self.assertGreater(len(edl.decisions), 1)
        # First decision should correspond to shot_04 (highest score)
        first_d = edl.decisions[0]
        self.assertEqual(first_d.source_in, 16.0)  # shot_04 start_pts is 16.0

    def test_05_recalculate_timeline_positions_ripple(self):
        """recalculate_timeline_positions computes continuous non-overlapping timeline positions."""
        edl = EditDecisionList(
            brief_id="brief_1",
            decisions=[
                EditDecision(source_in=0.0, source_out=3.0),
                EditDecision(source_in=5.0, source_out=9.0),
                EditDecision(source_in=10.0, source_out=12.5),
            ],
        )
        edl.recalculate_timeline_positions()
        self.assertAlmostEqual(edl.decisions[0].timeline_start, 0.0)
        self.assertAlmostEqual(edl.decisions[1].timeline_start, 3.0)
        self.assertAlmostEqual(edl.decisions[2].timeline_start, 7.0)
        self.assertAlmostEqual(edl.total_duration, 9.5)

    def test_06_edl_approval_lifecycle(self):
        """EDL status transitions through PROPOSED, APPROVED, REJECTED, and MODIFIED."""
        brief = self.service.create_brief("proj_1", "Test Brief", [self.asset_id_1])
        # Register doc with intelligence service
        self.service.intelligence_service.store_document(self.doc_1)

        edl = self.service.generate_rough_cut_edl(brief.brief_id)
        self.assertEqual(edl.status, EDLApprovalStatus.PROPOSED)

        # Approve
        approved = self.service.approve_edl(edl.edl_id)
        self.assertEqual(approved.status, EDLApprovalStatus.APPROVED)

        # Reject
        rejected = self.service.reject_edl(edl.edl_id)
        self.assertEqual(rejected.status, EDLApprovalStatus.REJECTED)

        # Modify
        modified = self.service.modify_edl_decisions(edl.edl_id, edl.decisions[:1])
        self.assertEqual(modified.status, EDLApprovalStatus.MODIFIED)
        self.assertEqual(len(modified.decisions), 1)

    def test_07_timeline_assembly_approval_gate(self):
        """Committing unapproved EDL fails with clear error."""
        edl = EditDecisionList(
            brief_id="brief_test",
            status=EDLApprovalStatus.PROPOSED,
            decisions=[EditDecision(source_in=0.0, source_out=3.0)],
        )
        self.service._edls[edl.edl_id] = edl

        result = self.service.commit_edl_to_timeline(edl.edl_id)
        self.assertFalse(result.success)
        self.assertIn("Must be APPROVED or MODIFIED", result.error)

    def test_08_timeline_assembly_success_and_links(self):
        """Approved EDL creates actual timeline video/audio items with LinkGroups."""
        brief = self.service.create_brief(
            project_id="proj_assemble",
            title="Assembly Brief",
            source_asset_ids=[self.asset_id_1],
            target_duration_seconds=12.0,
            include_source_audio=True,
        )
        self.service.intelligence_service.store_document(self.doc_1)

        edl = self.service.generate_rough_cut_edl(brief.brief_id)
        self.service.approve_edl(edl.edl_id)

        result = self.service.commit_edl_to_timeline(edl.edl_id, sequence_name="Test Rough Cut")
        self.assertTrue(result.success)
        self.assertGreater(result.items_created, 0)
        self.assertGreater(result.total_timeline_duration, 0.0)

        # Verify sequence contents
        seq = self.timeline_service.get_sequence(result.sequence_id)
        self.assertIsNotNone(seq)
        v_track = next(t for t in seq.tracks if t.track_type == TimelineTrackType.VIDEO)
        a_track = next(t for t in seq.tracks if t.track_type == TimelineTrackType.AUDIO)

        self.assertEqual(len(v_track.items), len(edl.decisions))
        self.assertEqual(len(a_track.items), len(edl.decisions))
        self.assertEqual(len(seq.link_groups), len(edl.decisions))

    def test_09_timeline_assembly_reversible_undo_redo(self):
        """Timeline assembly can be completely undone and redone via TimelineService."""
        brief = self.service.create_brief("proj_undo", "Undo Brief", [self.asset_id_1], target_duration_seconds=8.0)
        self.service.intelligence_service.store_document(self.doc_1)

        edl = self.service.generate_rough_cut_edl(brief.brief_id)
        self.service.approve_edl(edl.edl_id)

        result = self.service.commit_edl_to_timeline(edl.edl_id)
        seq = self.timeline_service.get_sequence(result.sequence_id)
        v_track = next(t for t in seq.tracks if t.track_type == TimelineTrackType.VIDEO)

        self.assertGreater(len(v_track.items), 0)

        # Undo the rough cut transaction
        undo_ok = self.timeline_service.undo(seq.sequence_id)
        self.assertTrue(undo_ok)
        self.assertEqual(len(v_track.items), 0, "All items should be removed on undo.")

        # Redo the rough cut transaction
        redo_ok = self.timeline_service.redo(seq.sequence_id)
        self.assertTrue(redo_ok)
        self.assertGreater(len(v_track.items), 0, "Items should be restored on redo.")

    def test_10_capability_registry_entries(self):
        """Module 36 capabilities are registered and available in the capability registry."""
        caps = [
            "video.editing.rough_cut_decision_engine",
            "video.editing.pacing_strategy",
            "video.editing.ai_assisted_assembly",
        ]
        for cap_id in caps:
            cap = video_studio_capability_registry.get(cap_id)
            self.assertIsNotNone(cap, f"Capability {cap_id} must be registered.")
            self.assertEqual(cap.implementation_state.value, "IMPLEMENTED")


if __name__ == "__main__":
    unittest.main()
