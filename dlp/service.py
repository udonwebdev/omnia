"""
dlp/service.py
DLPOrchestrator:
Central unified facade for OMNIA Module 52:
Autonomous Data Loss Prevention, Sensitive Information Monitoring & Exfiltration Defense Intelligence.
Singleton instance `dlp_service` provided.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple

from dlp.models import (
    DLPPolicy, DLPPolicyVersion, ProtectedFingerprint, SensitiveFinding,
    MovementEvent, TransferDecision, EnforcementAction, EndpointEnrollment,
    EndpointTelemetry, NetworkTelemetry, CloudEvent, CommunicationEvent,
    RemovableMediaEvent, ExfiltrationAlert, DLPIncident, DLPReport,
    DLPChannel, DLPDecision, FingerprintAlgorithm, DataCategory, SensitivityTier
)
from dlp.persistence import DLPRepository
from dlp.detector import SensitiveContentDetector
from dlp.fingerprint_engine import ContentFingerprintingEngine
from dlp.movement_monitor import DataMovementMonitor
from dlp.exfiltration_engine import ExfiltrationDetectionEngine
from dlp.policy_engine import DLPPolicyEngine
from dlp.transfer_control import TransferControlEngine
from dlp.behavioral_risk import BehavioralRiskEngine
from dlp.incident_manager import DLPIncidentManager
from dlp.simulation import DLPPolicySimulator
from dlp.reporting import DLPReportingEngine

logger = logging.getLogger("omnia.dlp.service")


class DLPOrchestrator:
    """
    Central unified facade managing sensitive content detection, fingerprint tracking,
    movement monitoring, exfiltration defense, policy enforcement, and sealed reporting.
    """

    def __init__(self, db_path: str = "omnia.db"):
        self.repo = DLPRepository(db_path=db_path)
        self.detector = SensitiveContentDetector()
        self.fingerprint_engine = ContentFingerprintingEngine(self.repo)
        self.movement_monitor = DataMovementMonitor(self.repo)
        self.exfiltration_engine = ExfiltrationDetectionEngine(self.repo)
        self.policy_engine = DLPPolicyEngine(self.repo)
        self.transfer_control = TransferControlEngine(self.repo)
        self.behavioral_risk = BehavioralRiskEngine(self.repo)
        self.incident_manager = DLPIncidentManager(self.repo)
        self.simulator = DLPPolicySimulator(self.repo, self.policy_engine)
        self.reporting = DLPReportingEngine(self.repo)

    # --- Tool 1 Facade: Sensitive Information Detection ---
    def detect_sensitive_information(
        self,
        text: str,
        source_ref: str = "payload",
        redact: bool = False
    ) -> Dict[str, Any]:
        """
        Inspects text or payload for sensitive tokens, credentials, PII, and financial identifiers.
        Optionally generates a sanitized, redacted representation.
        """
        findings = self.detector.inspect_content(text, source_ref=source_ref)
        for f in findings:
            self.repo.save_finding(f)

        redacted_text = self.detector.redact_content(text) if redact else None

        return {
            "source_ref": source_ref,
            "findings_count": len(findings),
            "findings": [f.to_dict() for f in findings],
            "redacted_text": redacted_text,
        }

    # --- Tool 2 Facade: Protected Content Fingerprinting ---
    def register_protected_content_fingerprint(
        self,
        name: str,
        content: str | bytes,
        data_category: str = DataCategory.INTELLECTUAL_PROPERTY.value,
        algorithm: str = FingerprintAlgorithm.SHA256_EXACT.value,
        threshold: float = 0.8,
        metadata: Optional[Dict[str, Any]] = None,
        fingerprint_id: Optional[str] = None
    ) -> ProtectedFingerprint:
        """
        Computes and records exact cryptographic file hashes (SHA-256) or rolling block shingles
        for document tracking and partial leak detection.
        """
        return self.fingerprint_engine.register_protected_content(
            name=name,
            content=content,
            data_category=data_category,
            algorithm=algorithm,
            threshold=threshold,
            metadata=metadata,
            fingerprint_id=fingerprint_id
        )

    # --- Tool 3 Facade: Movement Policy Evaluation ---
    def evaluate_data_movement_policy(
        self,
        actor_id: str,
        device_id: str,
        source_location: str,
        destination_location: str,
        channel: str,
        volume_bytes: int,
        payload_text: Optional[str] = None,
        is_authorized: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
        event_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Ingests a data movement event, detects sensitive tokens/fingerprints,
        evaluates exfiltration anomalies, and produces an authoritative DLP policy decision.
        """
        # 1. Ingest movement event
        event = self.movement_monitor.record_movement(
            actor_id=actor_id,
            device_id=device_id,
            source_location=source_location,
            destination_location=destination_location,
            channel=channel,
            volume_bytes=volume_bytes,
            is_authorized=is_authorized,
            metadata=metadata,
            event_id=event_id,
        )

        # 2. Inspect payload content if available
        findings: List[SensitiveFinding] = []
        matched_fps: List[Tuple[ProtectedFingerprint, float]] = []
        if payload_text:
            findings = self.detector.inspect_content(payload_text, source_ref=f"event:{event.event_id}")
            for f in findings:
                self.repo.save_finding(f)
            matched_fps = self.fingerprint_engine.match_content(payload_text)

        # 3. Analyze exfiltration risk
        risk_score, indicators, severity, alert = self.exfiltration_engine.evaluate_movement_risk(
            event=event,
            findings=findings
        )

        # 4. Evaluate against active DLP policies
        decision = self.policy_engine.evaluate_movement(
            event=event,
            findings=findings,
            alert=alert,
            matched_fingerprints=matched_fps
        )

        return {
            "event": event.to_dict(),
            "findings": [f.to_dict() for f in findings],
            "matched_fingerprints": [
                {"fingerprint": fp.to_dict(), "similarity": score}
                for fp, score in matched_fps
            ],
            "exfiltration_risk": {
                "score": risk_score,
                "severity": severity.value,
                "indicators": indicators,
                "alert_id": alert.alert_id if alert else None,
            },
            "transfer_decision": decision.to_dict(),
        }

    # --- Tool 4 Facade: Exfiltration Anomaly Detection ---
    def detect_data_exfiltration_anomalies(
        self,
        event_id: str,
        custom_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Analyzes transfer patterns for exfiltration anomalies, computing explainable risk scores
        and correlating insider risk signals.
        """
        event = self.repo.get_movement_event(event_id)
        if not event:
            raise ValueError(f"Movement event '{event_id}' not found.")

        findings = self.repo.list_findings(source_ref=f"event:{event.event_id}")
        risk_score, indicators, severity, alert = self.exfiltration_engine.evaluate_movement_risk(
            event=event,
            findings=findings,
            custom_context=custom_context
        )

        # Assess actor behavioral profile
        insider_score, insider_factors, review_rec = self.behavioral_risk.assess_actor_behavior(
            actor_id=event.actor_id
        )

        return {
            "event_id": event_id,
            "risk_score": risk_score,
            "severity": severity.value,
            "anomaly_indicators": indicators,
            "alert": alert.to_dict() if alert else None,
            "insider_behavior": {
                "insider_risk_score": insider_score,
                "correlated_factors": insider_factors,
                "review_recommendation": review_rec,
            }
        }

    # --- Tool 5 Facade: Transfer Enforcement Execution ---
    def execute_dlp_enforcement_action(
        self,
        decision_id: str,
        approval_token: Optional[str] = None,
        is_simulation: bool = False
    ) -> EnforcementAction:
        """
        Executes and verifies a real-time transfer control action (BLOCK, QUARANTINE, REDACT)
        with fail-closed validation and M20 human-in-the-loop approval checks.
        """
        decision = self.repo.get_transfer_decision(decision_id)
        if not decision:
            raise ValueError(f"Transfer decision '{decision_id}' not found.")

        event = self.repo.get_movement_event(decision.event_id)
        if not event:
            raise ValueError(f"Movement event '{decision.event_id}' associated with decision not found.")

        return self.transfer_control.execute_decision(
            decision=decision,
            event=event,
            approval_token=approval_token,
            is_simulation=is_simulation
        )

    # --- Tool 6 Facade: Operations Center Sealed Reporting ---
    def generate_dlp_operations_report(
        self,
        title: str = "OMNIA DLP Operations Intelligence Report",
        reporting_actor: str = "dlp_operations_officer",
        metadata: Optional[Dict[str, Any]] = None
    ) -> DLPReport:
        """
        Compiles persisted DLP operational metrics into a cryptographically sealed report.
        """
        return self.reporting.generate_operations_report(
            title=title,
            reporting_actor=reporting_actor,
            metadata=metadata
        )


# Singleton instance
dlp_service = DLPOrchestrator()
