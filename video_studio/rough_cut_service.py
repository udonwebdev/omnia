"""OMNIA Video Studio — AI-Assisted Editing, Automated Rough Cut & Edit Decision Service (Module 36).

Coordinates:
- Creation, persistence, and retrieval of EditingBrief specifications.
- Analysis orchestration using VideoIntelligenceService (Module 35).
- Proposal generation of EditDecisionLists (EDL).
- Review, interactive modification, re-ordering, and approval workflow (PROPOSED -> APPROVED/REJECTED).
- Assembly of approved EDLs into real sequence timelines with undo/redo capability.
- Capability registration in VideoStudioCapabilityRegistry under VideoStudioCategory.EDITING and VideoStudioCategory.AI.
"""

import time
import copy
import uuid
import logging
from typing import Dict, Any, List, Optional, Tuple

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
from video_studio.intelligence_service import VideoIntelligenceService, video_intelligence_service
from video_studio.timeline_service import TimelineService, timeline_service
from video_studio.registry import video_studio_capability_registry
from video_studio.registry_models import (
    VideoStudioCategory,
    ImplementationState,
    VideoStudioCapabilityDescriptor,
)

logger = logging.getLogger("Omnia.VideoStudio.RoughCutService")


class RoughCutService:
    """Central service managing AI-assisted rough cuts, edit decision lists, and sequence commits."""

    def __init__(
        self,
        engine: Optional[RoughCutEngine] = None,
        intelligence_service_instance: Optional[VideoIntelligenceService] = None,
        timeline_service_instance: Optional[TimelineService] = None,
    ):
        self.engine = engine or rough_cut_engine
        self.intelligence_service = intelligence_service_instance or video_intelligence_service
        self.timeline_service = timeline_service_instance or timeline_service

        # In-memory storage
        self._briefs: Dict[str, EditingBrief] = {}
        self._edls: Dict[str, EditDecisionList] = {}

        self.register_capabilities()

    def register_capabilities(self) -> None:
        """Register Module 36 capabilities into VideoStudioCapabilityRegistry."""
        caps = [
            VideoStudioCapabilityDescriptor(
                id="video.editing.rough_cut_decision_engine",
                name="AI Rough Cut & Edit Decision Engine",
                description="Synthesizes visual intelligence and briefs into editable, non-destructive rough cuts.",
                category=VideoStudioCategory.EDITING,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["editing", "rough_cut", "edl", "assembly"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.editing.pacing_strategy",
                name="Pacing & Narrative Assembly",
                description="Rhythmic shot duration mapping and narrative structuring for automated assembly.",
                category=VideoStudioCategory.EDITING,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["editing", "pacing", "narrative", "rhythm"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.editing.ai_assisted_assembly",
                name="AI-Assisted Timeline Assembly",
                description="Interactive human-in-the-loop rough cut generation with timeline transaction commit.",
                category=VideoStudioCategory.AI,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["editing", "ai", "assembly", "transaction"],
            ),
        ]
        for cap in caps:
            if video_studio_capability_registry.get(cap.id) is None:
                video_studio_capability_registry.register(cap, auth_token="core")
        logger.info("Registered Module 36 Rough Cut capabilities.")

    # -------------------------------------------------------------------------
    # Brief Management
    # -------------------------------------------------------------------------

    def create_brief(
        self,
        project_id: str,
        title: str,
        source_asset_ids: List[str],
        target_duration_seconds: float = 60.0,
        pacing: PacingProfile = PacingProfile.MODERATE,
        narrative_structure: NarrativeStructure = NarrativeStructure.CHRONOLOGICAL,
        required_keywords: Optional[List[str]] = None,
        excluded_keywords: Optional[List[str]] = None,
        min_shot_duration: float = 1.5,
        max_shot_duration: float = 8.0,
        include_captions: bool = True,
        include_source_audio: bool = True,
    ) -> EditingBrief:
        """Creates and stores an EditingBrief."""
        brief = EditingBrief(
            project_id=project_id,
            title=title,
            source_asset_ids=list(source_asset_ids),
            target_duration_seconds=target_duration_seconds,
            pacing=pacing,
            narrative_structure=narrative_structure,
            required_keywords=list(required_keywords or []),
            excluded_keywords=list(excluded_keywords or []),
            min_shot_duration=min_shot_duration,
            max_shot_duration=max_shot_duration,
            include_captions=include_captions,
            include_source_audio=include_source_audio,
        )
        self._briefs[brief.brief_id] = brief
        return brief

    def get_brief(self, brief_id: str) -> Optional[EditingBrief]:
        return self._briefs.get(brief_id)

    def list_briefs(self, project_id: Optional[str] = None) -> List[EditingBrief]:
        if project_id:
            return [b for b in self._briefs.values() if b.project_id == project_id]
        return list(self._briefs.values())

    # -------------------------------------------------------------------------
    # EDL Generation & Workflow
    # -------------------------------------------------------------------------

    def generate_rough_cut_edl(self, brief_id: str) -> EditDecisionList:
        """Evaluates assets and constructs a proposed EditDecisionList for a brief."""
        brief = self.get_brief(brief_id)
        if not brief:
            raise ValueError(f"EditingBrief not found: {brief_id}")

        # Fetch intelligence documents for all brief source assets
        docs = [
            self.intelligence_service.get_or_create_document(aid, project_id=brief.project_id)
            for aid in brief.source_asset_ids
        ]

        # Extract candidates
        candidates = self.engine.extract_candidate_moments(brief, docs)

        # Generate EDL
        edl = self.engine.generate_edl(brief, candidates, docs)
        self._edls[edl.edl_id] = edl
        return edl

    def get_edl(self, edl_id: str) -> Optional[EditDecisionList]:
        return self._edls.get(edl_id)

    def list_edls(self, project_id: Optional[str] = None) -> List[EditDecisionList]:
        if project_id:
            return [e for e in self._edls.values() if e.project_id == project_id]
        return list(self._edls.values())

    def approve_edl(self, edl_id: str) -> EditDecisionList:
        """Approves proposed EDL for timeline assembly."""
        edl = self.get_edl(edl_id)
        if not edl:
            raise ValueError(f"EDL not found: {edl_id}")
        edl.status = EDLApprovalStatus.APPROVED
        edl.updated_at = time.time()
        edl.revision += 1
        return edl

    def reject_edl(self, edl_id: str) -> EditDecisionList:
        """Rejects/discards proposed EDL."""
        edl = self.get_edl(edl_id)
        if not edl:
            raise ValueError(f"EDL not found: {edl_id}")
        edl.status = EDLApprovalStatus.REJECTED
        edl.updated_at = time.time()
        edl.revision += 1
        return edl

    def modify_edl_decisions(self, edl_id: str, new_decisions: List[EditDecision]) -> EditDecisionList:
        """Updates decisions list (reordering, trimming, deleting) and marks EDL as MODIFIED."""
        edl = self.get_edl(edl_id)
        if not edl:
            raise ValueError(f"EDL not found: {edl_id}")

        edl.decisions = list(new_decisions)
        edl.recalculate_timeline_positions()
        edl.status = EDLApprovalStatus.MODIFIED
        edl.revision += 1
        edl.updated_at = time.time()
        return edl

    # -------------------------------------------------------------------------
    # Timeline Commit
    # -------------------------------------------------------------------------

    def commit_edl_to_timeline(
        self,
        edl_id: str,
        sequence_id: Optional[str] = None,
        sequence_name: Optional[str] = None,
    ) -> RoughCutResult:
        """Commits an approved/modified EDL to a sequence timeline."""
        edl = self.get_edl(edl_id)
        if not edl:
            return RoughCutResult(
                success=False,
                edl_id=edl_id,
                error=f"EDL not found: {edl_id}",
            )

        return self.engine.build_rough_cut_sequence(
            edl=edl,
            sequence_id=sequence_id,
            sequence_name=sequence_name,
            target_service=self.timeline_service,
        )


# Global singleton
rough_cut_service = RoughCutService()
