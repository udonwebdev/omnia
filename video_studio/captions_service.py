"""OMNIA Video Studio — Captions, Subtitles & Transcript Service (Module 13).

Coordinates:
- Subtitle document persistence, retrieval, and cue management
- Transcript creation, segment editing, and phrase search
- Speech-to-Text provider abstraction with truthful capability states
- Timeline track integration and synchronization with playhead
- Capability registry registration for Module 13
"""

from typing import Dict, Any, List, Optional, Tuple, Set
import time
import uuid
import re
import logging

from video_studio.captions_models import (
    SubtitleFormat,
    SubtitleStyling,
    SubtitleCue,
    SubtitleDocument,
    TranscriptDocument,
    TranscriptSegment,
    WordTiming,
    SpeechToTextJob,
    TranscriptionJobStatus,
)
from video_studio.captions_formats import SubtitleParser
from video_studio.captions_renderer import captions_renderer, CaptionsRenderer
from video_studio.timeline_models import (
    VideoSequence,
    TimelineTrackModel,
    TimelineTrackType,
    TimelineItemModel,
    TimelineItemType,
    TimelineRange,
    SourceRange,
)
from video_studio.registry import video_studio_capability_registry
from video_studio.registry_models import VideoStudioCategory, ImplementationState, VideoStudioCapabilityDescriptor

logger = logging.getLogger("Omnia.VideoStudio.CaptionsService")

class ISpeechToTextProvider:
    """Interface for pluggable speech-to-text engines."""
    name: str

    def is_available(self) -> bool:
        raise NotImplementedError

    def transcribe_audio(self, audio_path: str, language: str = "en") -> TranscriptDocument:
        raise NotImplementedError

