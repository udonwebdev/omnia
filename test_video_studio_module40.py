"""OMNIA Video Studio — Module 40 Tests: Collaboration, Review & Annotation Engine.

Comprehensive test suite validating:
1. Review session creation, listing, retrieval, closing, and participant role checking.
2. Timestamped and time-range comments with duration bounds checking.
3. Normalized spatial region bounding-box validation (x, y, w, h in [0.0, 1.0]).
4. Threaded discussion replies and parent comment verification.
5. Comment resolution states (RESOLVED, REOPENED, WONT_FIX).
6. Non-destructive timeline marker projection from comments.
7. Revision tracking and stale comment detection against newer sequence edits.
8. Formal review decisions (APPROVED, CHANGES_REQUESTED, ABSTAIN) and aggregate status updates.
9. Security and authorization enforcement (preventing unauthorized comments, closes, or decisions).
10. Capability registration in VideoStudioCapabilityRegistry under COLLABORATION category.
"""

import os
import unittest
from video_studio.collaboration_models import (
    CommentResolutionState,
    NormalizedRegion,
    ParticipantRole,
    ReviewComment,
    ReviewDecision,
    ReviewDecisionType,
    ReviewSession,
    ReviewSessionStatus,
)
from video_studio.collaboration_engine import CollaborationEngine
from video_studio.collaboration_service import CollaborationService
from video_studio.registry import VideoStudioCapabilityRegistry
from video_studio.registry_models import ImplementationState, VideoStudioCategory
from video_studio.timeline_models import VideoSequence, TimelineTrackModel, TimelineTrackType


