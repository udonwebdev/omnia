"""
OMNIA Module 35: Threat Intelligence Manager & Indicator Validator
Validates external defensive threat intelligence, enforces source trust, detects poisoned feeds,
and manages indicator expiration and revocation.
"""

import time
import re
import ipaddress
import hashlib
import logging
from typing import Dict, Any, List, Optional, Tuple
from defense.models import (
    ThreatIndicator,
    IndicatorType,
    IndicatorValidationStatus,
    ThreatClassification,
)

logger = logging.getLogger("Omnia.Defense.Intelligence")


class IndicatorValidator:
    """Validates structural and semantic correctness of threat indicators."""

    MD5_REGEX = re.compile(r"^[a-fA-F0-9]{32}$")
    SHA1_REGEX = re.compile(r"^[a-fA-F0-9]{40}$")
    SHA256_REGEX = re.compile(r"^[a-fA-F0-9]{64}$")
    DOMAIN_REGEX = re.compile(r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$")
    URL_REGEX = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)

    # Disallowed/Reserved IP ranges for external threat indicators (anti-poisoning)
    RESERVED_NETWORKS = [
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("169.254.0.0/16"),
        ipaddress.ip_network("::1/128"),
    ]

    # Whitelisted internal/essential domains that must never be blocked via poisoned external feeds
    INTERNAL_WHITELIST_DOMAINS = {
        "localhost",
        "omniacloud.internal",
        "omnia.mesh",
        "github.com",
        "stripe.com",
        "slack.com",
    }

    def validate_indicator(self, ind_type: IndicatorType, value: str) -> Tuple[bool, str]:
        """Validates format, boundaries, and ensures essential assets are not poisoned."""
        val = value.strip()
        if not val:
            return False, "Indicator value cannot be empty."

        if ind_type == IndicatorType.IP_ADDRESS:
            try:
                ip_obj = ipaddress.ip_address(val)
                for net in self.RESERVED_NETWORKS:
                    if ip_obj in net:
                        return False, f"Anti-poisoning block: IP '{val}' belongs to private/internal network {net}."
                return True, "Valid public IP"
            except ValueError:
                return False, f"Invalid IP address format: '{val}'"

        elif ind_type == IndicatorType.DOMAIN:
            domain_clean = val.lower().rstrip(".")
            if domain_clean in self.INTERNAL_WHITELIST_DOMAINS or domain_clean.endswith(".internal") or domain_clean.endswith(".mesh"):
                return False, f"Anti-poisoning block: Domain '{val}' is whitelisted internal infrastructure."
            if not self.DOMAIN_REGEX.match(domain_clean):
                return False, f"Invalid domain name format: '{val}'"
            return True, "Valid domain"

        elif ind_type == IndicatorType.URL:
            if not self.URL_REGEX.match(val):
                return False, f"Invalid URL format: '{val}'"
            return True, "Valid URL"

        elif ind_type == IndicatorType.FILE_HASH:
            if self.MD5_REGEX.match(val) or self.SHA1_REGEX.match(val) or self.SHA256_REGEX.match(val):
                return True, "Valid cryptographic hash"
            return False, f"Invalid hash format (must be MD5, SHA-1, or SHA-256): '{val}'"

        elif ind_type in {IndicatorType.VULNERABILITY_ID, IndicatorType.ATTACK_PATTERN, IndicatorType.MALWARE_SIGNATURE}:
            if len(val) < 3 or len(val) > 256:
                return False, "Identifier length must be between 3 and 256 characters."
            return True, "Valid identifier"

        elif ind_type == IndicatorType.COMPROMISED_CREDENTIAL:
            # We never store the plaintext credential; only redacted fingerprints or hash digests
            if len(val) < 8:
                return False, "Compromised credential indicator must be a valid fingerprint digest."
            return True, "Valid credential fingerprint"

        return False, f"Unsupported indicator type: '{ind_type}'"


class ThreatIntelligenceManager:
    """Manages threat feed ingestion, indicator validation, trust scoring, and lifecycle expiration."""

    def __init__(self, validator: Optional[IndicatorValidator] = None):
        self.validator = validator or IndicatorValidator()
        self._indicators: Dict[str, ThreatIndicator] = {}
        self._trusted_sources: Dict[str, float] = {
            "internal_sentinel": 0.95,
            "circl_osint": 0.75,
            "abuse_ch": 0.80,
            "cisa_known_exploited": 0.90,
            "untrusted_feed": 0.20,
        }

    def register_trusted_source(self, source_name: str, reliability: float) -> None:
        """Registers or updates a threat feed provider with an authoritative reliability score."""
        self._trusted_sources[source_name] = max(0.0, min(1.0, reliability))

    def ingest_indicator(
        self,
        indicator_id: str,
        indicator_type: IndicatorType,
        indicator_value: str,
        source: str,
        confidence: float = 0.5,
        ttl_seconds: float = 86400.0,  # 24 hours default
        threat_classification: ThreatClassification = ThreatClassification.ANOMALOUS_BEHAVIOR,
        context: Optional[Dict[str, Any]] = None,
        applicable_scope: str = "GLOBAL",
    ) -> ThreatIndicator:
        """Ingests, validates, scores, and stores a defensive threat intelligence indicator."""
        # 1. Structural and Anti-Poisoning Validation
        is_valid, reason = self.validator.validate_indicator(indicator_type, indicator_value)
        status = IndicatorValidationStatus.VALIDATED if is_valid else IndicatorValidationStatus.REJECTED

        source_reliability = self._trusted_sources.get(source, 0.40)
        now = time.time()
        expires_at = now + ttl_seconds if ttl_seconds > 0 else None

        indicator = ThreatIndicator(
            indicator_id=indicator_id,
            indicator_type=indicator_type,
            indicator_value=indicator_value,
            source=source,
            source_reliability=source_reliability,
            confidence=max(0.0, min(1.0, confidence)),
            first_seen=now,
            last_seen=now,
            expires_at=expires_at,
            context=context or {"validation_reason": reason},
            threat_classification=threat_classification,
            validation_status=status,
            applicable_scope=applicable_scope,
        )

        if not is_valid:
            logger.warning(f"Threat indicator '{indicator_id}' rejected by validator: {reason}")

        self._indicators[indicator_id] = indicator
        return indicator

    def lookup_indicator(self, value: str, current_time: Optional[float] = None) -> Optional[ThreatIndicator]:
        """Looks up an active, non-expired, validated indicator matching a query value."""
        now = current_time or time.time()
        clean_val = value.strip().lower()

        for ind in self._indicators.values():
            if ind.indicator_value.lower() == clean_val:
                if ind.validation_status != IndicatorValidationStatus.VALIDATED:
                    continue
                if ind.is_expired(now):
                    ind.validation_status = IndicatorValidationStatus.EXPIRED
                    continue
                return ind
        return None

    def revoke_indicator(self, indicator_id: str, reason: str) -> bool:
        """Revokes an indicator (e.g. false positive confirmation)."""
        ind = self._indicators.get(indicator_id)
        if ind:
            ind.validation_status = IndicatorValidationStatus.REVOKED
            ind.context["revocation_reason"] = reason
            return True
        return False