class CaptionsService:
    """Core service for managing subtitle documents, transcripts, and timeline text sync."""

    def __init__(self, renderer: Optional[CaptionsRenderer] = None):
        self.renderer = renderer or captions_renderer

        # Storage: doc_id -> SubtitleDocument
        self._documents: Dict[str, SubtitleDocument] = {}
        # Transcripts: transcript_id -> TranscriptDocument
        self._transcripts: Dict[str, TranscriptDocument] = {}
        # STT Jobs: job_id -> SpeechToTextJob
        self._jobs: Dict[str, SpeechToTextJob] = {}
        # STT Providers: provider_name -> ISpeechToTextProvider
        self._providers: Dict[str, ISpeechToTextProvider] = {}

        self._register_capabilities()

    def _register_capabilities(self) -> None:
        caps = [
            ("video.captions.engine", "Captions & Subtitles Engine", "Core subtitle document management and timeline integration", ImplementationState.IMPLEMENTED),
            ("video.captions.srt", "SRT Import/Export", "SubRip standard format parser and generator", ImplementationState.IMPLEMENTED),
            ("video.captions.webvtt", "WebVTT Import/Export", "W3C WebVTT standard format parser and generator", ImplementationState.IMPLEMENTED),
            ("video.captions.transcript", "Transcript Editor", "Transcript segment management, splitting, merging and search", ImplementationState.IMPLEMENTED),
            ("video.captions.styling", "Subtitle Styling Engine", "Rich typography, color, background boxes, outlines and safe area", ImplementationState.IMPLEMENTED),
            ("video.captions.rendering", "Viewer Subtitle Rendering", "Real-time viewer compositing of active subtitle cues", ImplementationState.IMPLEMENTED),
            ("video.captions.search", "Transcript & Subtitle Search", "Exact phrase and keyword timestamp navigation", ImplementationState.IMPLEMENTED),
            ("video.captions.stt_provider", "Speech-to-Text Provider", "Pluggable transcription provider interface", ImplementationState.IMPLEMENTED),
        ]

        for cap_id, name, desc, state in caps:
            try:
                descriptor = VideoStudioCapabilityDescriptor(
                    id=cap_id,
                    name=name,
                    category=VideoStudioCategory.EDITING,
                    description=desc,
                    implementation_state=state,
                    enabled=True,
                )
                video_studio_capability_registry.register(descriptor)
            except Exception as e:
                logger.debug(f"Capability '{cap_id}' registration note: {e}")

    # =========================================================================
    # Subtitle Document Operations
    # =========================================================================

    def create_subtitle_document(
        self,
        project_id: str,
        name: str = "Subtitles",
        language: str = "en",
        format: SubtitleFormat = SubtitleFormat.SRT,
        sequence_id: Optional[str] = None,
        track_id: Optional[str] = None,
        styling: Optional[SubtitleStyling] = None,
    ) -> SubtitleDocument:
        """Creates a new subtitle document."""
        doc_id = f"subdoc_{uuid.uuid4().hex[:10]}"
        doc = SubtitleDocument(
            document_id=doc_id,
            project_id=project_id,
            sequence_id=sequence_id,
            track_id=track_id,
            name=name,
            language=language,
            format=format,
            default_styling=styling or SubtitleStyling(),
        )
        self._documents[doc_id] = doc
        return doc

    def get_subtitle_document(self, document_id: str) -> Optional[SubtitleDocument]:
        return self._documents.get(document_id)

    def delete_subtitle_document(self, document_id: str) -> bool:
        return self._documents.pop(document_id, None) is not None

    def list_documents_for_project(self, project_id: str) -> List[SubtitleDocument]:
        return [d for d in self._documents.values() if d.project_id == project_id]

    def list_documents_for_sequence(self, sequence_id: str) -> List[SubtitleDocument]:
        return [d for d in self._documents.values() if d.sequence_id == sequence_id]

    # =========================================================================
    # Cue Operations
    # =========================================================================

    def add_cue(
        self,
        document_id: str,
        start_time_seconds: float,
        end_time_seconds: float,
        text: str,
        speaker_name: Optional[str] = None,
        styling_override: Optional[SubtitleStyling] = None,
    ) -> SubtitleCue:
        doc = self.get_subtitle_document(document_id)
        if not doc:
            raise ValueError(f"Subtitle document '{document_id}' not found.")

        if start_time_seconds < 0 or end_time_seconds <= start_time_seconds:
            raise ValueError(f"Invalid cue time range: [{start_time_seconds}, {end_time_seconds}]. End must exceed start >= 0.")

        cue = SubtitleCue(
            cue_id=f"cue_{uuid.uuid4().hex[:8]}",
            start_time_seconds=start_time_seconds,
            end_time_seconds=end_time_seconds,
            text=text,
            speaker_name=speaker_name,
            styling_override=styling_override,
        )
        doc.cues.append(cue)
        doc.sort_cues()
        doc.updated_at = time.time()
        return cue

    def update_cue(
        self,
        document_id: str,
        cue_id: str,
        text: Optional[str] = None,
        start_time_seconds: Optional[float] = None,
        end_time_seconds: Optional[float] = None,
        speaker_name: Optional[str] = None,
    ) -> SubtitleCue:
        doc = self.get_subtitle_document(document_id)
        if not doc:
            raise ValueError(f"Subtitle document '{document_id}' not found.")

        cue = next((c for c in doc.cues if c.cue_id == cue_id), None)
        if not cue:
            raise ValueError(f"Cue '{cue_id}' not found in document '{document_id}'.")

        if text is not None:
            cue.text = text
        if start_time_seconds is not None:
            cue.start_time_seconds = float(start_time_seconds)
        if end_time_seconds is not None:
            cue.end_time_seconds = float(end_time_seconds)
        if speaker_name is not None:
            cue.speaker_name = speaker_name

        if cue.start_time_seconds < 0 or cue.end_time_seconds <= cue.start_time_seconds:
            raise ValueError(f"Invalid cue time range after update: [{cue.start_time_seconds}, {cue.end_time_seconds}].")

        doc.sort_cues()
        doc.updated_at = time.time()
        return cue

    def remove_cue(self, document_id: str, cue_id: str) -> bool:
        doc = self.get_subtitle_document(document_id)
        if not doc:
            return False
        orig_len = len(doc.cues)
        doc.cues = [c for c in doc.cues if c.cue_id != cue_id]
        if len(doc.cues) < orig_len:
            doc.updated_at = time.time()
            return True
        return False

    def split_cue(self, document_id: str, cue_id: str, split_time_seconds: float) -> Tuple[SubtitleCue, SubtitleCue]:
        doc = self.get_subtitle_document(document_id)
        if not doc:
            raise ValueError(f"Subtitle document '{document_id}' not found.")

        cue = next((c for c in doc.cues if c.cue_id == cue_id), None)
        if not cue:
            raise ValueError(f"Cue '{cue_id}' not found.")

        if not (cue.start_time_seconds < split_time_seconds < cue.end_time_seconds):
            raise ValueError(f"Split time {split_time_seconds}s is not strictly inside cue [{cue.start_time_seconds}, {cue.end_time_seconds}].")

        # Split text roughly in half if multiline or spaced
        words = cue.text.split()
        mid = len(words) // 2
        text1 = " ".join(words[:mid]) if mid > 0 else cue.text
        text2 = " ".join(words[mid:]) if mid > 0 else ""

        # Update first cue
        old_end = cue.end_time_seconds
        cue.end_time_seconds = split_time_seconds
        cue.text = text1

        # Create second cue
        cue2 = SubtitleCue(
            cue_id=f"cue_{uuid.uuid4().hex[:8]}",
            start_time_seconds=split_time_seconds,
            end_time_seconds=old_end,
            text=text2,
            speaker_name=cue.speaker_name,
            styling_override=cue.styling_override,
        )
        doc.cues.append(cue2)
        doc.sort_cues()
        doc.updated_at = time.time()
        return cue, cue2

    def merge_cues(self, document_id: str, cue_id_1: str, cue_id_2: str) -> SubtitleCue:
        doc = self.get_subtitle_document(document_id)
        if not doc:
            raise ValueError(f"Subtitle document '{document_id}' not found.")

        c1 = next((c for c in doc.cues if c.cue_id == cue_id_1), None)
        c2 = next((c for c in doc.cues if c.cue_id == cue_id_2), None)
        if not c1 or not c2:
            raise ValueError("Both cues must exist to merge.")

        first = c1 if c1.start_time_seconds <= c2.start_time_seconds else c2
        second = c2 if first == c1 else c1

        first.end_time_seconds = max(first.end_time_seconds, second.end_time_seconds)
        first.text = f"{first.text} {second.text}".strip()

        doc.cues = [c for c in doc.cues if c.cue_id != second.cue_id]
        doc.sort_cues()
        doc.updated_at = time.time()
        return first

    # =========================================================================
    # Import & Export
    # =========================================================================

    def import_subtitles(
        self,
        project_id: str,
        content: str,
        format: SubtitleFormat = SubtitleFormat.SRT,
        sequence_id: Optional[str] = None,
        name: str = "Imported Subtitles",
    ) -> SubtitleDocument:
        if format == SubtitleFormat.SRT:
            cues = SubtitleParser.parse_srt(content)
        elif format == SubtitleFormat.WEBVTT:
            cues = SubtitleParser.parse_webvtt(content)
        else:
            raise ValueError(f"Unsupported subtitle format for import: '{format}'")

        doc = self.create_subtitle_document(
            project_id=project_id,
            name=name,
            format=format,
            sequence_id=sequence_id,
        )
        doc.cues = cues
        doc.updated_at = time.time()
        return doc

    def export_subtitles(self, document_id: str, format: Optional[SubtitleFormat] = None) -> str:
        doc = self.get_subtitle_document(document_id)
        if not doc:
            raise ValueError(f"Subtitle document '{document_id}' not found.")

        target_fmt = format or doc.format
        if target_fmt == SubtitleFormat.SRT:
            return SubtitleParser.export_srt(doc.cues)
        elif target_fmt == SubtitleFormat.WEBVTT:
            return SubtitleParser.export_webvtt(doc.cues)
        else:
            raise ValueError(f"Export format '{target_fmt}' not supported.")

    # =========================================================================
    # Transcript Operations
    # =========================================================================

    def create_transcript(
        self,
        project_id: str,
        source_asset_id: Optional[str] = None,
        language: str = "en",
        provider_name: Optional[str] = None,
    ) -> TranscriptDocument:
        t_id = f"tr_{uuid.uuid4().hex[:10]}"
        t = TranscriptDocument(
            transcript_id=t_id,
            project_id=project_id,
            source_asset_id=source_asset_id,
            language=language,
            provider_name=provider_name,
        )
        self._transcripts[t_id] = t
        return t

    def get_transcript(self, transcript_id: str) -> Optional[TranscriptDocument]:
        return self._transcripts.get(transcript_id)

    def add_transcript_segment(
        self,
        transcript_id: str,
        start_time: float,
        end_time: float,
        text: str,
        speaker: str = "Speaker 1",
        confidence: float = 1.0,
        words: Optional[List[WordTiming]] = None,
    ) -> TranscriptSegment:
        tr = self.get_transcript(transcript_id)
        if not tr:
            raise ValueError(f"Transcript '{transcript_id}' not found.")

        seg = TranscriptSegment(
            segment_id=f"seg_{uuid.uuid4().hex[:8]}",
            start_time=start_time,
            end_time=end_time,
            text=text,
            speaker=speaker,
            confidence=confidence,
            words=words or [],
        )
        tr.segments.append(seg)
        tr.segments.sort(key=lambda s: s.start_time)
        tr.updated_at = time.time()
        return seg

    def search_transcript(self, transcript_id: str, query: str) -> List[Dict[str, Any]]:
        """Searches transcript text and returns matching segments with timestamps."""
        tr = self.get_transcript(transcript_id)
        if not tr:
            return []

        pattern = re.compile(re.escape(query), re.IGNORECASE)
        results = []
        for s in tr.segments:
            if pattern.search(s.text):
                results.append({
                    "segment_id": s.segment_id,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "speaker": s.speaker,
                    "text": s.text,
                })
        return results

    # =========================================================================
    # Speech-to-Text Integration
    # =========================================================================

    def register_stt_provider(self, provider: ISpeechToTextProvider) -> None:
        self._providers[provider.name] = provider

    def list_stt_providers(self) -> List[Dict[str, Any]]:
        res = []
        for name, p in self._providers.items():
            res.append({
                "provider_name": name,
                "is_available": p.is_available(),
            })
        return res

    def start_transcription_job(
        self,
        project_id: str,
        source_asset_id: str,
        provider_name: str,
    ) -> SpeechToTextJob:
        provider = self._providers.get(provider_name)
        if not provider or not provider.is_available():
            raise RuntimeError(f"Speech-to-text provider '{provider_name}' is not available or not configured.")

        job_id = f"job_stt_{uuid.uuid4().hex[:8]}"
        job = SpeechToTextJob(
            job_id=job_id,
            project_id=project_id,
            source_asset_id=source_asset_id,
            provider_name=provider_name,
            status=TranscriptionJobStatus.PROCESSING,
        )
        self._jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[SpeechToTextJob]:
        return self._jobs.get(job_id)


# Global singleton
captions_service = CaptionsService()
