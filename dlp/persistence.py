"""
dlp/persistence.py
SQLite persistence repository for OMNIA Module 52:
Autonomous Data Loss Prevention, Sensitive Information Monitoring & Exfiltration Defense Intelligence.
"""

import sqlite3
import json
import time
import os
import threading
from typing import List, Dict, Any, Optional

from dlp.models import (
    DLPPolicy, DLPPolicyVersion, ProtectedFingerprint, SensitiveFinding,
    MovementEvent, TransferDecision, EnforcementAction, EndpointEnrollment,
    EndpointTelemetry, NetworkTelemetry, CloudEvent, CommunicationEvent,
    RemovableMediaEvent, ExfiltrationAlert, DLPIncident, DLPReport
)


class DLPRepository:
    def __init__(self, db_path: str = "omnia.db"):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._ensure_tables()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self):
        """Ensures that schema tables exist in the target database."""
        from persistence.migrations import MIGRATION_V36
        with self._lock, self._get_connection() as conn:
            conn.executescript(MIGRATION_V36)
            conn.commit()

    # --- 1. Policies ---
    def save_policy(self, policy: DLPPolicy) -> DLPPolicy:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO dlp_policies (
                    policy_id, name, description, category, min_sensitivity_tier,
                    channel, mode, priority, is_active, created_at, updated_at,
                    conditions_json, actions_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(policy_id) DO UPDATE SET
                    name = excluded.name,
                    description = excluded.description,
                    category = excluded.category,
                    min_sensitivity_tier = excluded.min_sensitivity_tier,
                    channel = excluded.channel,
                    mode = excluded.mode,
                    priority = excluded.priority,
                    is_active = excluded.is_active,
                    updated_at = excluded.updated_at,
                    conditions_json = excluded.conditions_json,
                    actions_json = excluded.actions_json
                """,
                (
                    policy.policy_id, policy.name, policy.description, policy.category,
                    policy.min_sensitivity_tier, policy.channel, policy.mode,
                    policy.priority, 1 if policy.is_active else 0, policy.created_at,
                    policy.updated_at, json.dumps(policy.conditions), json.dumps(policy.actions)
                )
            )
            conn.commit()
        return policy

    def get_policy(self, policy_id: str) -> Optional[DLPPolicy]:
        with self._lock, self._get_connection() as conn:
            row = conn.execute("SELECT * FROM dlp_policies WHERE policy_id = ?", (policy_id,)).fetchone()
            if not row:
                return None
            return DLPPolicy(
                policy_id=row["policy_id"],
                name=row["name"],
                description=row["description"] or "",
                category=row["category"],
                min_sensitivity_tier=row["min_sensitivity_tier"],
                channel=row["channel"],
                mode=row["mode"],
                priority=row["priority"],
                is_active=bool(row["is_active"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                conditions=json.loads(row["conditions_json"] or "{}"),
                actions=json.loads(row["actions_json"] or "[]"),
            )

    def list_policies(self, active_only: bool = True, channel: Optional[str] = None) -> List[DLPPolicy]:
        query = "SELECT * FROM dlp_policies WHERE 1=1"
        params: List[Any] = []
        if active_only:
            query += " AND is_active = 1"
        if channel:
            query += " AND channel = ?"
            params.append(channel)
        query += " ORDER BY priority ASC, created_at DESC"

        policies: List[DLPPolicy] = []
        with self._lock, self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            for row in rows:
                policies.append(DLPPolicy(
                    policy_id=row["policy_id"],
                    name=row["name"],
                    description=row["description"] or "",
                    category=row["category"],
                    min_sensitivity_tier=row["min_sensitivity_tier"],
                    channel=row["channel"],
                    mode=row["mode"],
                    priority=row["priority"],
                    is_active=bool(row["is_active"]),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    conditions=json.loads(row["conditions_json"] or "{}"),
                    actions=json.loads(row["actions_json"] or "[]"),
                ))
        return policies

    # --- 2. Policy Versions ---
    def save_policy_version(self, version: DLPPolicyVersion) -> DLPPolicyVersion:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO dlp_policy_versions (
                    version_id, policy_id, version_num, changes_summary,
                    created_at, created_by, snapshot_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(version_id) DO UPDATE SET
                    changes_summary = excluded.changes_summary,
                    snapshot_json = excluded.snapshot_json
                """,
                (
                    version.version_id, version.policy_id, version.version_num,
                    version.changes_summary, version.created_at, version.created_by,
                    json.dumps(version.snapshot)
                )
            )
            conn.commit()
        return version

    def list_policy_versions(self, policy_id: str) -> List[DLPPolicyVersion]:
        with self._lock, self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM dlp_policy_versions WHERE policy_id = ? ORDER BY version_num DESC",
                (policy_id,)
            ).fetchall()
            return [
                DLPPolicyVersion(
                    version_id=r["version_id"],
                    policy_id=r["policy_id"],
                    version_num=r["version_num"],
                    changes_summary=r["changes_summary"] or "",
                    created_at=r["created_at"],
                    created_by=r["created_by"],
                    snapshot=json.loads(r["snapshot_json"] or "{}"),
                ) for r in rows
            ]

    # --- 3. Protected Fingerprints ---
    def save_fingerprint(self, fp: ProtectedFingerprint) -> ProtectedFingerprint:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO dlp_protected_fingerprints (
                    fingerprint_id, name, data_category, fingerprint_hash,
                    algorithm, threshold, is_active, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fingerprint_id) DO UPDATE SET
                    name = excluded.name,
                    data_category = excluded.data_category,
                    fingerprint_hash = excluded.fingerprint_hash,
                    algorithm = excluded.algorithm,
                    threshold = excluded.threshold,
                    is_active = excluded.is_active,
                    metadata_json = excluded.metadata_json
                """,
                (
                    fp.fingerprint_id, fp.name, fp.data_category, fp.fingerprint_hash,
                    fp.algorithm, fp.threshold, 1 if fp.is_active else 0,
                    fp.created_at, json.dumps(fp.metadata)
                )
            )
            conn.commit()
        return fp

    def get_fingerprint(self, fingerprint_id: str) -> Optional[ProtectedFingerprint]:
        with self._lock, self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM dlp_protected_fingerprints WHERE fingerprint_id = ?",
                (fingerprint_id,)
            ).fetchone()
            if not row:
                return None
            return ProtectedFingerprint(
                fingerprint_id=row["fingerprint_id"],
                name=row["name"],
                data_category=row["data_category"],
                fingerprint_hash=row["fingerprint_hash"],
                algorithm=row["algorithm"],
                threshold=row["threshold"],
                is_active=bool(row["is_active"]),
                created_at=row["created_at"],
                metadata=json.loads(row["metadata_json"] or "{}"),
            )

    def list_fingerprints(self, active_only: bool = True) -> List[ProtectedFingerprint]:
        query = "SELECT * FROM dlp_protected_fingerprints WHERE 1=1"
        if active_only:
            query += " AND is_active = 1"
        query += " ORDER BY created_at DESC"

        fps: List[ProtectedFingerprint] = []
        with self._lock, self._get_connection() as conn:
            rows = conn.execute(query).fetchall()
            for r in rows:
                fps.append(ProtectedFingerprint(
                    fingerprint_id=r["fingerprint_id"],
                    name=r["name"],
                    data_category=r["data_category"],
                    fingerprint_hash=r["fingerprint_hash"],
                    algorithm=r["algorithm"],
                    threshold=r["threshold"],
                    is_active=bool(r["is_active"]),
                    created_at=r["created_at"],
                    metadata=json.loads(r["metadata_json"] or "{}"),
                ))
        return fps

    # --- 4. Sensitive Findings ---
    def save_finding(self, finding: SensitiveFinding) -> SensitiveFinding:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO dlp_sensitive_findings (
                    finding_id, source_ref, data_category, sensitivity_tier,
                    detection_method, confidence, matched_tokens_count,
                    detected_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(finding_id) DO UPDATE SET
                    confidence = excluded.confidence,
                    matched_tokens_count = excluded.matched_tokens_count,
                    metadata_json = excluded.metadata_json
                """,
                (
                    finding.finding_id, finding.source_ref, finding.data_category,
                    finding.sensitivity_tier, finding.detection_method, finding.confidence,
                    finding.matched_tokens_count, finding.detected_at, json.dumps(finding.metadata)
                )
            )
            conn.commit()
        return finding

    def list_findings(self, source_ref: Optional[str] = None, limit: int = 100) -> List[SensitiveFinding]:
        query = "SELECT * FROM dlp_sensitive_findings WHERE 1=1"
        params: List[Any] = []
        if source_ref:
            query += " AND source_ref = ?"
            params.append(source_ref)
        query += " ORDER BY detected_at DESC LIMIT ?"
        params.append(limit)

        findings: List[SensitiveFinding] = []
        with self._lock, self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            for r in rows:
                findings.append(SensitiveFinding(
                    finding_id=r["finding_id"],
                    source_ref=r["source_ref"],
                    data_category=r["data_category"],
                    sensitivity_tier=r["sensitivity_tier"],
                    detection_method=r["detection_method"],
                    confidence=r["confidence"],
                    matched_tokens_count=r["matched_tokens_count"],
                    detected_at=r["detected_at"],
                    metadata=json.loads(r["metadata_json"] or "{}"),
                ))
        return findings

    # --- 5. Movement Events ---
    def save_movement_event(self, event: MovementEvent) -> MovementEvent:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO dlp_movement_events (
                    event_id, actor_id, device_id, source_location,
                    destination_location, channel, volume_bytes,
                    timestamp, is_authorized, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    is_authorized = excluded.is_authorized,
                    metadata_json = excluded.metadata_json
                """,
                (
                    event.event_id, event.actor_id, event.device_id, event.source_location,
                    event.destination_location, event.channel, event.volume_bytes,
                    event.timestamp, 1 if event.is_authorized else 0, json.dumps(event.metadata)
                )
            )
            conn.commit()
        return event

    def get_movement_event(self, event_id: str) -> Optional[MovementEvent]:
        with self._lock, self._get_connection() as conn:
            row = conn.execute("SELECT * FROM dlp_movement_events WHERE event_id = ?", (event_id,)).fetchone()
            if not row:
                return None
            return MovementEvent(
                event_id=row["event_id"],
                actor_id=row["actor_id"],
                device_id=row["device_id"],
                source_location=row["source_location"],
                destination_location=row["destination_location"],
                channel=row["channel"],
                volume_bytes=row["volume_bytes"],
                timestamp=row["timestamp"],
                is_authorized=bool(row["is_authorized"]),
                metadata=json.loads(row["metadata_json"] or "{}"),
            )

    def list_movement_events(self, actor_id: Optional[str] = None, channel: Optional[str] = None, limit: int = 100) -> List[MovementEvent]:
        query = "SELECT * FROM dlp_movement_events WHERE 1=1"
        params: List[Any] = []
        if actor_id:
            query += " AND actor_id = ?"
            params.append(actor_id)
        if channel:
            query += " AND channel = ?"
            params.append(channel)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        events: List[MovementEvent] = []
        with self._lock, self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            for r in rows:
                events.append(MovementEvent(
                    event_id=r["event_id"],
                    actor_id=r["actor_id"],
                    device_id=r["device_id"],
                    source_location=r["source_location"],
                    destination_location=r["destination_location"],
                    channel=r["channel"],
                    volume_bytes=r["volume_bytes"],
                    timestamp=r["timestamp"],
                    is_authorized=bool(r["is_authorized"]),
                    metadata=json.loads(r["metadata_json"] or "{}"),
                ))
        return events

    # --- 6. Transfer Decisions ---
    def save_transfer_decision(self, decision: TransferDecision) -> TransferDecision:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO dlp_transfer_decisions (
                    decision_id, event_id, policy_id, decision, reason, evaluated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(decision_id) DO UPDATE SET
                    decision = excluded.decision,
                    reason = excluded.reason
                """,
                (
                    decision.decision_id, decision.event_id, decision.policy_id,
                    decision.decision, decision.reason, decision.evaluated_at
                )
            )
            conn.commit()
        return decision

    def get_transfer_decision(self, decision_id: str) -> Optional[TransferDecision]:
        with self._lock, self._get_connection() as conn:
            row = conn.execute("SELECT * FROM dlp_transfer_decisions WHERE decision_id = ?", (decision_id,)).fetchone()
            if not row:
                return None
            return TransferDecision(
                decision_id=row["decision_id"],
                event_id=row["event_id"],
                policy_id=row["policy_id"],
                decision=row["decision"],
                reason=row["reason"],
                evaluated_at=row["evaluated_at"],
            )

    # --- 7. Enforcement Actions ---
    def save_enforcement_action(self, action: EnforcementAction) -> EnforcementAction:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO dlp_enforcement_actions (
                    action_id, decision_id, event_id, adapter_type,
                    action_status, execution_result, verified, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(action_id) DO UPDATE SET
                    action_status = excluded.action_status,
                    execution_result = excluded.execution_result,
                    verified = excluded.verified
                """,
                (
                    action.action_id, action.decision_id, action.event_id,
                    action.adapter_type, action.action_status, action.execution_result,
                    1 if action.verified else 0, action.timestamp
                )
            )
            conn.commit()
        return action

    def list_enforcement_actions(self, decision_id: Optional[str] = None, limit: int = 100) -> List[EnforcementAction]:
        query = "SELECT * FROM dlp_enforcement_actions WHERE 1=1"
        params: List[Any] = []
        if decision_id:
            query += " AND decision_id = ?"
            params.append(decision_id)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        actions: List[EnforcementAction] = []
        with self._lock, self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            for r in rows:
                actions.append(EnforcementAction(
                    action_id=r["action_id"],
                    decision_id=r["decision_id"],
                    event_id=r["event_id"],
                    adapter_type=r["adapter_type"],
                    action_status=r["action_status"],
                    execution_result=r["execution_result"] or "",
                    verified=bool(r["verified"]),
                    timestamp=r["timestamp"],
                ))
        return actions

    # --- 8. Endpoint Enrollments & Telemetry ---
    def save_endpoint(self, ep: EndpointEnrollment) -> EndpointEnrollment:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO dlp_endpoint_enrollments (
                    endpoint_id, hostname, os_type, agent_version, status, enrolled_at, last_heartbeat
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(endpoint_id) DO UPDATE SET
                    status = excluded.status,
                    last_heartbeat = excluded.last_heartbeat
                """,
                (
                    ep.endpoint_id, ep.hostname, ep.os_type, ep.agent_version,
                    ep.status, ep.enrolled_at, ep.last_heartbeat
                )
            )
            conn.commit()
        return ep

    def get_endpoint(self, endpoint_id: str) -> Optional[EndpointEnrollment]:
        with self._lock, self._get_connection() as conn:
            row = conn.execute("SELECT * FROM dlp_endpoint_enrollments WHERE endpoint_id = ?", (endpoint_id,)).fetchone()
            if not row:
                return None
            return EndpointEnrollment(
                endpoint_id=row["endpoint_id"],
                hostname=row["hostname"],
                os_type=row["os_type"],
                agent_version=row["agent_version"],
                status=row["status"],
                enrolled_at=row["enrolled_at"],
                last_heartbeat=row["last_heartbeat"],
            )

    def save_endpoint_telemetry(self, tel: EndpointTelemetry) -> EndpointTelemetry:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO dlp_endpoint_telemetry (
                    telemetry_id, endpoint_id, operation_type, file_path, process_name, volume_bytes, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tel.telemetry_id, tel.endpoint_id, tel.operation_type,
                    tel.file_path, tel.process_name, tel.volume_bytes, tel.timestamp
                )
            )
            conn.commit()
        return tel

    # --- 9. Network Telemetry ---
    def save_network_telemetry(self, net: NetworkTelemetry) -> NetworkTelemetry:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO dlp_network_telemetry (
                    net_telemetry_id, source_ip, dest_ip, dest_domain, protocol, bytes_out, bytes_in, is_encrypted, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    net.net_telemetry_id, net.source_ip, net.dest_ip, net.dest_domain,
                    net.protocol, net.bytes_out, net.bytes_in, 1 if net.is_encrypted else 0, net.timestamp
                )
            )
            conn.commit()
        return net

    # --- 10. Cloud Events ---
    def save_cloud_event(self, cloud: CloudEvent) -> CloudEvent:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO dlp_cloud_events (
                    cloud_event_id, service_name, storage_target, action_type,
                    external_recipients_json, volume_bytes, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cloud.cloud_event_id, cloud.service_name, cloud.storage_target,
                    cloud.action_type, json.dumps(cloud.external_recipients),
                    cloud.volume_bytes, cloud.timestamp
                )
            )
            conn.commit()
        return cloud

    # --- 11. Communication Events ---
    def save_communication_event(self, comm: CommunicationEvent) -> CommunicationEvent:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO dlp_communication_events (
                    comm_event_id, app_name, sender, recipients_json,
                    attachments_json, has_external_recipient, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    comm.comm_event_id, comm.app_name, comm.sender,
                    json.dumps(comm.recipients), json.dumps(comm.attachments),
                    1 if comm.has_external_recipient else 0, comm.timestamp
                )
            )
            conn.commit()
        return comm

    # --- 12. Removable Media Events ---
    def save_removable_media_event(self, media: RemovableMediaEvent) -> RemovableMediaEvent:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO dlp_removable_media_events (
                    media_event_id, endpoint_id, device_vendor, serial_number,
                    file_name, volume_bytes, is_approved_device, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    media.media_event_id, media.endpoint_id, media.device_vendor,
                    media.serial_number, media.file_name, media.volume_bytes,
                    1 if media.is_approved_device else 0, media.timestamp
                )
            )
            conn.commit()
        return media

    def list_removable_media_events(self, endpoint_id: Optional[str] = None, limit: int = 100) -> List[RemovableMediaEvent]:
        query = "SELECT * FROM dlp_removable_media_events WHERE 1=1"
        params: List[Any] = []
        if endpoint_id:
            query += " AND endpoint_id = ?"
            params.append(endpoint_id)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        events: List[RemovableMediaEvent] = []
        with self._lock, self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            for r in rows:
                events.append(RemovableMediaEvent(
                    media_event_id=r["media_event_id"],
                    endpoint_id=r["endpoint_id"],
                    device_vendor=r["device_vendor"],
                    serial_number=r["serial_number"],
                    file_name=r["file_name"],
                    volume_bytes=r["volume_bytes"],
                    is_approved_device=bool(r["is_approved_device"]),
                    timestamp=r["timestamp"],
                ))
        return events

    # --- 13. Exfiltration Alerts ---
    def save_exfiltration_alert(self, alert: ExfiltrationAlert) -> ExfiltrationAlert:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO dlp_exfiltration_alerts (
                    alert_id, title, severity, risk_score, confidence,
                    anomaly_indicators_json, actor_id, destination, status, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(alert_id) DO UPDATE SET
                    title = excluded.title,
                    severity = excluded.severity,
                    risk_score = excluded.risk_score,
                    confidence = excluded.confidence,
                    anomaly_indicators_json = excluded.anomaly_indicators_json,
                    status = excluded.status
                """,
                (
                    alert.alert_id, alert.title, alert.severity, alert.risk_score,
                    alert.confidence, json.dumps(alert.anomaly_indicators),
                    alert.actor_id, alert.destination, alert.status, alert.timestamp
                )
            )
            conn.commit()
        return alert

    def list_exfiltration_alerts(self, status: Optional[str] = None, limit: int = 100) -> List[ExfiltrationAlert]:
        query = "SELECT * FROM dlp_exfiltration_alerts WHERE 1=1"
        params: List[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        alerts: List[ExfiltrationAlert] = []
        with self._lock, self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            for r in rows:
                alerts.append(ExfiltrationAlert(
                    alert_id=r["alert_id"],
                    title=r["title"],
                    severity=r["severity"],
                    risk_score=r["risk_score"],
                    confidence=r["confidence"],
                    anomaly_indicators=json.loads(r["anomaly_indicators_json"] or "[]"),
                    actor_id=r["actor_id"],
                    destination=r["destination"],
                    status=r["status"],
                    timestamp=r["timestamp"],
                ))
        return alerts

    # --- 14. DLP Incidents ---
    def save_incident(self, incident: DLPIncident) -> DLPIncident:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO dlp_incidents (
                    incident_id, title, severity, containment_status,
                    affected_assets_json, evidence_package_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(incident_id) DO UPDATE SET
                    title = excluded.title,
                    severity = excluded.severity,
                    containment_status = excluded.containment_status,
                    affected_assets_json = excluded.affected_assets_json,
                    evidence_package_json = excluded.evidence_package_json,
                    updated_at = excluded.updated_at
                """,
                (
                    incident.incident_id, incident.title, incident.severity,
                    incident.containment_status, json.dumps(incident.affected_assets),
                    json.dumps(incident.evidence_package), incident.created_at, incident.updated_at
                )
            )
            conn.commit()
        return incident

    def get_incident(self, incident_id: str) -> Optional[DLPIncident]:
        with self._lock, self._get_connection() as conn:
            row = conn.execute("SELECT * FROM dlp_incidents WHERE incident_id = ?", (incident_id,)).fetchone()
            if not row:
                return None
            return DLPIncident(
                incident_id=row["incident_id"],
                title=row["title"],
                severity=row["severity"],
                containment_status=row["containment_status"],
                affected_assets=json.loads(row["affected_assets_json"] or "[]"),
                evidence_package=json.loads(row["evidence_package_json"] or "{}"),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def list_incidents(self, containment_status: Optional[str] = None, limit: int = 100) -> List[DLPIncident]:
        query = "SELECT * FROM dlp_incidents WHERE 1=1"
        params: List[Any] = []
        if containment_status:
            query += " AND containment_status = ?"
            params.append(containment_status)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        incidents: List[DLPIncident] = []
        with self._lock, self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            for r in rows:
                incidents.append(DLPIncident(
                    incident_id=r["incident_id"],
                    title=r["title"],
                    severity=r["severity"],
                    containment_status=r["containment_status"],
                    affected_assets=json.loads(r["affected_assets_json"] or "[]"),
                    evidence_package=json.loads(r["evidence_package_json"] or "{}"),
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                ))
        return incidents

    # --- 15. Reports ---
    def save_report(self, report: DLPReport) -> DLPReport:
        with self._lock, self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO dlp_reports (
                    report_id, title, findings_count, blocked_transfers_count,
                    active_alerts_count, sha256_seal, generated_at, report_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_id) DO UPDATE SET
                    title = excluded.title,
                    findings_count = excluded.findings_count,
                    blocked_transfers_count = excluded.blocked_transfers_count,
                    active_alerts_count = excluded.active_alerts_count,
                    sha256_seal = excluded.sha256_seal,
                    generated_at = excluded.generated_at,
                    report_json = excluded.report_json
                """,
                (
                    report.report_id, report.title, report.findings_count,
                    report.blocked_transfers_count, report.active_alerts_count,
                    report.sha256_seal, report.generated_at, json.dumps(report.report_data)
                )
            )
            conn.commit()
        return report

    def get_report(self, report_id: str) -> Optional[DLPReport]:
        with self._lock, self._get_connection() as conn:
            row = conn.execute("SELECT * FROM dlp_reports WHERE report_id = ?", (report_id,)).fetchone()
            if not row:
                return None
            return DLPReport(
                report_id=row["report_id"],
                title=row["title"],
                findings_count=row["findings_count"],
                blocked_transfers_count=row["blocked_transfers_count"],
                active_alerts_count=row["active_alerts_count"],
                sha256_seal=row["sha256_seal"],
                generated_at=row["generated_at"],
                report_data=json.loads(row["report_json"] or "{}"),
            )

    # --- Aggregate Metrics for Operations Center ---
    def get_operations_metrics(self) -> Dict[str, Any]:
        with self._lock, self._get_connection() as conn:
            findings_count = conn.execute("SELECT COUNT(*) FROM dlp_sensitive_findings").fetchone()[0]
            blocked_transfers = conn.execute(
                "SELECT COUNT(*) FROM dlp_transfer_decisions WHERE decision IN ('BLOCK', 'QUARANTINE')"
            ).fetchone()[0]
            active_alerts = conn.execute(
                "SELECT COUNT(*) FROM dlp_exfiltration_alerts WHERE status = 'OPEN'"
            ).fetchone()[0]
            total_events = conn.execute("SELECT COUNT(*) FROM dlp_movement_events").fetchone()[0]
            enforcements_count = conn.execute("SELECT COUNT(*) FROM dlp_enforcement_actions").fetchone()[0]
            unapproved_media = conn.execute(
                "SELECT COUNT(*) FROM dlp_removable_media_events WHERE is_approved_device = 0"
            ).fetchone()[0]
            active_incidents = conn.execute(
                "SELECT COUNT(*) FROM dlp_incidents WHERE containment_status NOT IN ('RESOLVED')"
            ).fetchone()[0]

            return {
                "findings_count": findings_count,
                "blocked_transfers_count": blocked_transfers,
                "active_alerts_count": active_alerts,
                "total_movement_events": total_events,
                "enforcement_actions_count": enforcements_count,
                "unapproved_media_events": unapproved_media,
                "active_incidents_count": active_incidents,
            }
