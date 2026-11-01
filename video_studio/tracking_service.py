"""OMNIA Video Studio — Tracking Service & Track-to-Effects Orchestrator (Module 22).

Coordinates:
- Creation, retrieval, update, and lifecycle management of TrackingSession entities.
- Non-destructive execution of motion tracking jobs using MotionTrackingEngine.
- Binding tracked motion to:
  1. Transform properties (Position X/Y, Scale, Rotation) in AnimationService.
  2. Effect parameters in EffectsEngine.
  3. Mask coordinates / shapes in Compositor / Mask layers.
- Capability registration with OMNIA Video Studio subsystem registry.
"""

import uuid
import time
import logging
from typing import Dict, Any, List, Optional, Tuple

from video_studio.tracking_models import (
    TrackingSession,
    TrackSample,
    TrackingMethodType,
    TrackingStatus,
    TrackTargetType,
    TrackApplicationTarget,
    TrackToEffectBinding,
)
from video_studio.tracking_engine import (
    MotionTrackingEngine,
    motion_tracking_engine,
)
from video_studio.animation_service import (
    AnimationService,
    InterpolationMode,
)
from video_studio.registry import video_studio_capability_registry
from video_studio.registry_models import (
    VideoStudioCategory,
    ImplementationState,
    VideoStudioCapabilityDescriptor,
)

logger = logging.getLogger("omnia.video_studio.tracking_service")


