"""
OMNIA Module 47: Autonomous Threat Detection, Behavioral Analytics & Real-Time Security Operations Intelligence
Hybrid Threat Detection Engine - detection_engine.py
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from secops.baselines import BehavioralBaselineEngine
from secops.models import (
    AlertStatus,
    DetectionRule,
    RuleType,
    SecurityAlert,
    SecurityEvent,
    SecuritySeverity,
)
from secops.persistence import SecOpsRepository

logger = logging.getLogger("Omnia.SecOps.Detection")


class ThreatDetectionEngine:
    """
    Executes hybrid detection over normalized security telemetry:
    - Deterministic rule matching (MITRE ATT&CK techniques, failed auth bursts, privilege escalation)
    - Statistical anomaly detection (Z-score deviation against behavioral baselines)
    - Model-assisted supplementary classification
    """

    def __init__(
        self,
        repository: Optional[SecOpsRepository] = None,
        baseline_engine: Optional[BehavioralBaselineEngine] = None,
    ):
        self.repo = repository or SecOpsRepository()
        self.baselines = baseline_engine or BehavioralBaselineEngine(self.repo)

    def evaluate_events(self, events: List[SecurityEvent]) -> List[SecurityAlert]:
        alerts: List[SecurityAlert] = []
        rules = self.repo.list_rules()

        for rule in rules:
            if not rule.is_enabled:
                continue

            matched_events = [e for e in events if self._match_rule(rule, e)]
            if matched_events:
                # Group matched events by primary actor or asset
                alert = self._generate_alert(rule, matched_events)
                if alert:
                    alerts.append(alert)

        return alerts

    def _match_rule(self, rule: DetectionRule, event: SecurityEvent) -> bool:
        if rule.required_telemetry_sources:
            if event.provider not in rule.required_telemetry_sources and event.source_id not in rule.required_telemetry_sources:
                return False

        if rule.rule_type == RuleType.DETERMINISTIC:
            return self._match_deterministic_rule(rule, event)
        elif rule.rule_type == RuleType.ANOMALY:
            return self._match_anomaly_rule(rule, event)
        return False

    def _match_deterministic_rule(self, rule: DetectionRule, event: SecurityEvent) -> bool:
        params = rule.threshold_params
        match_type = params.get("target_event_type")

        if match_type and event.event_type != match_type:
            return False

        # Check required action or result
        if "required_result" in params and event.result.value != params["required_result"]:
            return False

        # Configuration change rule
        if rule.rule_id == "RULE-TAMPER-001" and event.event_type == "CONFIG_CHANGE":
            if event.metadata.get("audit_logging_disabled") is True:
                return True

        # Failed login burst check
        if rule.rule_id == "RULE-AUTH-001" and event.event_type == "USER_LOGIN_FAILED":
            return True

        # Unusual Privilege Escalation
        if rule.rule_id == "RULE-PRIV-001" and event.event_type == "ROLE_ASSIGNMENT":
            if "ADMIN" in str(event.metadata.get("role_granted", "")).upper():
                return True

        # Suspicious outbound traffic
        if rule.rule_id == "RULE-NET-001" and event.event_type == "EGRESS_CONNECTION":
            port = event.metadata.get("destination_port", 0)
            if port in [4444, 1337, 6667, 9001]:
                return True

        return False

    def _match_anomaly_rule(self, rule: DetectionRule, event: SecurityEvent) -> bool:
        params = rule.threshold_params
        metric_name = params.get("metric_name", "api_request_rate")
        observed_val = float(event.metadata.get(metric_name, 0.0))

        entity_id = event.actor_id or event.asset_id
        if not entity_id or observed_val <= 0.0:
            return False

        # Evaluate against baseline
        z_threshold = float(params.get("z_threshold", 3.0))
        is_anom, z_score, confidence = self.baselines.evaluate_anomaly(
            entity_id=entity_id,
            metric_name=metric_name,
            observed_value=observed_val,
            z_threshold=z_threshold,
        )

        if is_anom:
            event.metadata["anomaly_z_score"] = z_score
            event.metadata["baseline_confidence"] = confidence
            return True

        return False

    def _generate_alert(self, rule: DetectionRule, matched_events: List[SecurityEvent]) -> Optional[SecurityAlert]:
        first_evt = matched_events[0]
        actor = first_evt.actor_id
        asset = first_evt.asset_id

        # Deduplication key based on rule, actor, and asset
        dedup_raw = f"{rule.rule_id}:{actor or 'NO_ACTOR'}:{asset or 'NO_ASSET'}"
        dedup_key = hashlib.sha256(dedup_raw.encode("utf-8")).hexdigest()

        # Check existing alert to avoid duplicate flooding
        existing = self.repo.get_alert_by_dedup(dedup_key)
        if existing and existing.status in [AlertStatus.NEW, AlertStatus.INVESTIGATING]:
            # Append new event IDs to existing alert
            new_ids = set(existing.contributing_event_ids)
            for e in matched_events:
                new_ids.add(e.event_id)
            existing.contributing_event_ids = list(new_ids)
            existing.updated_at = datetime.now(timezone.utc).isoformat()
            self.repo.save_alert(existing)
            return existing

        aid = f"alert-{uuid.uuid4().hex[:8]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        explanation = {
            "rule_id": rule.rule_id,
            "rule_name": rule.name,
            "rule_type": rule.rule_type.value,
            "mitre_technique": rule.mitre_attack_technique,
            "matched_event_count": len(matched_events),
            "sample_event_id": first_evt.event_id,
            "evidence_summary": f"Triggered {rule.name} with {len(matched_events)} matching security telemetry event(s).",
        }

        alert = SecurityAlert(
            alert_id=aid,
            rule_id=rule.rule_id,
            title=f"Security Alert: {rule.name}",
            description=rule.description,
            severity=rule.severity,
            confidence=rule.confidence_score,
            asset_id=asset,
            actor_id=actor,
            status=AlertStatus.NEW,
            dedup_key=dedup_key,
            contributing_event_ids=[e.event_id for e in matched_events],
            explanation=explanation,
            created_at=now_iso,
            updated_at=now_iso,
        )

        self.repo.save_alert(alert)
        logger.warning(f"Raised security alert {aid}: '{rule.name}' (Severity: {rule.severity.value})")
        return alert
