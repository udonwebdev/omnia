import time
from typing import Dict, Any, Optional
from secrets.models import SecretTelemetry, SecretStatus
from secrets.persistence import SecretPersistence

class SecretTelemetryCollector:
    """Collects safe operational metrics for secrets without revealing sensitive values."""

    def __init__(self, persistence: Optional[SecretPersistence] = None):
        self.persistence = persistence or SecretPersistence()
        self.granted_count = 0
        self.denied_count = 0
        self.rotation_success = 0
        self.rotation_failures = 0

    def record_access_granted(self):
        self.granted_count += 1

    def record_access_denied(self):
        self.denied_count += 1

    def record_rotation_result(self, success: bool):
        if success:
            self.rotation_success += 1
        else:
            self.rotation_failures += 1

    def get_telemetry(self) -> SecretTelemetry:
        now = time.time()
        secrets = self.persistence.list_secrets_metadata()
        active_leases = self.persistence.list_active_leases()

        expiring_soon = 0
        revoked = 0
        compromised = 0

        for s in secrets:
            if s.status == SecretStatus.REVOKED:
                revoked += 1
            elif s.status == SecretStatus.COMPROMISED:
                compromised += 1

            if s.expires_at and (s.expires_at - now) < 86400.0 and s.status == SecretStatus.ACTIVE:
                expiring_soon += 1

        return SecretTelemetry(
            total_secrets=len(secrets),
            active_leases=len(active_leases),
            expiring_soon_count=expiring_soon,
            revoked_count=revoked,
            compromised_count=compromised,
            access_requests_granted=self.granted_count,
            access_requests_denied=self.denied_count,
            rotation_success_count=self.rotation_success,
            rotation_failure_count=self.rotation_failures,
            last_updated=now
        )