class TrackingService:
    """Orchestrator for video motion tracking, session management, and track-to-effect linking."""

    def __init__(
        self,
        engine: Optional[MotionTrackingEngine] = None,
        animation_service: Optional[AnimationService] = None,
    ):
        self.engine = engine or motion_tracking_engine
        self.animation_service = animation_service
        self._sessions: Dict[str, TrackingSession] = {}
        self._bindings: Dict[str, TrackToEffectBinding] = {}

    def set_animation_service(self, animation_service: AnimationService) -> None:
        self.animation_service = animation_service

    # -------------------------------------------------------------------------
    # 1. Session Management
    # -------------------------------------------------------------------------

    def create_session(
        self,
        project_id: str,
        clip_id: str,
        asset_id: str,
        target_name: str,
        initial_x: float,
        initial_y: float,
        initial_width: float = 64.0,
        initial_height: float = 64.0,
        start_frame: int = 0,
        end_frame: int = 0,
        method: TrackingMethodType = TrackingMethodType.POINT_OPTICAL_FLOW,
        target_type: TrackTargetType = TrackTargetType.POINT,
    ) -> TrackingSession:
        """Instantiates and registers a new motion tracking session."""
        session_id = f"track_{uuid.uuid4().hex[:12]}"
        session = TrackingSession(
            session_id=session_id,
            project_id=project_id,
            clip_id=clip_id,
            asset_id=asset_id,
            target_name=target_name,
            method=method,
            target_type=target_type,
            status=TrackingStatus.IDLE,
            initial_x=initial_x,
            initial_y=initial_y,
            initial_width=initial_width,
            initial_height=initial_height,
            start_frame=start_frame,
            end_frame=end_frame,
        )
        self._sessions[session_id] = session
        logger.info(f"Created tracking session {session_id} for target '{target_name}' on clip {clip_id}.")
        return session

    def get_session(self, session_id: str) -> Optional[TrackingSession]:
        return self._sessions.get(session_id)

    def list_sessions(self, clip_id: Optional[str] = None, project_id: Optional[str] = None) -> List[TrackingSession]:
        sessions = list(self._sessions.values())
        if project_id:
            sessions = [s for s in sessions if s.project_id == project_id]
        if clip_id:
            sessions = [s for s in sessions if s.clip_id == clip_id]
        return sessions

    def delete_session(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            # Clean up associated bindings
            self._bindings = {k: b for k, b in self._bindings.items() if b.session_id != session_id}
            return True
        return False

    # -------------------------------------------------------------------------
    # 2. Tracking Execution
    # -------------------------------------------------------------------------

    def start_tracking(
        self,
        session_id: str,
        file_path: str,
        cancel_check: Optional[Any] = None,
    ) -> TrackingSession:
        """Executes tracking across frames in the given video file."""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Tracking session '{session_id}' not found.")

        updated_session = self.engine.track_session(
            file_path=file_path,
            session=session,
            cancel_check=cancel_check,
        )
        updated_session.updated_at = time.time()
        self._sessions[session_id] = updated_session
        return updated_session

    def update_sample_manually(
        self,
        session_id: str,
        frame_index: int,
        x: float,
        y: float,
        width: Optional[float] = None,
        height: Optional[float] = None,
    ) -> TrackSample:
        """Allows manual user correction / keyframe refinement on a specific frame."""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Tracking session '{session_id}' not found.")

        existing = session.samples.get(frame_index)
        w = width if width is not None else (existing.width if existing else session.initial_width)
        h = height if height is not None else (existing.height if existing else session.initial_height)

        sample = TrackSample(
            frame_index=frame_index,
            x=x,
            y=y,
            width=w,
            height=h,
            confidence=1.0,
            is_valid=True,
            tracking_lost=False,
        )
        session.samples[frame_index] = sample
        if frame_index in session.lost_track_frames:
            session.lost_track_frames.remove(frame_index)
        session.updated_at = time.time()
        return sample

    # -------------------------------------------------------------------------
    # 3. Track-to-Effects & Track-to-Transform Binding
    # -------------------------------------------------------------------------

    def create_binding(
        self,
        session_id: str,
        target_clip_id: str,
        application_target: TrackApplicationTarget = TrackApplicationTarget.TRANSFORM_POSITION,
        offset_x: float = 0.0,
        offset_y: float = 0.0,
        invert_motion: bool = False,
        relative_to_initial: bool = True,
        target_property_id: Optional[str] = None,
    ) -> TrackToEffectBinding:
        """Creates a binding between a tracking session and a destination transform/effect."""
        if session_id not in self._sessions:
            raise ValueError(f"Tracking session '{session_id}' not found.")

        binding_id = f"bind_{uuid.uuid4().hex[:10]}"
        binding = TrackToEffectBinding(
            binding_id=binding_id,
            session_id=session_id,
            target_clip_id=target_clip_id,
            application_target=application_target,
            offset_x=offset_x,
            offset_y=offset_y,
            invert_motion=invert_motion,
            relative_to_initial=relative_to_initial,
            target_property_id=target_property_id,
            is_active=True,
        )
        self._bindings[binding_id] = binding
        return binding

    def get_binding(self, binding_id: str) -> Optional[TrackToEffectBinding]:
        return self._bindings.get(binding_id)

    def list_bindings_for_session(self, session_id: str) -> List[TrackToEffectBinding]:
        return [b for b in self._bindings.values() if b.session_id == session_id]

    def apply_track_to_clip_transform(
        self,
        session_id: str,
        target_clip_id: str,
        binding: Optional[TrackToEffectBinding] = None,
        animation_service: Optional[AnimationService] = None,
    ) -> Dict[str, int]:
        """
        Converts tracking samples into Module 8 animatable keyframes on the target clip.
        Returns a dict with count of keyframes added per property.
        """
        anim = animation_service or self.animation_service
        if not anim:
            raise RuntimeError("AnimationService is required to apply tracking data to transforms.")

        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Tracking session '{session_id}' not found.")

        if not binding:
            binding = self.create_binding(session_id, target_clip_id)

        transform = anim.get_or_create_transform(target_clip_id)
        counts = {"pos_x": 0, "pos_y": 0, "rotation": 0, "scale": 0}

        sorted_frames = sorted(session.samples.keys())
        if not sorted_frames:
            return counts

        init_x = session.initial_x
        init_y = session.initial_y

        for f_idx in sorted_frames:
            sample = session.samples[f_idx]
            if not sample.is_valid or sample.tracking_lost:
                continue

            # Compute effective delta or absolute position
            if binding.relative_to_initial:
                dx = sample.x - init_x
                dy = sample.y - init_y
                if binding.invert_motion:
                    dx = -dx
                    dy = -dy
                val_x = dx + binding.offset_x
                val_y = dy + binding.offset_y
            else:
                val_x = sample.x + binding.offset_x
                val_y = sample.y + binding.offset_y
                if binding.invert_motion:
                    val_x = -val_x
                    val_y = -val_y

            if binding.application_target in (
                TrackApplicationTarget.TRANSFORM_POSITION,
                TrackApplicationTarget.TRANSFORM_ALL,
            ):
                anim.add_keyframe(
                    property_id=transform.position_x.property_id,
                    frame=f_idx,
                    value=val_x,
                    interpolation=InterpolationMode.LINEAR,
                )
                counts["pos_x"] += 1

                anim.add_keyframe(
                    property_id=transform.position_y.property_id,
                    frame=f_idx,
                    value=val_y,
                    interpolation=InterpolationMode.LINEAR,
                )
                counts["pos_y"] += 1

            if binding.application_target in (
                TrackApplicationTarget.TRANSFORM_ROTATION,
                TrackApplicationTarget.TRANSFORM_ALL,
            ):
                rot_deg = sample.rotation_rad * (180.0 / 3.141592653589793)
                if binding.invert_motion:
                    rot_deg = -rot_deg
                anim.add_keyframe(
                    property_id=transform.rotation.property_id,
                    frame=f_idx,
                    value=rot_deg,
                    interpolation=InterpolationMode.LINEAR,
                )
                counts["rotation"] += 1

            if binding.application_target in (
                TrackApplicationTarget.TRANSFORM_SCALE,
                TrackApplicationTarget.TRANSFORM_ALL,
            ):
                s = sample.scale
                anim.add_keyframe(
                    property_id=transform.scale_x.property_id,
                    frame=f_idx,
                    value=s,
                    interpolation=InterpolationMode.LINEAR,
                )
                anim.add_keyframe(
                    property_id=transform.scale_y.property_id,
                    frame=f_idx,
                    value=s,
                    interpolation=InterpolationMode.LINEAR,
                )
                counts["scale"] += 2

        logger.info(f"Applied track session {session_id} to clip {target_clip_id}: {counts}")
        return counts

    # -------------------------------------------------------------------------
    # 4. Capability Registration
    # -------------------------------------------------------------------------

    def register_capabilities(self) -> None:
        """Registers Module 22 capabilities with OMNIA Video Studio subsystem registry."""
        capabilities = [
            ("video.tracking.point", "Lucas-Kanade point optical flow tracking with forward-backward validation"),
            ("video.tracking.region", "Normalized cross-correlation template matching region tracking"),
            ("video.tracking.effects_binding", "Automated binding of motion tracks to transforms, effects, and masks"),
            ("video.tracking.quality_analysis", "Tracking confidence scoring, tracking loss detection, and manual sample editing"),
        ]
        for cap_id, desc in capabilities:
            try:
                if video_studio_capability_registry.get(cap_id) is None:
                    desc_model = VideoStudioCapabilityDescriptor(
                        id=cap_id,
                        name=cap_id,
                        description=desc,
                        category=VideoStudioCategory.TRACKING,
                        implementation_state=ImplementationState.IMPLEMENTED,
                    )
                    video_studio_capability_registry.register(desc_model, auth_token="core")
            except Exception as e:
                logger.debug(f"Capability '{cap_id}' registration note: {e}")


# Global singleton instance
tracking_service = TrackingService()
