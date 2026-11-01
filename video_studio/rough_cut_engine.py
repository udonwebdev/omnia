"""OMNIA Video Studio — AI-Assisted Editing, Automated Rough Cut & Edit Decision Engine (Module 36).

Provides deterministic and AI-assisted algorithms for:
- Evaluating Candidate Moments from VideoContentIntelligenceDocuments:
  * Keyword filtering (mandating required_keywords, pruning excluded_keywords)
  * Technical score estimation based on lighting, motion stability, and confidence
  * Speech presence correlation from audio event segments
- Generating EditDecisionLists (EDL) from EditingBriefs:
  * Pacing rhythm mapping (FAST_PACED, MODERATE, SLOW_CINEMATIC)
  * Narrative sequencing strategies (CHRONOLOGICAL, HIGHLIGHTS_FIRST, THEMATIC)
  * Target duration clamping within defined tolerances
  * Ripple timeline position recalculation
- Building timeline sequences via atomic TimelineCommand / TimelineTransaction execution:
  * Checks mandatory EDL approval status (APPROVED or MODIFIED)
  * Places video items on track_v1 and audio items on track_a1
  * Generates synchronized LinkGroups binding video & audio pairs
  * Returns RoughCutResult with non-destructive undo/redo capability
"""

import time
import uuid
import copy
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
from video_studio.intelligence_models import (
    VideoContentIntelligenceDocument,
    ShotMetadata,
    AudioEventType,
    ShotTypeClassification,
    CameraMotionClassification,
    LightingClassification,
)
from video_studio.timeline_models import (
    VideoSequence,
    SequenceSettings,
    TimelineTrackModel,
    TimelineItemModel,
    TimelineRange,
    SourceRange,
    TimelineTrackType,
    TimelineItemType,
    TimelineItemState,
    LinkGroup,
)
from video_studio.timeline_commands import (
    TimelineCommand,
    TimelineTransaction,
    TimelineOpType,
)
from video_studio.timeline_service import TimelineService, timeline_service

logger = logging.getLogger("Omnia.VideoStudio.RoughCutEngine")


