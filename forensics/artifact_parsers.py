"""
forensics/artifact_parsers.py
Safe, non-executable parsers for forensic artifacts in OMNIA Module 48:
Autonomous Digital Forensics, Evidence Preservation & Incident Investigation Intelligence.
"""

import json
import uuid
import datetime
import logging
from typing import List, Dict, Any, Optional

from forensics.models import TimelineEvent, EvidenceReliabilityTier, ArtifactType

logger = logging.getLogger("omnia.forensics.parsers")


class SafeArtifactParser:
    """
    Non-executable parser interface for structured forensic telemetry,
    including authentication logs, process trees, cloud audit trails, and network flows.
    NEVER evaluates or executes arbitrary payloads.
    """

    @staticmethod
    def _parse_timestamp(raw_val: Any) -> float:
        """Helper to convert various timestamp formats to UTC float seconds."""
        if isinstance(raw_val, (int, float)):
            return float(raw_val)
        if isinstance(raw_val, str):
            try:
                # ISO format parse
                clean_str = raw_val.replace("Z", "+00:00")
                dt = datetime.datetime.fromisoformat(clean_str)
                return dt.timestamp()
            except Exception:
                pass
        return datetime.datetime.now(datetime.timezone.utc).timestamp()

    def parse_events(
        self,
        case_id: str,
        artifact_id: str,
        artifact_type: ArtifactType,
        raw_bytes: bytes
    ) -> List[TimelineEvent]:
        """
        Parses raw bytes into normalized TimelineEvent records based on artifact type.
        """
        events: List[TimelineEvent] = []
        try:
            content_str = raw_bytes.decode("utf-8", errors="replace")
        except Exception as e:
            logger.error(f"Failed to decode artifact bytes for {artifact_id}: {e}")
            return []

        # Attempt to parse as line-delimited JSON or JSON array
        items = []
        try:
            if content_str.strip().startswith("[") and content_str.strip().endswith("]"):
                items = json.loads(content_str)
            else:
                for line in content_str.splitlines():
                    line = line.strip()
                    if line:
                        try:
                            items.append(json.loads(line))
                        except json.JSONDecodeError:
                            # Fallback: treat as plain log line
                            items.append({"raw_line": line})
        except Exception as e:
            logger.warning(f"Could not parse artifact {artifact_id} as structured JSON: {e}")
            items.append({"raw_line": content_str[:1000]})

        for item in items:
            raw_ts = str(item.get("timestamp", item.get("time", item.get("eventTime", datetime.datetime.now(datetime.timezone.utc).isoformat()))))
            utc_ts = self._parse_timestamp(raw_ts)

            if artifact_type == ArtifactType.IDENTITY_AUDIT:
                actor = item.get("user", item.get("principal", item.get("actor", "UNKNOWN_IDENTITY")))
                action = item.get("action", item.get("event_type", "LOGIN"))
                source_ip = item.get("ip_address", item.get("source_ip", "0.0.0.0"))
                events.append(TimelineEvent(
                    event_id=f"ev_{uuid.uuid4().hex[:12]}",
                    case_id=case_id,
                    artifact_id=artifact_id,
                    timestamp_utc=utc_ts,
                    raw_timestamp=raw_ts,
                    event_category="IDENTITY",
                    action=action,
                    actor=actor,
                    source_entity=source_ip,
                    target_entity=item.get("target_service", "IDP"),
                    summary=f"Identity event {action} for user {actor} from {source_ip}",
                    details=item,
                    reliability_tier=EvidenceReliabilityTier.CONFIRMED
                ))

            elif artifact_type == ArtifactType.ENDPOINT_PROCESS:
                actor = item.get("user", item.get("username", "SYSTEM"))
                proc_name = item.get("process_name", item.get("image", "unknown.exe"))
                pid = item.get("pid", 0)
                cmdline = item.get("command_line", proc_name)
                events.append(TimelineEvent(
                    event_id=f"ev_{uuid.uuid4().hex[:12]}",
                    case_id=case_id,
                    artifact_id=artifact_id,
                    timestamp_utc=utc_ts,
                    raw_timestamp=raw_ts,
                    event_category="PROCESS",
                    action="PROCESS_EXECUTE",
                    actor=actor,
                    source_entity=f"PID_{pid}",
                    target_entity=proc_name,
                    summary=f"Process launch: {proc_name} (PID {pid}) by {actor} with cmd: {cmdline[:60]}",
                    details=item,
                    reliability_tier=EvidenceReliabilityTier.HIGH
                ))

            elif artifact_type == ArtifactType.CLOUD_AUDIT_LOG:
                actor = item.get("principalEmail", item.get("actor", "serviceAccount"))
                method = item.get("methodName", item.get("action", "gcp.api.call"))
                resource = item.get("resourceName", item.get("resource", "cloud_resource"))
                events.append(TimelineEvent(
                    event_id=f"ev_{uuid.uuid4().hex[:12]}",
                    case_id=case_id,
                    artifact_id=artifact_id,
                    timestamp_utc=utc_ts,
                    raw_timestamp=raw_ts,
                    event_category="CLOUD_AUDIT",
                    action=method,
                    actor=actor,
                    source_entity=item.get("callerIp", "unknown_caller"),
                    target_entity=resource,
                    summary=f"Cloud API Call: {method} on {resource} by {actor}",
                    details=item,
                    reliability_tier=EvidenceReliabilityTier.CONFIRMED
                ))

            elif artifact_type == ArtifactType.NETWORK_CONNECTION_LOG:
                src_ip = item.get("src_ip", "0.0.0.0")
                dst_ip = item.get("dst_ip", "0.0.0.0")
                dst_port = item.get("dst_port", 0)
                proto = item.get("protocol", "TCP")
                events.append(TimelineEvent(
                    event_id=f"ev_{uuid.uuid4().hex[:12]}",
                    case_id=case_id,
                    artifact_id=artifact_id,
                    timestamp_utc=utc_ts,
                    raw_timestamp=raw_ts,
                    event_category="NETWORK",
                    action="CONNECTION_ESTABLISHED",
                    actor=item.get("user", None),
                    source_entity=f"{src_ip}",
                    target_entity=f"{dst_ip}:{dst_port}",
                    summary=f"Network flow: {src_ip} -> {dst_ip}:{dst_port} ({proto})",
                    details=item,
                    reliability_tier=EvidenceReliabilityTier.HIGH
                ))

            else:
                # Default generic event
                events.append(TimelineEvent(
                    event_id=f"ev_{uuid.uuid4().hex[:12]}",
                    case_id=case_id,
                    artifact_id=artifact_id,
                    timestamp_utc=utc_ts,
                    raw_timestamp=raw_ts,
                    event_category="SYSTEM",
                    action=item.get("action", "SYSTEM_LOG"),
                    actor=item.get("actor", None),
                    source_entity=item.get("source", None),
                    target_entity=item.get("target", None),
                    summary=item.get("raw_line", str(item))[:120],
                    details=item,
                    reliability_tier=EvidenceReliabilityTier.MODERATE
                ))

        return events