class TestVideoStudioModule40Collaboration(unittest.TestCase):
    """Test suite for Module 40 Collaboration Engine."""

    def setUp(self) -> None:
        self.audit_log = "test_collab_audit.jsonl"
        self.registry = VideoStudioCapabilityRegistry()
        self.service = CollaborationService(
            capability_registry=self.registry,
            audit_log_path=self.audit_log,
        )

    def tearDown(self) -> None:
        if os.path.exists(self.audit_log):
            try:
                os.remove(self.audit_log)
            except Exception:
                pass

    def test_01_session_lifecycle_and_participants(self) -> None:
        """Verifies review session creation, participant roles, and closing."""
        session = self.service.create_review_session(
            project_id="prj_alpha",
            sequence_id="seq_101",
            title="Rough Cut Review",
            created_by="director_dan",
            target_revision=2,
            description="Client review pass for ep 1",
            participants={
                "editor_ed": ParticipantRole.EDITOR,
                "client_claire": ParticipantRole.REVIEWER,
            },
        )
        self.assertIsNotNone(session.session_id)
        self.assertEqual(session.status, ReviewSessionStatus.OPEN)
        self.assertEqual(session.participants["director_dan"], ParticipantRole.OWNER)
        self.assertEqual(session.participants["editor_ed"], ParticipantRole.EDITOR)
        self.assertEqual(session.participants["client_claire"], ParticipantRole.REVIEWER)

        # Retrieve and list
        fetched = self.service.get_session(session.session_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.title, "Rough Cut Review")

        sessions = self.service.list_sessions(project_id="prj_alpha")
        self.assertEqual(len(sessions), 1)

        # Close session by owner
        closed_session = self.service.close_session(session.session_id, user_id="director_dan")
        self.assertEqual(closed_session.status, ReviewSessionStatus.CLOSED)
        self.assertEqual(closed_session.closed_by, "director_dan")

    def test_02_timestamped_and_range_comments(self) -> None:
        """Verifies point and duration-bounded comments across timeline time."""
        seq = VideoSequence(sequence_id="seq_101", project_id="prj_alpha", name="Test Sequence")
        seq.duration_frames = 120 * 24
        session = self.service.create_review_session(
            project_id="prj_alpha",
            sequence_id="seq_101",
            title="Timing Review",
            created_by="director_dan",
            participants={"client_claire": ParticipantRole.REVIEWER},
        )

        # Valid point comment
        c1 = self.service.add_comment(
            session_id=session.session_id,
            author_id="client_claire",
            content="Audio dip here",
            timestamp_seconds=15.5,
            sequence=seq,
        )
        self.assertFalse(c1.is_range())
        self.assertEqual(c1.timestamp_seconds, 15.5)

        # Valid range comment
        c2 = self.service.add_comment(
            session_id=session.session_id,
            author_id="client_claire",
            content="Color grading too warm over this speech",
            timestamp_seconds=20.0,
            end_timestamp_seconds=25.5,
            sequence=seq,
        )
        self.assertTrue(c2.is_range())
        self.assertEqual(c2.end_timestamp_seconds, 25.5)

        # Out-of-bounds rejection
        with self.assertRaises(ValueError):
            self.service.add_comment(
                session_id=session.session_id,
                author_id="client_claire",
                content="Past sequence end",
                timestamp_seconds=150.0,
                sequence=seq,
            )

        # Negative timestamp rejection
        with self.assertRaises(ValueError):
            self.service.add_comment(
                session_id=session.session_id,
                author_id="client_claire",
                content="Negative timestamp",
                timestamp_seconds=-2.0,
                sequence=seq,
            )

    def test_03_spatial_bounding_box_validation(self) -> None:
        """Verifies normalized rectangular regions [0.0, 1.0] and bounds enforcement."""
        session = self.service.create_review_session(
            project_id="prj_alpha",
            sequence_id="seq_101",
            title="Visual QC",
            created_by="director_dan",
        )

        valid_region = NormalizedRegion(x=0.1, y=0.2, width=0.3, height=0.4)
        c = self.service.add_comment(
            session_id=session.session_id,
            author_id="director_dan",
            content="Boom mic visible in upper corner",
            timestamp_seconds=5.0,
            region=valid_region,
        )
        self.assertIsNotNone(c.region)
        self.assertEqual(c.region.x, 0.1)

        # Negative coords
        with self.assertRaises(ValueError):
            NormalizedRegion(x=-0.1, y=0.0, width=0.5, height=0.5)

        # Dimension overflow (x + width > 1.0)
        with self.assertRaises(ValueError):
            NormalizedRegion(x=0.8, y=0.1, width=0.4, height=0.2)

        # Height overflow (y + height > 1.0)
        with self.assertRaises(ValueError):
            NormalizedRegion(x=0.1, y=0.9, width=0.2, height=0.3)

    def test_04_threaded_discussions(self) -> None:
        """Tests parent-child comment threading and reply hierarchies."""
        session = self.service.create_review_session(
            project_id="prj_alpha",
            sequence_id="seq_101",
            title="Note Discussion",
            created_by="director_dan",
            participants={"editor_ed": ParticipantRole.EDITOR},
        )

        c1 = self.service.add_comment(
            session_id=session.session_id,
            author_id="director_dan",
            content="Can we trim two frames off the head of this cut?",
            timestamp_seconds=10.0,
        )

        # Reply to c1
        reply = self.service.add_comment(
            session_id=session.session_id,
            author_id="editor_ed",
            content="Trimmed in revision 2, looks snappier now.",
            timestamp_seconds=10.0,
            parent_comment_id=c1.comment_id,
        )
        self.assertEqual(reply.parent_comment_id, c1.comment_id)
        self.assertEqual(len(session.comments), 2)

        # Invalid parent rejection
        with self.assertRaises(KeyError):
            self.service.add_comment(
                session_id=session.session_id,
                author_id="editor_ed",
                content="Ghost reply",
                timestamp_seconds=10.0,
                parent_comment_id="non-existent-comment-id",
            )

    def test_05_comment_resolution_workflow(self) -> None:
        """Tests comment resolution transitions and role permissions."""
        session = self.service.create_review_session(
            project_id="prj_alpha",
            sequence_id="seq_101",
            title="Fix Tracking",
            created_by="director_dan",
            participants={
                "editor_ed": ParticipantRole.EDITOR,
                "client_claire": ParticipantRole.REVIEWER,
            },
        )

        c = self.service.add_comment(
            session_id=session.session_id,
            author_id="director_dan",
            content="Adjust Foley sync",
            timestamp_seconds=12.0,
        )
        self.assertEqual(c.resolution_state, CommentResolutionState.OPEN)

        # Editor resolves
        resolved = self.service.resolve_comment(
            session_id=session.session_id,
            comment_id=c.comment_id,
            user_id="editor_ed",
            state=CommentResolutionState.RESOLVED,
        )
        self.assertEqual(resolved.resolution_state, CommentResolutionState.RESOLVED)
        self.assertEqual(resolved.resolved_by, "editor_ed")

        # Reopen comment
        reopened = self.service.resolve_comment(
            session_id=session.session_id,
            comment_id=c.comment_id,
            user_id="director_dan",
            state=CommentResolutionState.REOPENED,
        )
        self.assertEqual(reopened.resolution_state, CommentResolutionState.REOPENED)
        self.assertIsNone(reopened.resolved_by)

    def test_06_non_destructive_timeline_marker_projection(self) -> None:
        """Tests non-destructive export of review comments into TimelineMarkers."""
        session = self.service.create_review_session(
            project_id="prj_alpha",
            sequence_id="seq_101",
            title="Marker Sync",
            created_by="director_dan",
        )

        c1 = self.service.add_comment(
            session_id=session.session_id,
            author_id="director_dan",
            content="VFX artifact",
            timestamp_seconds=14.2,
            region=NormalizedRegion(0.2, 0.2, 0.2, 0.2),
        )
        c2 = self.service.add_comment(
            session_id=session.session_id,
            author_id="director_dan",
            content="Mix music higher",
            timestamp_seconds=45.0,
        )
        self.service.resolve_comment(session.session_id, c2.comment_id, "director_dan")

        # Only open comments
        active_markers = self.service.export_timeline_markers(session.session_id, include_resolved=False)
        self.assertEqual(len(active_markers), 1)
        self.assertEqual(active_markers[0].frame, int(round(14.2 * 24.0)))

        # Include resolved
        all_markers = self.service.export_timeline_markers(session.session_id, include_resolved=True)
        self.assertEqual(len(all_markers), 2)

    def test_07_revision_drift_and_stale_comment_detection(self) -> None:
        """Verifies comments detect when the underlying sequence revision has drifted forward."""
        session = self.service.create_review_session(
            project_id="prj_alpha",
            sequence_id="seq_101",
            title="Revision Drift Test",
            created_by="director_dan",
            target_revision=1,
        )

        c1 = self.service.add_comment(
            session_id=session.session_id,
            author_id="director_dan",
            content="Cut on action feels early",
            timestamp_seconds=18.0,
            target_revision=1,
        )
        self.assertFalse(c1.is_stale(current_sequence_revision=1))

        # Sequence edits increment revision to 3
        stale_list = self.service.get_stale_comments(session.session_id, current_sequence_revision=3)
        self.assertEqual(len(stale_list), 1)
        comment, drift = stale_list[0]
        self.assertEqual(comment.comment_id, c1.comment_id)
        self.assertEqual(drift, 2)
        self.assertTrue(comment.is_stale(current_sequence_revision=3))

    def test_08_formal_review_decisions_and_session_status(self) -> None:
        """Tests decision submission (APPROVED, CHANGES_REQUESTED) and session state aggregation."""
        session = self.service.create_review_session(
            project_id="prj_alpha",
            sequence_id="seq_101",
            title="Final Delivery Approval",
            created_by="director_dan",
            target_revision=1,
            participants={"client_claire": ParticipantRole.REVIEWER},
        )

        # Changes requested
        d1 = self.service.submit_decision(
            session_id=session.session_id,
            reviewer_id="client_claire",
            decision_type=ReviewDecisionType.CHANGES_REQUESTED,
            rationale="Ending needs fade to black",
        )
        self.assertEqual(d1.decision_type, ReviewDecisionType.CHANGES_REQUESTED)
        self.assertEqual(session.status, ReviewSessionStatus.CHANGES_REQUESTED)

        # Revision bumped to 2, approved
        session.target_revision = 2
        d2 = self.service.submit_decision(
            session_id=session.session_id,
            reviewer_id="client_claire",
            decision_type=ReviewDecisionType.APPROVED,
            rationale="Looks perfect now!",
            target_revision=2,
        )
        self.assertEqual(session.status, ReviewSessionStatus.APPROVED)
        self.assertEqual(len(session.decisions), 2)

    def test_09_security_and_role_authorization_enforcement(self) -> None:
        """Verifies viewers and unauthorized users are prohibited from mutating review state."""
        session = self.service.create_review_session(
            project_id="prj_alpha",
            sequence_id="seq_101",
            title="Security Guard Test",
            created_by="director_dan",
            participants={
                "viewer_vince": ParticipantRole.VIEWER,
                "editor_ed": ParticipantRole.EDITOR,
            },
        )

        # Viewer cannot comment
        with self.assertRaises(PermissionError):
            self.service.add_comment(
                session_id=session.session_id,
                author_id="viewer_vince",
                content="Viewers cannot talk",
                timestamp_seconds=5.0,
            )

        # Editor cannot render formal decision (only OWNER or REVIEWER can)
        with self.assertRaises(PermissionError):
            self.service.submit_decision(
                session_id=session.session_id,
                reviewer_id="editor_ed",
                decision_type=ReviewDecisionType.APPROVED,
            )

        # Uninvited user cannot comment
        with self.assertRaises(PermissionError):
            self.service.add_comment(
                session_id=session.session_id,
                author_id="hacker_harold",
                content="Unauthorized",
                timestamp_seconds=5.0,
            )

    def test_10_registry_capabilities(self) -> None:
        """Verifies all Module 40 capabilities are registered with IMPLEMENTED state."""
        expected_caps = [
            "video.collaboration.review_sessions",
            "video.collaboration.timestamped_annotations",
            "video.collaboration.version_aware_review",
            "video.collaboration.decision_audit",
        ]
        for cap_id in expected_caps:
            cap = self.registry.get(cap_id)
            self.assertIsNotNone(cap, f"Capability {cap_id} missing from registry.")
            self.assertEqual(cap.category, VideoStudioCategory.COLLABORATION)
            self.assertEqual(cap.implementation_state, ImplementationState.IMPLEMENTED)


if __name__ == "__main__":
    unittest.main()
