"""
OMNIA Module 35: Threat Detection Engine & Behavioral Anomaly Detector
Evaluates normalized telemetry against deterministic security rules and baseline statistics.
Generates explainable ThreatAlerts separating confidence, severity, and urgency.
"""

import time
import uuid
import logging
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict

from defense.models import (
    SecurityTelemetryEvent,
    SecurityDetectionRule,
    ThreatAlert,
    ThreatClassification,
    SecuritySeverity,
    ResponseAutonomyLevel,
)
from defense.intelligence import ThreatIntelligenceManager

logger = logging.getLogger("Omnia.Defense.Detector")


class BehavioralAnomalyDetector:
    """Maintains statistical baseline profiles to detect rate and frequency anomalies."""

    def __init__(self, window_sec: float = 60.0, rate_threshold: int = 5):
        self.window_sec = window_sec
        self.rate_threshold = rate_threshold
        # Key: (source_identity, action_category) -> List[timestamp]
        self._action_windows: Dict[Tuple[str, str], List[float]] = defaultdict(list)

    def record_and_evaluate(
        self,
        source_identity: str,
        action_category: str,
        timestamp: Optional[float] = None
    ) -> Tuple[bool, float, str]:
        """Evaluates whether an entity has exceeded baseline frequency bounds."""
        now = timestamp or time.time()
        key = (source_identity, action_category)
        history = self._action_windows[key]

        # Prune older entries
        cutoff = now - self.window_sec
        self._action_windows[key] = [t for t in history if t >= cutoff]
        self._action_windows[key].append(now)

        count = len(self._action_windows[key])
        if count > self.rate_threshold:
            anomaly_score = min(1.0, count / (self.rate_threshold * 2))
            explanation = (
                f"Rate anomaly: Entity '{source_identity}' performed {count} '{action_category}' "
                f"actions within {self.window_sec}s (Threshold: {self.rate_threshold})."
            )
            return True, anomaly_score, explanation
        return False, 0.0, "Within normal bounds"


