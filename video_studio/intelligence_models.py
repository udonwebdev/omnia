"""OMNIA Video Studio — Video Understanding, Scene Analysis & Content Intelligence Models (Module 35).

Defines authoritative domain models for:
- SceneBoundaryType: HARD_CUT, FADE_OUT, FADE_IN, DISSOLVE, GRADUAL_TRANSITION
- ShotTypeClassification: EXTREME_WIDE_SHOT, WIDE_SHOT, MEDIUM_SHOT, CLOSE_UP, EXTREME_CLOSE_UP, MACRO, OVER_THE_SHOULDER
- CameraMotionClassification: STATIC, PAN_HORIZONTAL, TILT_VERTICAL, ZOOM_IN, ZOOM_OUT, TRACKING_DOLLY, HANDHELD_SHAKE
- LightingClassification: HIGH_KEY_BRIGHT, LOW_KEY_DARK, NATURAL_BALANCED, HIGH_CONTRAST_SPECULAR, BACKLIT
- AudioEventType: SPEECH, MUSIC, AMBIENCE, SILENCE, SOUND_EFFECT
- AnalysisSourceType: DETERMINISTIC_CV, AI_MODEL_INTERPRETATION, USER_CONFIRMED
- ShotMetadata: Single detected shot interval (start/end frames, timestamps, boundary type, confidence, shot type)
- SceneMetadata: Group of related shots constituting a semantic scene, with summaries and visual tags
- AudioEventSegment: Time-coded audio classification (speech, silence, music, ambience)
- VideoContentIntelligenceDocument: Master versioned container holding all intelligence for a video asset:
  * Detected shots and scenes
  * Visual classification and composition descriptions
  * Transcript references and audio events
  * Object segmentation references
  * User annotations and manual boundary corrections
  * Provenance and model metadata
- SemanticSearchQuery: Multimodal query model supporting text, shot type, time range, and semantic embeddings
- SemanticSearchResult: Ranked search result linking directly to source asset timestamp and preview thumbnail
"""

import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple


class SceneBoundaryType(str, Enum):
    """Categorization of shot boundary transition dynamics."""
    HARD_CUT = "HARD_CUT"                     # Instantaneous 1-frame cut
    FADE_OUT = "FADE_OUT"                     # Luminance fades to black
    FADE_IN = "FADE_IN"                       # Luminance rises from black
    DISSOLVE = "DISSOLVE"                     # Linear cross-fade blend
    GRADUAL_TRANSITION = "GRADUAL_TRANSITION" # General multi-frame transition


class ShotTypeClassification(str, Enum):
    """Cinematographic framing and camera composition scale."""
    EXTREME_WIDE_SHOT = "EXTREME_WIDE_SHOT"   # Panoramic establishing shot
    WIDE_SHOT = "WIDE_SHOT"                   # Full subject in environment
    MEDIUM_SHOT = "MEDIUM_SHOT"               # Waist-up composition
    CLOSE_UP = "CLOSE_UP"                     # Face / primary subject filling frame
    EXTREME_CLOSE_UP = "EXTREME_CLOSE_UP"     # Macro detail (eyes, hand, specific object)
    UNKNOWN = "UNKNOWN"


class CameraMotionClassification(str, Enum):
    """Camera kinematics estimated from optical flow and inter-frame transforms."""
    STATIC = "STATIC"                         # Locked-off tripod
    PAN_HORIZONTAL = "PAN_HORIZONTAL"         # Horizontal panning rotation
    TILT_VERTICAL = "TILT_VERTICAL"           # Vertical tilting rotation
    ZOOM_IN = "ZOOM_IN"                       # Optical focal length expansion / dolly forward
    ZOOM_OUT = "ZOOM_OUT"                     # Optical focal length reduction / dolly backward
    TRACKING_DOLLY = "TRACKING_DOLLY"         # Lateral camera translation
    HANDHELD_SHAKE = "HANDHELD_SHAKE"         # Organic high-frequency jitter


class LightingClassification(str, Enum):
    """Photometric exposure and contrast categorization."""
    HIGH_KEY_BRIGHT = "HIGH_KEY_BRIGHT"       # Bright, low contrast, minimal deep shadows
    LOW_KEY_DARK = "LOW_KEY_DARK"             # Dark, moody, high contrast, prominent shadows
    NATURAL_BALANCED = "NATURAL_BALANCED"     # Standard dynamic range daylight / studio
    HIGH_CONTRAST_SPECULAR = "HIGH_CONTRAST_SPECULAR" # Strong specular highlights
    BACKLIT = "BACKLIT"                       # Silhouette against bright background


class AudioEventType(str, Enum):
    """Acoustic categorization of audio content."""
    SPEECH = "SPEECH"                         # Human voice / dialogue
    MUSIC = "MUSIC"                           # Instrumental or musical accompaniment
    AMBIENCE = "AMBIENCE"                     # Environmental background noise / room tone
    SILENCE = "SILENCE"                       # Low-energy silence interval (< -50 dBFS)
    SOUND_EFFECT = "SOUND_EFFECT"             # Discrete transient impact / foley


