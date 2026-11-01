"""
OMNIA Module 46: Autonomous Application Security Testing, Vulnerability Intelligence & Defensive Validation
Security Audit Engine - security_audit.py

Provides an immutable, append-only record of all security assessment actions,
target authorizations, and remediation workflows.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app_security.models import SecurityAuditRecord
from app_security.persistence import AppSecurityRepository

logger = logging.getLogger("Omnia.AppSecurity.AuditEngine")


class SecurityAuditEngine:
    """
    Records and queries security audit events.
    """

    def __init__(self, repository: Optional[AppSecurityRepository] = None):
        self.repo = repository or AppSecurityRepository()

    def record_audit_event(
        self,
        action_type: str,
        actor: str,
        authorization_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> SecurityAuditRecord:
        aid = f"audit-{uuid.uuid4().hex[:8]}"
        rec = SecurityAuditRecord(
            audit_id=aid,
            authorization_id=authorization_id,
            asset_id=asset_id,
            action_type=action_type,
            actor=actor,
            details=details or {},
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        self.repo.save_audit_record(rec)
        return rec
