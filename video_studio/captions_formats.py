"""OMNIA Video Studio — Subtitle Parsers & Exporters (SRT & WebVTT) (Module 13).

Provides robust, bidirectional parsing and exporting for industry standard subtitle formats:
- SubRip (.srt): Numbered cues, comma/dot millisecond timestamps (00:01:23,456), multiline text.
- WebVTT (.vtt): WEBVTT header, cue identifiers, optional cue settings (line, position, align).
- Format validation, malformed cue isolation, UTF-8 normalization, and error reporting.
"""

from typing import List, Tuple, Optional, Dict, Any
import re
import uuid
import logging

from video_studio.captions_models import (
    SubtitleFormat,
    SubtitleCue,
    SubtitleDocument,
)

logger = logging.getLogger("Omnia.VideoStudio.CaptionsFormats")

class SubtitleFormatError(Exception):
    """Raised when parsing fails due to malformed subtitle data."""
    pass

def parse_srt_timestamp(ts_str: str) -> float:
    """Parses SRT timestamp format 'HH:MM:SS,mmm' or 'HH:MM:SS.mmm' into float seconds."""
    ts_str = ts_str.strip().replace(",", ".")
    parts = ts_str.split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid timestamp structure: '{ts_str}'")
    hours = float(parts[0])
    minutes = float(parts[1])
    seconds = float(parts[2])
    return hours * 3600.0 + minutes * 60.0 + seconds

def format_srt_timestamp(seconds: float) -> str:
    """Formats float seconds into SRT timestamp 'HH:MM:SS,mmm'."""
    seconds = max(0.0, float(seconds))
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        secs += 1
        millis -= 1000
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

def format_vtt_timestamp(seconds: float) -> str:
    """Formats float seconds into WebVTT timestamp 'HH:MM:SS.mmm'."""
    return format_srt_timestamp(seconds).replace(",", ".")