class ThreatDetectionEngine:
    """Executes deterministic rules and intelligence correlation over security events."""

    def __init__(self, intel_mgr: Optional[ThreatIntelligenceManager] = None):
        self.intel_mgr = intel_mgr or ThreatIntelligenceManager()
        self.anomaly_detector = BehavioralAnomalyDetector()
        self._rules: Dict[str, SecurityDetectionRule] = {}
        self._suppression_cache: Dict[str, float] = {}  # suppression_key -> last_alert_time
        self._load_builtin_rules()

    def _load_builtin_rules(self) -> None:
        """Registers foundational deterministic rules for Omnia runtime operations."""
        builtin = [
            SecurityDetectionRule(
                rule_id="RULE-AUTH-001",
                name="Repeated Authentication Failures",
                description="Detects multiple authentication failures from the same source identity or node.",
                threat_classification=ThreatClassification.UNAUTHORIZED_ACCESS,
                severity=SecuritySeverity.HIGH,
                required_telemetry_types=["auth.login", "auth.token_validate"],
                matching_criteria={"outcome": "FAILURE"},
                confidence=0.85,
                suppression_window_sec=30.0,
                expected_response_level=ResponseAutonomyLevel.LEVEL_2_LOW_RISK_AUTO,
            ),
            SecurityDetectionRule(
                rule_id="RULE-CAP-002",
                name="Unauthorized Capability Invocation",
                description="Detects execution attempts on unapproved or restricted capabilities.",
                threat_classification=ThreatClassification.CAPABILITY_ABUSE,
                severity=SecuritySeverity.CRITICAL,
                required_telemetry_types=["capability.execute", "skill.invoke"],
                matching_criteria={"outcome": "PERMISSION_DENIED"},
                confidence=0.95,
                suppression_window_sec=60.0,
                expected_response_level=ResponseAutonomyLevel.LEVEL_3_APPROVAL_REQUIRED,
            ),
            SecurityDetectionRule(
                rule_id="RULE-SEC-003",
                name="Suspicious Secret Access Pattern",
                description="Detects access to sensitive credentials or secret leases from unauthorized caller.",
                threat_classification=ThreatClassification.CREDENTIAL_EXPOSURE,
                severity=SecuritySeverity.CRITICAL,
                required_telemetry_types=["secrets.lease", "secrets.access"],
                matching_criteria={"outcome": "ACCESS_DENIED"},
                confidence=0.90,
                suppression_window_sec=45.0,
                expected_response_level=ResponseAutonomyLevel.LEVEL_3_APPROVAL_REQUIRED,
            ),
            SecurityDetectionRule(
                rule_id="RULE-DIST-004",
                name="Distributed Split-Brain or Stale Epoch Fencing",
                description="Detects distributed node attempting commands with invalid leadership epoch.",
                threat_classification=ThreatClassification.DISTRIBUTED_SPLIT_BRAIN,
                severity=SecuritySeverity.HIGH,
                required_telemetry_types=["coordination.fencing", "consensus.claim"],
                matching_criteria={"outcome": "FENCED_STALE_EPOCH"},
                confidence=0.92,
                suppression_window_sec=30.0,
                expected_response_level=ResponseAutonomyLevel.LEVEL_2_LOW_RISK_AUTO,
            ),
        ]
        for r in builtin:
            self._rules[r.rule_id] = r

    def register_rule(self, rule: SecurityDetectionRule) -> None:
        """Registers or updates a detection rule."""
        self._rules[rule.rule_id] = rule

    def evaluate_event(self, event: SecurityTelemetryEvent) -> List[ThreatAlert]:
        """Evaluates a single telemetry event against rules, threat intelligence, and anomaly detector."""
        alerts = []
        now = event.timestamp

        # 1. Deterministic Rule Matching
        for rule in self._rules.values():
            if not rule.is_active:
                continue
            
            # Match required telemetry types
            if rule.required_telemetry_types and event.action_category not in rule.required_telemetry_types:
                continue

            # Match criteria
            match = True
            for k, expected_v in rule.matching_criteria.items():
                if k == "outcome" and event.outcome != expected_v:
                    match = False
                    break
                elif k in event.details and event.details[k] != expected_v:
                    match = False
                    break

            if match:
                supp_key = f"{rule.rule_id}:{event.source_identity or event.node_identity or 'unknown'}"
                last_fired = self._suppression_cache.get(supp_key, 0.0)
                if (now - last_fired) < rule.suppression_window_sec:
                    continue  # Suppressed

                self._suppression_cache[supp_key] = now
                alert = ThreatAlert(
                    alert_id=f"alert-{uuid.uuid4().hex[:8]}",
                    rule_id=rule.rule_id,
                    title=rule.name,
                    threat_classification=rule.threat_classification,
                    severity=rule.severity,
                    confidence=rule.confidence,
                    trigger_event_ids=[event.event_id],
                    affected_resources=[event.resource_reference] if event.resource_reference else [event.source_component],
                    explanation=f"{rule.description} (Outcome: {event.outcome})",
                    timestamp=now,
                    source_identity=event.source_identity,
                    node_identity=event.node_identity,
                    suggested_response_level=rule.expected_response_level,
                )
                alerts.append(alert)

        # 2. Threat Intelligence Indicator Lookup (e.g., target resource or connection)
        if event.resource_reference:
            matched_ind = self.intel_mgr.lookup_indicator(event.resource_reference, now)
            if matched_ind:
                alert = ThreatAlert(
                    alert_id=f"alert-ti-{uuid.uuid4().hex[:8]}",
                    rule_id="RULE-INTEL-MATCH",
                    title=f"Threat Intelligence Hit: {matched_ind.indicator_value}",
                    threat_classification=matched_ind.threat_classification,
                    severity=SecuritySeverity.HIGH if matched_ind.confidence > 0.7 else SecuritySeverity.MEDIUM,
                    confidence=matched_ind.confidence * matched_ind.source_reliability,
                    trigger_event_ids=[event.event_id],
                    affected_resources=[event.resource_reference],
                    explanation=(
                        f"Resource matches active intelligence indicator '{matched_ind.indicator_value}' "
                        f"(Source: {matched_ind.source}, Type: {matched_ind.indicator_type.value})"
                    ),
                    timestamp=now,
                    source_identity=event.source_identity,
                    node_identity=event.node_identity,
                    suggested_response_level=ResponseAutonomyLevel.LEVEL_2_LOW_RISK_AUTO,
                )
                alerts.append(alert)

        # 3. Behavioral Anomaly Detection
        if event.source_identity:
            is_anomaly, score, explanation = self.anomaly_detector.record_and_evaluate(
                event.source_identity, event.action_category, now
            )
            if is_anomaly:
                alert = ThreatAlert(
                    alert_id=f"alert-anom-{uuid.uuid4().hex[:8]}",
                    rule_id="RULE-BEHAVIORAL-ANOMALY",
                    title=f"Behavioral Anomaly: {event.action_category}",
                    threat_classification=ThreatClassification.ANOMALOUS_BEHAVIOR,
                    severity=SecuritySeverity.MEDIUM if score < 0.8 else SecuritySeverity.HIGH,
                    confidence=score,
                    trigger_event_ids=[event.event_id],
                    affected_resources=[event.source_identity],
                    explanation=explanation,
                    timestamp=now,
                    source_identity=event.source_identity,
                    node_identity=event.node_identity,
                    suggested_response_level=ResponseAutonomyLevel.LEVEL_1_RECOMMEND,
                )
                alerts.append(alert)

        return alerts