class AnalysisSourceType(str, Enum):
    """Provenance and verification level of extracted intelligence."""
    DETERMINISTIC_CV = "DETERMINISTIC_CV"         # Algorithmic (histograms, frame-difference, optical flow)
    AI_MODEL_INTERPRETATION = "AI_MODEL_INTERPRETATION" # Deep learning inference (vision-language / classifier)
    USER_CONFIRMED = "USER_CONFIRMED"             # Verified, edited, or confirmed by human editor


@dataclass
class AudioEventSegment:
    """Time-bounded audio classification interval."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: AudioEventType = AudioEventType.SPEECH
    start_time: float = 0.0
    end_time: float = 0.0
    confidence: float = 1.0
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "start_time": round(float(self.start_time), 3),
            "end_time": round(float(self.end_time), 3),
            "duration": round(float(self.end_time - self.start_time), 3),
            "confidence": round(float(self.confidence), 3),
            "details": self.details,
        }


@dataclass
class ShotMetadata:
    """Individual continuous shot interval."""
    shot_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    start_frame: int = 0
    end_frame: int = 1
    start_pts: float = 0.0
    end_pts: float = 0.04
    boundary_in_type: SceneBoundaryType = SceneBoundaryType.HARD_CUT
    boundary_confidence: float = 1.0
    shot_type: ShotTypeClassification = ShotTypeClassification.UNKNOWN
    camera_motion: CameraMotionClassification = CameraMotionClassification.STATIC
    lighting: LightingClassification = LightingClassification.NATURAL_BALANCED
    visual_description: str = ""
    source_type: AnalysisSourceType = AnalysisSourceType.DETERMINISTIC_CV
    tags: List[str] = field(default_factory=list)
    thumbnail_pts: Optional[float] = None
    is_user_confirmed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "start_pts": round(float(self.start_pts), 3),
            "end_pts": round(float(self.end_pts), 3),
            "duration_pts": round(float(self.end_pts - self.start_pts), 3),
            "boundary_in_type": self.boundary_in_type.value,
            "boundary_confidence": round(float(self.boundary_confidence), 3),
            "shot_type": self.shot_type.value,
            "camera_motion": self.camera_motion.value,
            "lighting": self.lighting.value,
            "visual_description": self.visual_description,
            "source_type": self.source_type.value,
            "tags": list(self.tags),
            "thumbnail_pts": round(float(self.thumbnail_pts), 3) if self.thumbnail_pts is not None else None,
            "is_user_confirmed": self.is_user_confirmed,
        }


@dataclass
class SceneMetadata:
    """Semantic grouping of one or more sequential shots."""
    scene_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    scene_number: int = 1
    title: str = "Scene 1"
    summary: str = ""
    start_pts: float = 0.0
    end_pts: float = 0.0
    shot_ids: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    user_notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "scene_number": self.scene_number,
            "title": self.title,
            "summary": self.summary,
            "start_pts": round(float(self.start_pts), 3),
            "end_pts": round(float(self.end_pts), 3),
            "duration": round(float(self.end_pts - self.start_pts), 3),
            "shot_ids": list(self.shot_ids),
            "tags": list(self.tags),
            "user_notes": self.user_notes,
        }


@dataclass
class VideoContentIntelligenceDocument:
    """Master document storing comprehensive media intelligence for a video asset."""
    asset_id: str
    project_id: str = "default_project"
    revision: int = 1
    duration_seconds: float = 0.0
    total_frames: int = 0
    fps: float = 25.0
    shots: List[ShotMetadata] = field(default_factory=list)
    scenes: List[SceneMetadata] = field(default_factory=list)
    audio_events: List[AudioEventSegment] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    provenance_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "project_id": self.project_id,
            "revision": self.revision,
            "duration_seconds": round(float(self.duration_seconds), 3),
            "total_frames": self.total_frames,
            "fps": round(float(self.fps), 2),
            "shot_count": len(self.shots),
            "scene_count": len(self.scenes),
            "audio_event_count": len(self.audio_events),
            "shots": [s.to_dict() for s in self.shots],
            "scenes": [sc.to_dict() for sc in self.scenes],
            "audio_events": [a.to_dict() for a in self.audio_events],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "provenance_metadata": dict(self.provenance_metadata),
        }


@dataclass
class SemanticSearchQuery:
    """Query parameters for search across content intelligence and transcripts."""
    query_text: str = ""
    project_id: Optional[str] = None
    asset_id: Optional[str] = None
    shot_type: Optional[ShotTypeClassification] = None
    camera_motion: Optional[CameraMotionClassification] = None
    audio_event: Optional[AudioEventType] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    include_transcripts: bool = True
    max_results: int = 25


@dataclass
class SemanticSearchResult:
    """Individual match linking directly to timeline/asset timestamp."""
    asset_id: str
    timestamp_pts: float
    end_pts: float
    match_score: float
    match_type: str                   # "TRANSCRIPT", "VISUAL_TAG", "SHOT_TYPE", "SCENE_SUMMARY"
    snippet: str
    shot_id: Optional[str] = None
    scene_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "timestamp_pts": round(float(self.timestamp_pts), 3),
            "end_pts": round(float(self.end_pts), 3),
            "match_score": round(float(self.match_score), 3),
            "match_type": self.match_type,
            "snippet": self.snippet,
            "shot_id": self.shot_id,
            "scene_id": self.scene_id,
        }
