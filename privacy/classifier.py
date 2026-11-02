"""
privacy/classifier.py
Data Classification Engine executing rule-based, regex-based, and metadata-based
classification for sensitive fields (SSN, Email, Credit Card, IP, Phone, Password,
Health tokens, Biometrics, Financial tokens) with confidence scoring.
"""

import re
import uuid
import time
import logging
from typing import List, Dict, Any, Optional, Tuple

from privacy.models import DataClassification, DataCategory, SensitivityTier
from privacy.persistence import PrivacyRepository

logger = logging.getLogger("omnia.privacy.classifier")


def luhn_checksum_valid(card_num: str) -> bool:
    """Validates credit card numbers using the Luhn algorithm."""
    digits = [int(c) for c in re.sub(r"\D", "", card_num)]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        if i % 2 == 1:
            doubled = d * 2
            checksum += (doubled - 9) if doubled > 9 else doubled
        else:
            checksum += d
    return checksum % 10 == 0


class DataClassificationEngine:
    # Regex patterns for value-based classification
    PATTERNS = {
        "SSN": (re.compile(r"^\d{3}-\d{2}-\d{4}$|^\d{9}$"), DataCategory.GOV_ID, SensitivityTier.HIGHLY_RESTRICTED, 0.95),
        "CREDIT_CARD": (re.compile(r"^(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11}|6(?:011|5[0-9]{2})[0-9]{12}|(?:2131|1800|35\d{3})\d{11})$"), DataCategory.FINANCIAL, SensitivityTier.HIGHLY_RESTRICTED, 0.98),
        "EMAIL": (re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"), DataCategory.PII, SensitivityTier.CONFIDENTIAL, 0.95),
        "PHONE": (re.compile(r"^(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}$"), DataCategory.PII, SensitivityTier.CONFIDENTIAL, 0.90),
        "IPV4": (re.compile(r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"), DataCategory.LOCATION, SensitivityTier.INTERNAL, 0.85),
        "IBAN": (re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$"), DataCategory.FINANCIAL, SensitivityTier.RESTRICTED, 0.92),
    }

    # Field name semantic heuristics
    FIELD_NAME_RULES = [
        # (keywords, category, tier, confidence, rule_name)
        (["ssn", "social_security", "social_sec"], DataCategory.GOV_ID, SensitivityTier.HIGHLY_RESTRICTED, 0.92, "NAME_SSN"),
        (["passport", "driver_license", "dl_number", "national_id"], DataCategory.GOV_ID, SensitivityTier.HIGHLY_RESTRICTED, 0.90, "NAME_GOV_ID"),
        (["credit_card", "card_num", "pan", "cvv", "cvc", "card_number"], DataCategory.FINANCIAL, SensitivityTier.HIGHLY_RESTRICTED, 0.95, "NAME_CARD"),
        (["bank_account", "routing_number", "iban", "account_num", "swift"], DataCategory.FINANCIAL, SensitivityTier.RESTRICTED, 0.88, "NAME_BANK"),
        (["email", "mail_address", "e_mail"], DataCategory.PII, SensitivityTier.CONFIDENTIAL, 0.90, "NAME_EMAIL"),
        (["phone", "mobile", "telephone", "cell_phone"], DataCategory.PII, SensitivityTier.CONFIDENTIAL, 0.85, "NAME_PHONE"),
        (["password", "passwd", "pwd", "secret_key", "api_key", "auth_token", "private_key"], DataCategory.CREDENTIALS, SensitivityTier.HIGHLY_RESTRICTED, 0.96, "NAME_CREDENTIALS"),
        (["diagnosis", "mrn", "health", "prescription", "medical", "patient", "clinical"], DataCategory.HEALTH, SensitivityTier.HIGHLY_RESTRICTED, 0.92, "NAME_HEALTH"),
        (["biometric", "fingerprint", "iris", "retina", "face_encoding"], DataCategory.BIOMETRIC, SensitivityTier.HIGHLY_RESTRICTED, 0.95, "NAME_BIOMETRIC"),
        (["latitude", "longitude", "gps", "geo_loc", "postal_code", "zipcode", "street_address"], DataCategory.LOCATION, SensitivityTier.CONFIDENTIAL, 0.82, "NAME_LOCATION"),
        (["full_name", "first_name", "last_name", "birth_date", "dob", "gender"], DataCategory.PII, SensitivityTier.CONFIDENTIAL, 0.80, "NAME_PII"),
    ]

    def __init__(self, repo: PrivacyRepository):
        self.repo = repo

    def classify_field(
        self,
        asset_id: str,
        field_name: str,
        sample_values: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> DataClassification:
        """Classifies a specific field using name analysis, metadata, and sample value regex matching."""
        cid = f"cls_{uuid.uuid4().hex[:12]}"
        now = time.time()
        norm_name = field_name.lower().strip()

        matched_category = DataCategory.CONFIDENTIAL_BIZ
        matched_tier = SensitivityTier.INTERNAL
        confidence = 0.50
        rule_name = "DEFAULT_HEURISTIC"

        # 1. Check Field Name Rules
        for keywords, cat, tier, conf, rname in self.FIELD_NAME_RULES:
            if any(k in norm_name for k in keywords):
                matched_category = cat
                matched_tier = tier
                confidence = conf
                rule_name = rname
                break

        # 2. Check Sample Values if provided
        if sample_values:
            cleaned_samples = [str(s).strip() for s in sample_values if s is not None and str(s).strip()]
            for val in cleaned_samples[:20]:
                # Luhn check for card
                if re.sub(r"[\s-]", "", val).isdigit() and luhn_checksum_valid(val):
                    matched_category = DataCategory.FINANCIAL
                    matched_tier = SensitivityTier.HIGHLY_RESTRICTED
                    confidence = 0.99
                    rule_name = "REGEX_LUHN_CREDIT_CARD"
                    break

                for pname, (pattern, cat, tier, conf) in self.PATTERNS.items():
                    if pattern.match(val):
                        # Escalate if regex match is stronger
                        if conf > confidence or SensitivityTier.rank(tier) > SensitivityTier.rank(matched_tier):
                            matched_category = cat
                            matched_tier = tier
                            confidence = conf
                            rule_name = f"REGEX_{pname}"
                        break

        classification = DataClassification(
            class_id=cid,
            asset_id=asset_id,
            field_name=field_name,
            category=matched_category,
            sensitivity_tier=matched_tier,
            confidence=round(confidence, 2),
            rule_matched=rule_name,
            classified_at=now
        )
        saved = self.repo.save_classification(classification)
        logger.debug(f"Classified {asset_id}.{field_name} -> {matched_category.value} ({matched_tier.value}, conf={confidence:.2f})")
        return saved

    def classify_schema(
        self,
        asset_id: str,
        fields: List[Dict[str, Any]]
    ) -> List[DataClassification]:
        """Classifies a list of fields for an asset schema."""
        results = []
        for f in fields:
            fname = f.get("name") or f.get("field_name")
            if not fname:
                continue
            samples = f.get("sample_values") or f.get("samples") or []
            meta = f.get("metadata") or {}
            c = self.classify_field(asset_id=asset_id, field_name=fname, sample_values=samples, metadata=meta)
            results.append(c)
        return results
