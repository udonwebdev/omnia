"""
OMNIA Module 45: Autonomous Quality Assurance, Software Verification & Continuous Testing Intelligence
Test Data Manager - test_data_manager.py

Generates deterministic synthetic fixtures, manages isolated test datasets,
and enforces sensitive data redaction.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Any, Dict, List

logger = logging.getLogger("Omnia.QAVerification.TestDataManager")


class TestDataManager:
    """
    Supplies controlled, isolated fixtures for testing without polluting real environments.
    """

    def generate_fixture(self, schema_name: str, seed: int = 42) -> Dict[str, Any]:
        h = hashlib.sha256(f"{schema_name}:{seed}".encode()).hexdigest()
        return {
            "fixture_id": f"fix-{uuid.uuid4().hex[:8]}",
            "schema": schema_name,
            "seed": seed,
            "fingerprint": h[:12],
            "record": {
                "id": f"user_{h[:6]}",
                "email": f"test_{h[:6]}@omnia.mock",
                "role": "QA_PRINCIPAL",
                "quota": 1000,
            },
        }

    def mask_sensitive_data(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Redacts passwords, tokens, and secret keys."""
        masked = dict(payload)
        for k in list(masked.keys()):
            if any(term in k.lower() for term in ("password", "secret", "token", "key", "auth")):
                masked[k] = "[REDACTED_BY_QA]"
        return masked