class SubtitleParser:
    """Parses and exports SRT and WebVTT files."""

    @classmethod
    def parse_srt(cls, content: str) -> List[SubtitleCue]:
        """Parses an SRT string into a list of SubtitleCue objects."""
        # Normalize line endings
        content = content.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not content:
            return []

        blocks = re.split(r"\n\s*\n", content)
        cues: List[SubtitleCue] = []

        for block in blocks:
            lines = [l.strip() for l in block.split("\n") if l.strip()]
            if not lines:
                continue

            # Check if first line is cue index number
            idx_offset = 0
            if lines[0].isdigit():
                idx_offset = 1

            if len(lines) <= idx_offset:
                continue

            # Parse timestamp line: "00:00:01,000 --> 00:00:04,000"
            ts_line = lines[idx_offset]
            if "-->" not in ts_line:
                logger.warning(f"Skipping malformed SRT timestamp line: '{ts_line}'")
                continue

            ts_parts = ts_line.split("-->")
            try:
                start_sec = parse_srt_timestamp(ts_parts[0])
                end_sec = parse_srt_timestamp(ts_parts[1].split()[0])  # Ignore any trailing parameters
            except Exception as e:
                logger.warning(f"Error parsing SRT timestamps in line '{ts_line}': {e}")
                continue

            # Remaining lines are text
            text_lines = lines[idx_offset + 1:]
            text = "\n".join(text_lines)

            # Check for optional speaker tag, e.g. "<v John>Hello" or "John: Hello"
            speaker_name = None
            speaker_match = re.match(r"^<v\s+([^>]+)>(.*)$", text, re.DOTALL)
            if speaker_match:
                speaker_name = speaker_match.group(1).strip()
                text = speaker_match.group(2).strip()
            elif ":" in text.split("\n")[0]:
                first_line = text.split("\n")[0]
                sp_cand, rest = first_line.split(":", 1)
                if len(sp_cand.split()) <= 3 and sp_cand.isalnum():
                    speaker_name = sp_cand.strip()
                    text = rest.strip() + ("\n" + "\n".join(text.split("\n")[1:]) if len(text.split("\n")) > 1 else "")

            cue = SubtitleCue(
                cue_id=f"cue_{uuid.uuid4().hex[:8]}",
                start_time_seconds=start_sec,
                end_time_seconds=end_sec,
                text=text,
                speaker_name=speaker_name,
            )
            cues.append(cue)

        cues.sort(key=lambda c: c.start_time_seconds)
        return cues

    @classmethod
    def export_srt(cls, cues: List[SubtitleCue]) -> str:
        """Serializes subtitle cues into standard SRT format."""
        sorted_cues = sorted(cues, key=lambda c: c.start_time_seconds)
        blocks = []

        for idx, cue in enumerate(sorted_cues, start=1):
            ts_start = format_srt_timestamp(cue.start_time_seconds)
            ts_end = format_srt_timestamp(cue.end_time_seconds)
            text = cue.text
            if cue.speaker_name:
                text = f"{cue.speaker_name}: {text}"
            block = f"{idx}\n{ts_start} --> {ts_end}\n{text}"
            blocks.append(block)

        return "\n\n".join(blocks) + "\n"

    @classmethod
    def parse_webvtt(cls, content: str) -> List[SubtitleCue]:
        """Parses WebVTT format into a list of SubtitleCue objects."""
        content = content.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not content:
            return []

        lines = content.split("\n")
        if not lines[0].strip().startswith("WEBVTT"):
            raise SubtitleFormatError("Missing required 'WEBVTT' header at beginning of file.")

        cues: List[SubtitleCue] = []
        blocks = re.split(r"\n\s*\n", content)

        # Skip header block
        for block in blocks[1:]:
            b_lines = [l.strip() for l in block.split("\n") if l.strip()]
            if not b_lines:
                continue

            # Look for timestamp line with '-->'
            ts_idx = -1
            for i, line in enumerate(b_lines):
                if "-->" in line:
                    ts_idx = i
                    break

            if ts_idx == -1:
                continue

            cue_id = b_lines[0] if ts_idx > 0 else f"cue_{uuid.uuid4().hex[:8]}"
            ts_line = b_lines[ts_idx]
            parts = ts_line.split("-->")

            try:
                start_sec = parse_srt_timestamp(parts[0])
                # End timestamp may have settings after it: "00:00:05.000 align:start position:10%"
                end_and_settings = parts[1].strip().split()
                end_sec = parse_srt_timestamp(end_and_settings[0])
                settings_raw = " ".join(end_and_settings[1:]) if len(end_and_settings) > 1 else None
            except Exception as e:
                logger.warning(f"Error parsing WebVTT timestamp '{ts_line}': {e}")
                continue

            text_lines = b_lines[ts_idx + 1:]
            text = "\n".join(text_lines)

            # WebVTT voice span parsing: <v Speaker>text</v>
            speaker_name = None
            v_match = re.match(r"^<v\s+([^>]+)>(.*?)(?:</v>)?$", text, re.DOTALL)
            if v_match:
                speaker_name = v_match.group(1).strip()
                text = v_match.group(2).strip()

            cues.append(SubtitleCue(
                cue_id=cue_id,
                start_time_seconds=start_sec,
                end_time_seconds=end_sec,
                text=text,
                speaker_name=speaker_name,
                settings_raw=settings_raw,
            ))

        cues.sort(key=lambda c: c.start_time_seconds)
        return cues

    @classmethod
    def export_webvtt(cls, cues: List[SubtitleCue]) -> str:
        """Serializes subtitle cues into standard WebVTT format."""
        sorted_cues = sorted(cues, key=lambda c: c.start_time_seconds)
        blocks = ["WEBVTT\n"]

        for idx, cue in enumerate(sorted_cues, start=1):
            ts_start = format_vtt_timestamp(cue.start_time_seconds)
            ts_end = format_vtt_timestamp(cue.end_time_seconds)
            settings = f" {cue.settings_raw}" if cue.settings_raw else ""
            ts_header = f"{ts_start} --> {ts_end}{settings}"

            text = cue.text
            if cue.speaker_name:
                text = f"<v {cue.speaker_name}>{text}</v>"

            cue_id_line = f"{cue.cue_id}\n" if cue.cue_id and not cue.cue_id.startswith("cue_") else ""
            block = f"{cue_id_line}{ts_header}\n{text}"
            blocks.append(block)

        return "\n\n".join(blocks) + "\n"
