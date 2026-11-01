"""OMNIA Video Studio — Captions, Subtitles & Transcript Domain Models (Module 13).

Provides canonical domain models:
- SubtitleFormat: SRT, WEBVTT, TTML, ASS
- SubtitleDocument: Versioned document holding cues for a sequence/project
- SubtitleCue: Individual timed subtitle cue (start, end, text, speaker, styling, positioning)
- SubtitleStyling: Comprehensive typography, colors, shadows, borders, alignment, safe areas
- TranscriptDocument: Versioned speech transcript representation
- TranscriptSegment: Segment with speaker, text, confidence, timestamps, word-level timing
- SpeechToTextJob: Background transcription job state, provider metadata, progress
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Set
import time
import uuid

class SubtitleFormat(str, Enum):
    SRT = "SRT"
    WEBVTT = "WEBVTT"
    TTML = "TTML"
    ASS = "ASS"

class SubtitleAlignment(str, Enum):
    LEFT = "LEFT"
    CENTER = "CENTER"
    RIGHT = "RIGHT"

class SubtitleVerticalPosition(str, Enum):
    BOTTOM = "BOTTOM"
    TOP = "TOP"
    CENTER = "CENTER"

class TranscriptionJobStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

@dataclass
class SubtitleStyling:
    """Rich visual styling configuration for subtitles and captions."""
    font_family: str = "Arial"
    font_size: int = 36
    font_weight: str = "bold"
    is_italic: bool = False
    text_color: str = "#FFFFFF"         # Hex RGB
    text_alpha: float = 1.0            # 0.0 to 1.0
    background_color: str = "#000000"   # Hex RGB
    background_alpha: float = 0.65      # 0.0 to 1.0 (translucent box)
    outline_color: str = "#000000"
    outline_width: int = 2
    shadow_color: str = "#000000"
    shadow_offset: Tuple[int, int] = (2, 2)
    alignment: SubtitleAlignment = SubtitleAlignment.CENTER
    vertical_position: SubtitleVerticalPosition = SubtitleVerticalPosition.BOTTOM
    margin_vertical: int = 40          # Distance from canvas edge (safe area)
    margin_horizontal: int = 50
    line_spacing: int = 6
    max_line_width: int = 1200         # Max width in pixels before wrap
    enable_safe_area: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "font_family": self.font_family,
            "font_size": self.font_size,
            "font_weight": self.font_weight,
            "is_italic": self.is_italic,
            "text_color": self.text_color,
            "text_alpha": self.text_alpha,
            "background_color": self.background_color,
            "background_alpha": self.background_alpha,
            "outline_color": self.outline_color,
            "outline_width": self.outline_width,
            "shadow_color": self.shadow_color,
            "shadow_offset": list(self.shadow_offset),
            "alignment": self.alignment.value,
            "vertical_position": self.vertical_position.value,
            "margin_vertical": self.margin_vertical,
            "margin_horizontal": self.margin_horizontal,
            "line_spacing": self.line_spacing,
            "max_line_width": self.max_line_width,
            "enable_safe_area": self.enable_safe_area,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SubtitleStyling":
        align = SubtitleAlignment(d.get("alignment", SubtitleAlignment.CENTER.value))
        vpos = SubtitleVerticalPosition(d.get("vertical_position", SubtitleVerticalPosition.BOTTOM.value))
        soff = tuple(d.get("shadow_offset", (2, 2)))
        return cls(
            font_family=d.get("font_family", "Arial"),
            font_size=d.get("font_size", 36),
            font_weight=d.get("font_weight", "bold"),
            is_italic=d.get("is_italic", False),
            text_color=d.get("text_color", "#FFFFFF"),
            text_alpha=d.get("text_alpha", 1.0),
            background_color=d.get("background_color", "#000000"),
            background_alpha=d.get("background_alpha", 0.65),
            outline_color=d.get("outline_color", "#000000"),
            outline_width=d.get("outline_width", 2),
            shadow_color=d.get("shadow_color", "#000000"),
            shadow_offset=soff,
            alignment=align,
            vertical_position=vpos,
            margin_vertical=d.get("margin_vertical", 40),
            margin_horizontal=d.get("margin_horizontal", 50),
            line_spacing=d.get("line_spacing", 6),
            max_line_width=d.get("max_line_width", 1200),
            enable_safe_area=d.get("enable_safe_area", True),
        )

@dataclass
class SubtitleCue:
    """Individual timed subtitle cue."""
    cue_id: str
    start_time_seconds: float
    end_time_seconds: float
    text: str
    speaker_id: Optional[str] = None
    speaker_name: Optional[str] = None
    styling_override: Optional[SubtitleStyling] = None
    settings_raw: Optional[str] = None   # WebVTT or ASS raw positioning string
    metadata: Dict[str, Any] = field(default_factory=dict)
    sequence_start_frame: Optional[int] = None
    sequence_end_frame: Optional[int] = None

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.end_time_seconds - self.start_time_seconds)

    def is_active_at_time(self, time_sec: float) -> bool:
        return self.start_time_seconds <= time_sec < self.end_time_seconds

    def is_active_at_frame(self, frame: int, fps: float) -> bool:
        c_start_frame = int(round(self.start_time_seconds * fps))
        c_end_frame = int(round(self.end_time_seconds * fps))
        return c_start_frame <= frame < c_end_frame

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cue_id": self.cue_id,
            "start_time_seconds": self.start_time_seconds,
            "end_time_seconds": self.end_time_seconds,
            "duration_seconds": self.duration_seconds,
            "text": self.text,
            "speaker_id": self.speaker_id,
            "speaker_name": self.speaker_name,
            "styling_override": self.styling_override.to_dict() if self.styling_override else None,
            "settings_raw": self.settings_raw,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SubtitleCue":
        override = SubtitleStyling.from_dict(d["styling_override"]) if d.get("styling_override") else None
        return cls(
            cue_id=d["cue_id"],
            start_time_seconds=float(d["start_time_seconds"]),
            end_time_seconds=float(d["end_time_seconds"]),
            text=d.get("text", ""),
            speaker_id=d.get("speaker_id"),
            speaker_name=d.get("speaker_name"),
            styling_override=override,
            settings_raw=d.get("settings_raw"),
            metadata=d.get("metadata", {}),
        )

@dataclass
class SubtitleDocument:
    """Canonical model for a complete subtitle or caption track."""
    document_id: str
    project_id: str
    sequence_id: Optional[str] = None
    track_id: Optional[str] = None
    name: str = "Subtitles"
    language: str = "en"
    locale: str = "en-US"
    format: SubtitleFormat = SubtitleFormat.SRT
    default_styling: SubtitleStyling = field(default_factory=SubtitleStyling)
    cues: List[SubtitleCue] = field(default_factory=list)
    version: str = "1.0.0"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def sort_cues(self) -> None:
        self.cues.sort(key=lambda c: c.start_time_seconds)

    def get_cues_at_time(self, time_sec: float) -> List[SubtitleCue]:
        return [c for c in self.cues if c.is_active_at_time(time_sec)]

    def get_cues_at_frame(self, frame: int, fps: float) -> List[SubtitleCue]:
        return [c for c in self.cues if c.is_active_at_frame(frame, fps)]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "project_id": self.project_id,
            "sequence_id": self.sequence_id,
            "track_id": self.track_id,
            "name": self.name,
            "language": self.language,
            "locale": self.locale,
            "format": self.format.value,
            "default_styling": self.default_styling.to_dict(),
            "cues_count": len(self.cues),
            "cues": [c.to_dict() for c in self.cues],
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SubtitleDocument":
        styling = SubtitleStyling.from_dict(d.get("default_styling", {}))
        cues = [SubtitleCue.from_dict(c) for c in d.get("cues", [])]
        s_fmt = SubtitleFormat(d.get("format", SubtitleFormat.SRT.value))
        doc = cls(
            document_id=d["document_id"],
            project_id=d["project_id"],
            sequence_id=d.get("sequence_id"),
            track_id=d.get("track_id"),
            name=d.get("name", "Subtitles"),
            language=d.get("language", "en"),
            locale=d.get("locale", "en-US"),
            format=s_fmt,
            default_styling=styling,
            cues=cues,
            version=d.get("version", "1.0.0"),
            created_at=d.get("created_at", time.time()),
            updated_at=d.get("updated_at", time.time()),
        )
        doc.sort_cues()
        return doc

@dataclass
class WordTiming:
    word: str
    start_time: float
    end_time: float
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "word": self.word,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "confidence": self.confidence,
        }

@dataclass
class TranscriptSegment:
    segment_id: str
    start_time: float
    end_time: float
    text: str
    speaker: str = "Speaker 1"
    confidence: float = 1.0
    words: List[WordTiming] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return max(0.0, self.end_time - self.start_time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "text": self.text,
            "speaker": self.speaker,
            "confidence": self.confidence,
            "words": [w.to_dict() for w in self.words],
            "metadata": self.metadata,
        }

@dataclass
class TranscriptDocument:
    transcript_id: str
    project_id: str
    source_asset_id: Optional[str] = None
    language: str = "en"
    segments: List[TranscriptSegment] = field(default_factory=list)
    provider_name: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "transcript_id": self.transcript_id,
            "project_id": self.project_id,
            "source_asset_id": self.source_asset_id,
            "language": self.language,
            "provider_name": self.provider_name,
            "segments_count": len(self.segments),
            "segments": [s.to_dict() for s in self.segments],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

@dataclass
class SpeechToTextJob:
    job_id: str
    project_id: str
    source_asset_id: str
    provider_name: str
    status: TranscriptionJobStatus = TranscriptionJobStatus.PENDING
    progress: float = 0.0
    error_message: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    result_transcript_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "project_id": self.project_id,
            "source_asset_id": self.source_asset_id,
            "provider_name": self.provider_name,
            "status": self.status.value,
            "progress": self.progress,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "result_transcript_id": self.result_transcript_id,
        }
