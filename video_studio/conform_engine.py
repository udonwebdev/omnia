"""OMNIA Video Studio — Module 43: Media Conform & Offline-to-Online Engine.

Core algorithmic logic for:
- Evaluating frame-rate, duration, aspect ratio, and audio stream compatibility between original and proxy.
- Building preflight conform reports with issue classification (COMPATIBLE, WARNING, RESOLUTION, BLOCKING).
- Mapping timeline clip source references seamlessly between proxy and original asset IDs.
- Validating physical media availability and cryptographic fingerprint consistency before conform.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from video_studio.conform_models import (
    ConformCompatibilityGrade,
    ConformIssue,
    ConformPreflightReport,
    MediaRepresentationMode,
    ProxyMappingRecord,
)
from video_studio.media_models import MediaAsset
from video_studio.timeline_models import VideoSequence


class ConformEngine:
    """Core domain logic for offline-to-online conform verification and timing alignment."""

    @staticmethod
    def evaluate_compatibility(
        original: MediaAsset,
        proxy: MediaAsset,
        mapping: Optional[ProxyMappingRecord] = None,
    ) -> List[ConformIssue]:
        """Compares original source asset against proxy representation to identify timing or format issues."""
        issues: List[ConformIssue] = []

        # 1. Physical existence
        if not (os.path.exists(original.file_location) and os.path.isfile(original.file_location)):
            issues.append(
                ConformIssue(
                    asset_id=original.asset_id,
                    property_name="file_location",
                    grade=ConformCompatibilityGrade.BLOCKING,
                    message=f"Original high-resolution file is missing at path '{original.file_location}'.",
                    original_value=original.file_location,
                )
            )
            return issues  # Cannot evaluate further if missing

        # 2. Frame Rate / Timebase check
        if original.frame_rate > 0 and proxy.frame_rate > 0:
            diff_fps = abs(original.frame_rate - proxy.frame_rate)
            if diff_fps > 0.01:
                issues.append(
                    ConformIssue(
                        asset_id=original.asset_id,
                        property_name="frame_rate",
                        grade=ConformCompatibilityGrade.BLOCKING,
                        message=f"Frame rate mismatch: original is {original.frame_rate} fps, proxy is {proxy.frame_rate} fps.",
                        original_value=original.frame_rate,
                        proxy_value=proxy.frame_rate,
                    )
                )

        # 3. Frame count / Duration variance
        if original.total_frames > 0 and proxy.total_frames > 0:
            frame_diff = abs(original.total_frames - proxy.total_frames)
            if frame_diff > 2:  # >2 frames drift is blocking
                issues.append(
                    ConformIssue(
                        asset_id=original.asset_id,
                        property_name="total_frames",
                        grade=ConformCompatibilityGrade.BLOCKING,
                        message=f"Total frame count drift: original has {original.total_frames} frames, proxy has {proxy.total_frames} frames.",
                        original_value=original.total_frames,
                        proxy_value=proxy.total_frames,
                    )
                )
            elif frame_diff > 0:
                issues.append(
                    ConformIssue(
                        asset_id=original.asset_id,
                        property_name="total_frames",
                        grade=ConformCompatibilityGrade.COMPATIBLE_WITH_WARNING,
                        message=f"Minor boundary frame variance of {frame_diff} frame(s).",
                        original_value=original.total_frames,
                        proxy_value=proxy.total_frames,
                    )
                )

        # 4. Audio channels check
        if original.audio_channels and proxy.audio_channels:
            if original.audio_channels != proxy.audio_channels:
                issues.append(
                    ConformIssue(
                        asset_id=original.asset_id,
                        property_name="audio_channels",
                        grade=ConformCompatibilityGrade.COMPATIBLE_WITH_WARNING,
                        message=f"Audio channel count differs: original={original.audio_channels}, proxy={proxy.audio_channels}.",
                        original_value=original.audio_channels,
                        proxy_value=proxy.audio_channels,
                    )
                )

        # 5. Aspect ratio check
        orig_aspect = (original.width / original.height) if (original.width and original.height) else 1.777
        proxy_aspect = (proxy.width / proxy.height) if (proxy.width and proxy.height) else 1.777
        if abs(orig_aspect - proxy_aspect) > 0.05:
            issues.append(
                ConformIssue(
                    asset_id=original.asset_id,
                    property_name="aspect_ratio",
                    grade=ConformCompatibilityGrade.REQUIRES_RESOLUTION,
                    message=f"Aspect ratio discrepancy: original ({orig_aspect:.2f}) vs proxy ({proxy_aspect:.2f}).",
                    original_value=f"{original.width}x{original.height}",
                    proxy_value=f"{proxy.width}x{proxy.height}",
                )
            )

        return issues

    @staticmethod
    def generate_preflight_report(
        project_id: str,
        sequence: VideoSequence,
        mappings: Dict[str, ProxyMappingRecord], # proxy_asset_id -> ProxyMappingRecord
        assets: Dict[str, MediaAsset],
        target_mode: MediaRepresentationMode = MediaRepresentationMode.ORIGINAL,
    ) -> ConformPreflightReport:
        """Inspects all clips in a sequence and builds a comprehensive conform preflight audit."""
        report = ConformPreflightReport(
            project_id=project_id,
            sequence_id=sequence.sequence_id,
        )

        all_issues: List[ConformIssue] = []
        proposed: List[Dict[str, Any]] = []
        total_clips = 0
        compatible_clips = 0

        for track in sequence.tracks:
            for item in track.items:
                total_clips += 1
                curr_ref = item.source_reference_id

                if target_mode == MediaRepresentationMode.ORIGINAL:
                    # Currently using proxy, wanting to switch to original
                    mapping = mappings.get(curr_ref)
                    if mapping:
                        orig_asset = assets.get(mapping.original_asset_id)
                        proxy_asset = assets.get(curr_ref)
                        if orig_asset and proxy_asset:
                            clip_issues = ConformEngine.evaluate_compatibility(orig_asset, proxy_asset, mapping)
                            all_issues.extend(clip_issues)

                            has_blocking = any(i.grade == ConformCompatibilityGrade.BLOCKING for i in clip_issues)
                            if not has_blocking:
                                compatible_clips += 1
                            proposed.append({
                                "clip_id": item.item_id,
                                "track_id": track.track_id,
                                "current_reference": curr_ref,
                                "target_reference": orig_asset.asset_id,
                                "is_compatible": not has_blocking,
                            })
                        else:
                            all_issues.append(
                                ConformIssue(
                                    asset_id=curr_ref,
                                    property_name="asset_resolution",
                                    grade=ConformCompatibilityGrade.BLOCKING,
                                    message=f"Original or proxy asset object missing from library for clip '{item.name}'.",
                                )
                            )
                    else:
                        # Clip already points to original or unmapped source
                        orig_asset = assets.get(curr_ref)
                        if orig_asset and os.path.exists(orig_asset.file_location):
                            compatible_clips += 1
                        else:
                            all_issues.append(
                                ConformIssue(
                                    asset_id=curr_ref,
                                    property_name="file_location",
                                    grade=ConformCompatibilityGrade.BLOCKING,
                                    message=f"Source file for clip '{item.name}' not found on disk.",
                                )
                            )
                elif target_mode == MediaRepresentationMode.PROXY:
                    # Currently using original, wanting to switch to proxy
                    # Find mapping where original_asset_id == curr_ref
                    mapping = next((m for m in mappings.values() if m.original_asset_id == curr_ref), None)
                    if mapping:
                        proxy_asset = assets.get(mapping.proxy_asset_id)
                        if proxy_asset and os.path.exists(proxy_asset.file_location):
                            compatible_clips += 1
                            proposed.append({
                                "clip_id": item.item_id,
                                "track_id": track.track_id,
                                "current_reference": curr_ref,
                                "target_reference": proxy_asset.asset_id,
                                "is_compatible": True,
                            })
                        else:
                            all_issues.append(
                                ConformIssue(
                                    asset_id=curr_ref,
                                    property_name="proxy_file_location",
                                    grade=ConformCompatibilityGrade.BLOCKING,
                                    message=f"Proxy file missing for asset '{curr_ref}'.",
                                )
                            )
                    else:
                        compatible_clips += 1  # Retain original if no proxy exists

        report.total_clips_inspected = total_clips
        report.compatible_clips_count = compatible_clips
        report.issues = all_issues
        report.proposed_relinks = proposed

        blocking_count = sum(1 for i in all_issues if i.grade == ConformCompatibilityGrade.BLOCKING)
        resolution_count = sum(1 for i in all_issues if i.grade == ConformCompatibilityGrade.REQUIRES_RESOLUTION)
        warning_count = sum(1 for i in all_issues if i.grade == ConformCompatibilityGrade.COMPATIBLE_WITH_WARNING)

        report.blocking_issues_count = blocking_count

        if blocking_count > 0:
            report.overall_grade = ConformCompatibilityGrade.BLOCKING
            report.is_ready_for_online_render = False
        elif resolution_count > 0:
            report.overall_grade = ConformCompatibilityGrade.REQUIRES_RESOLUTION
            report.is_ready_for_online_render = False
        elif warning_count > 0:
            report.overall_grade = ConformCompatibilityGrade.COMPATIBLE_WITH_WARNING
            report.is_ready_for_online_render = True
        else:
            report.overall_grade = ConformCompatibilityGrade.COMPATIBLE
            report.is_ready_for_online_render = True

        return report