class RoughCutEngine:
    """Core algorithmic engine for candidate moment extraction, EDL generation, and timeline assembly."""

    # Pacing cut duration envelopes (seconds): (min_cut, max_cut, default_cut)
    PACING_ENVELOPES = {
        PacingProfile.FAST_PACED: (1.5, 3.0, 2.0),
        PacingProfile.MODERATE: (3.0, 6.0, 4.0),
        PacingProfile.SLOW_CINEMATIC: (6.0, 12.0, 8.0),
    }

    # -------------------------------------------------------------------------
    # 1. Candidate Moment Evaluation
    # -------------------------------------------------------------------------

    def extract_candidate_moments(
        self,
        brief: EditingBrief,
        intelligence_docs: List[VideoContentIntelligenceDocument],
    ) -> List[CandidateMoment]:
        """Extracts and scores candidate moments across provided asset intelligence documents."""
        candidates: List[CandidateMoment] = []

        for doc in intelligence_docs:
            asset_id = doc.asset_id
            if brief.source_asset_ids and asset_id not in brief.source_asset_ids:
                continue

            # Map audio speech segments for quick lookup
            speech_intervals: List[Tuple[float, float]] = [
                (ev.start_time, ev.end_time)
                for ev in doc.audio_events
                if ev.event_type == AudioEventType.SPEECH
            ]

            # If no discrete shots exist, create default candidate covering entire media
            if not doc.shots:
                dur = max(doc.duration_seconds, 3.0)
                cand = CandidateMoment(
                    asset_id=asset_id,
                    source_in=0.0,
                    source_out=dur,
                    shot_id=None,
                    score=1.0,
                    selection_rationale="Full clip candidate (no shot segmentation)",
                    tags=[],
                    has_speech=len(speech_intervals) > 0,
                    is_mandatory=False,
                )
                candidates.append(cand)
                continue

            for shot in doc.shots:
                shot_duration = shot.end_pts - shot.start_pts
                if shot_duration < 0.5:
                    continue  # Ignore micro fragments under 0.5s

                # Check excluded keywords against visual description and tags
                combined_text = f"{shot.visual_description} {' '.join(shot.tags)} {shot.shot_type.value} {shot.camera_motion.value}".lower()
                
                is_excluded = False
                for ex_kw in brief.excluded_keywords:
                    if ex_kw.strip().lower() in combined_text:
                        is_excluded = True
                        break
                if is_excluded:
                    continue

                # Check required keywords
                is_mandatory = False
                matched_req = []
                for req_kw in brief.required_keywords:
                    cleaned = req_kw.strip().lower()
                    if cleaned and cleaned in combined_text:
                        is_mandatory = True
                        matched_req.append(cleaned)

                # Check speech overlap
                has_speech = False
                for s_start, s_end in speech_intervals:
                    if max(shot.start_pts, s_start) < min(shot.end_pts, s_end):
                        has_speech = True
                        break

                # Compute technical quality score
                score = 1.0
                rationale_parts = []

                # Shot boundary confidence
                score += shot.boundary_confidence * 0.2

                # Lighting stability bonus
                if shot.lighting == LightingClassification.NATURAL_BALANCED:
                    score += 0.3
                    rationale_parts.append("Balanced lighting")
                elif shot.lighting == LightingClassification.HIGH_KEY_BRIGHT:
                    score += 0.2
                    rationale_parts.append("Bright high-key")

                # Camera motion aesthetics
                if shot.camera_motion in (CameraMotionClassification.STATIC, CameraMotionClassification.TRACKING_DOLLY):
                    score += 0.3
                    rationale_parts.append(f"Stable camera motion ({shot.camera_motion.value})")
                elif shot.camera_motion == CameraMotionClassification.HANDHELD_SHAKE:
                    score -= 0.1

                # Framing aesthetics
                if shot.shot_type in (ShotTypeClassification.CLOSE_UP, ShotTypeClassification.MEDIUM_SHOT):
                    score += 0.2
                    rationale_parts.append(f"Framing: {shot.shot_type.value}")

                # Speech presence
                if has_speech:
                    score += 0.2
                    rationale_parts.append("Contains dialogue")

                # Mandatory multiplier
                if is_mandatory:
                    score += 2.0
                    rationale_parts.append(f"Matched mandatory requirement: {', '.join(matched_req)}")

                cand = CandidateMoment(
                    asset_id=asset_id,
                    source_in=shot.start_pts,
                    source_out=shot.end_pts,
                    shot_id=shot.shot_id,
                    score=score,
                    selection_rationale="; ".join(rationale_parts) or "Standard shot candidate",
                    tags=list(shot.tags),
                    has_speech=has_speech,
                    is_mandatory=is_mandatory,
                )
                candidates.append(cand)

        return candidates

    # -------------------------------------------------------------------------
    # 2. EDL Generation
    # -------------------------------------------------------------------------

    def generate_edl(
        self,
        brief: EditingBrief,
        candidate_moments: List[CandidateMoment],
        intelligence_docs: Optional[List[VideoContentIntelligenceDocument]] = None,
    ) -> EditDecisionList:
        """Generates an editable, non-destructive EditDecisionList conforming to brief requirements."""
        edl = EditDecisionList(
            brief_id=brief.brief_id,
            project_id=brief.project_id,
            status=EDLApprovalStatus.PROPOSED,
        )

        if not candidate_moments:
            return edl

        # Copy candidates so we can manipulate without side effects
        cands = list(candidate_moments)

        # 1. Separate mandatory moments from optional moments
        mandatory_cands = [c for c in cands if c.is_mandatory]
        optional_cands = [c for c in cands if not c.is_mandatory]

        # 2. Sequence candidates based on NarrativeStructure
        ordered_cands: List[CandidateMoment] = []

        if brief.narrative_structure == NarrativeStructure.HIGHLIGHTS_FIRST:
            # Sort optional candidates by score descending to find hook
            sorted_by_score = sorted(cands, key=lambda c: c.score, reverse=True)
            if sorted_by_score:
                hook = sorted_by_score[0]
                ordered_cands.append(hook)
                remaining = [c for c in cands if c.moment_id != hook.moment_id]
                # Chronological remainder
                remaining_sorted = sorted(remaining, key=lambda c: (c.asset_id, c.source_in))
                ordered_cands.extend(remaining_sorted)
            else:
                ordered_cands = cands

        elif brief.narrative_structure == NarrativeStructure.THEMATIC:
            # Group by tags/visual theme, then chronological within theme
            def get_theme_key(cand: CandidateMoment) -> str:
                return cand.tags[0].lower() if cand.tags else "general"

            ordered_cands = sorted(
                cands,
                key=lambda c: (get_theme_key(c), -c.score, c.source_in)
            )

        else:  # CHRONOLOGICAL (default)
            ordered_cands = sorted(
                cands,
                key=lambda c: (c.asset_id, c.source_in)
            )

        # 3. Apply pacing profile constraints to determine cut lengths
        min_pacing, max_pacing, default_pacing = self.PACING_ENVELOPES.get(
            brief.pacing,
            (brief.min_shot_duration, brief.max_shot_duration, 4.0)
        )

        # Clamp between brief's min/max shot duration
        eff_min = max(brief.min_shot_duration, min_pacing)
        eff_max = min(brief.max_shot_duration, max_pacing)
        if eff_min > eff_max:
            eff_min = eff_max

        # Map doc shots for shot type lookup
        shot_type_map: Dict[str, str] = {}
        if intelligence_docs:
            for doc in intelligence_docs:
                for s in doc.shots:
                    shot_type_map[s.shot_id] = s.shot_type.value

        # 4. Fill decisions up to target duration + tolerance
        target_dur = brief.target_duration_seconds
        max_allowed_dur = target_dur + brief.duration_tolerance_seconds

        accumulated_duration = 0.0
        decisions: List[EditDecision] = []

        # Always include all mandatory shots first if possible
        for cand in ordered_cands:
            raw_duration = cand.source_out - cand.source_in
            if raw_duration <= 0.0:
                continue

            # Determine trimmed cut duration
            cut_duration = min(raw_duration, eff_max)
            cut_duration = max(cut_duration, eff_min)
            # Ensure it fits available source
            cut_duration = min(cut_duration, raw_duration)

            # Check if adding this shot exceeds max duration (unless mandatory)
            if not cand.is_mandatory and (accumulated_duration + cut_duration) > max_allowed_dur:
                # If we haven't reached minimum target (target - tolerance), take partial slice
                rem = (target_dur + brief.duration_tolerance_seconds) - accumulated_duration
                if rem >= eff_min:
                    cut_duration = rem
                else:
                    continue  # Skip optional clip if timeline full

            source_in = cand.source_in
            source_out = source_in + cut_duration

            shot_type = shot_type_map.get(cand.shot_id, "MEDIUM_SHOT") if cand.shot_id else "MEDIUM_SHOT"

            decision = EditDecision(
                asset_id=cand.asset_id,
                source_in=source_in,
                source_out=source_out,
                timeline_start=accumulated_duration,
                track_id="track_v1",
                audio_track_id="track_a1" if brief.include_source_audio else None,
                rationale=cand.selection_rationale or f"{brief.pacing.value} cut",
                shot_type=shot_type,
                tags=list(cand.tags),
            )
            decisions.append(decision)
            accumulated_duration += cut_duration

            # If target reached and all mandatory moments are in, we can stop
            if accumulated_duration >= target_dur:
                # Check if any remaining unplaced moments are mandatory
                unplaced_mandatories = [
                    c for c in ordered_cands[ordered_cands.index(cand)+1:]
                    if c.is_mandatory and c.moment_id not in [d.asset_id for d in decisions]
                ]
                if not unplaced_mandatories:
                    break

        edl.decisions = decisions
        edl.recalculate_timeline_positions()
        return edl

    # -------------------------------------------------------------------------
    # 3. Timeline Sequence Assembly
    # -------------------------------------------------------------------------

    def build_rough_cut_sequence(
        self,
        edl: EditDecisionList,
        sequence_id: Optional[str] = None,
        sequence_name: Optional[str] = None,
        target_service: Optional[TimelineService] = None,
    ) -> RoughCutResult:
        """Commits an APPROVED or MODIFIED EDL into a real timeline sequence using atomic transactions."""
        svc = target_service or timeline_service

        # Mandatory human-in-the-loop approval gate
        if edl.status not in (EDLApprovalStatus.APPROVED, EDLApprovalStatus.MODIFIED):
            return RoughCutResult(
                success=False,
                edl_id=edl.edl_id,
                error=f"Cannot commit EDL to timeline: Status is '{edl.status.value}'. Must be APPROVED or MODIFIED.",
            )

        if not edl.decisions:
            return RoughCutResult(
                success=False,
                edl_id=edl.edl_id,
                error="Cannot commit empty EDL to timeline.",
            )

        # Retrieve or create target sequence
        seq: Optional[VideoSequence] = None
        if sequence_id:
            seq = svc.get_sequence(sequence_id)

        if not seq:
            name = sequence_name or f"Rough Cut Assembly — {time.strftime('%Y-%m-%d %H:%M')}"
            seq = svc.create_sequence(
                project_id=edl.project_id,
                name=name,
                create_default_tracks=True,
            )

        fps = seq.settings.frame_rate if seq.settings else 24.0

        # Find target video and audio tracks
        v_track = next((t for t in seq.tracks if t.track_type == TimelineTrackType.VIDEO), None)
        a_track = next((t for t in seq.tracks if t.track_type == TimelineTrackType.AUDIO), None)

        if not v_track:
            v_track = svc.add_track(seq.sequence_id, "V1", TimelineTrackType.VIDEO)
        if not a_track and any(d.audio_track_id for d in edl.decisions):
            a_track = svc.add_track(seq.sequence_id, "A1", TimelineTrackType.AUDIO)

        # Build atomic transaction for reversible assembly
        tx_id = f"tx_roughcut_{uuid.uuid4().hex[:8]}"
        tx = TimelineTransaction(
            transaction_id=tx_id,
            sequence_id=seq.sequence_id,
            description=f"Automated Rough Cut Assembly for EDL {edl.edl_id}",
        )

        items_created = 0
        edl.recalculate_timeline_positions()

        created_item_ids: List[str] = []

        for d in edl.decisions:
            start_frame = int(round(d.timeline_start * fps))
            dur_frames = max(1, int(round(d.duration * fps)))
            src_in_frame = int(round(d.source_in * fps))

            # 1. Video Clip Item
            v_item_id = f"vclip_{uuid.uuid4().hex[:10]}"
            v_item = TimelineItemModel(
                item_id=v_item_id,
                track_id=v_track.track_id,
                sequence_id=seq.sequence_id,
                source_reference_id=d.asset_id,
                name=f"{d.asset_id} [{d.shot_type}]",
                item_type=TimelineItemType.MEDIA_CLIP,
                timeline_range=TimelineRange(start_frame=start_frame, duration_frames=dur_frames),
                source_range=SourceRange(in_frame=src_in_frame, duration_frames=dur_frames),
                speed=1.0,
                metadata={"rationale": d.rationale, "tags": d.tags, "decision_id": d.decision_id},
            )

            cmd_v = TimelineCommand(
                command_id=f"cmd_v_{uuid.uuid4().hex[:8]}",
                op_type=TimelineOpType.ADD_ITEM,
                sequence_id=seq.sequence_id,
                target_id=v_track.track_id,
                payload={"track_id": v_track.track_id, "item": v_item.to_dict()},
            )
            tx.append(cmd_v)
            items_created += 1
            created_item_ids.append(v_item_id)

            # 2. Audio Clip Item (if requested)
            if d.audio_track_id and a_track:
                a_item_id = f"aclip_{uuid.uuid4().hex[:10]}"
                a_item = TimelineItemModel(
                    item_id=a_item_id,
                    track_id=a_track.track_id,
                    sequence_id=seq.sequence_id,
                    source_reference_id=d.asset_id,
                    name=f"{d.asset_id} [Audio]",
                    item_type=TimelineItemType.MEDIA_CLIP,
                    timeline_range=TimelineRange(start_frame=start_frame, duration_frames=dur_frames),
                    source_range=SourceRange(in_frame=src_in_frame, duration_frames=dur_frames),
                    speed=1.0,
                    metadata={"decision_id": d.decision_id},
                )

                cmd_a = TimelineCommand(
                    command_id=f"cmd_a_{uuid.uuid4().hex[:8]}",
                    op_type=TimelineOpType.ADD_ITEM,
                    sequence_id=seq.sequence_id,
                    target_id=a_track.track_id,
                    payload={"track_id": a_track.track_id, "item": a_item.to_dict()},
                )
                tx.append(cmd_a)
                items_created += 1
                created_item_ids.append(a_item_id)

                # Link audio and video
                link_id = f"link_{uuid.uuid4().hex[:8]}"
                cmd_link = TimelineCommand(
                    command_id=f"cmd_link_{uuid.uuid4().hex[:8]}",
                    op_type=TimelineOpType.LINK_ITEMS,
                    sequence_id=seq.sequence_id,
                    target_id=link_id,
                    payload={"link_id": link_id, "item_ids": [v_item_id, a_item_id]},
                )
                tx.append(cmd_link)

        # Commit transaction through HistoryManager
        hm = svc._history_managers.get(seq.sequence_id)
        if hm:
            committed = hm.commit_transaction(tx)
            if not committed:
                return RoughCutResult(
                    success=False,
                    sequence_id=seq.sequence_id,
                    edl_id=edl.edl_id,
                    error="Transaction commit failed during timeline assembly.",
                )
        else:
            # Fallback direct execution
            for cmd in tx.commands:
                cmd.execute(seq)

        seq.calculate_duration_frames()
        total_timeline_sec = float(seq.duration_frames) / fps if fps > 0 else 0.0

        return RoughCutResult(
            success=True,
            sequence_id=seq.sequence_id,
            edl_id=edl.edl_id,
            items_created=items_created,
            total_timeline_duration=total_timeline_sec,
            warnings=[],
        )


# Global singleton
rough_cut_engine = RoughCutEngine()
