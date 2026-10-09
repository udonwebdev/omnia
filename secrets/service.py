import time
import logging
from typing import Dict, Any, List, Optional, Tuple, Callable

from secrets.models import (
    SecretType,
    SecretStatus,
    TrustLevel,
    ProviderHealth,
    SecretRecord,
    SecretVersionRecord,
    SecretLease,
    SecretAccessRequest,
    SecretHandle,
    SecretReference,
    SecretTelemetry
)
from secrets.encryption import encryption_engine, EncryptionEngine
from secrets.persistence import SecretPersistence
from secrets.providers import (
    SecretProvider,
    LocalEncryptedStoreProvider,
    EnvironmentSecretProvider,
    MemoryVaultProvider,
    ProviderManager,
    SecretUnavailableError
)
from secrets.access import SecretAccessAuthorizer, AccessDeniedError
from secrets.leases import LeaseManager
from secrets.rotation import RotationEngine
from secrets.revocation import RevocationEngine
from secrets.redaction import redaction_engine, RedactionEngine
from secrets.audit import SecretAuditLogger
from secrets.telemetry import SecretTelemetryCollector

logger = logging.getLogger("Omnia.Secrets.Service")

class SecretControlPlaneService:
    """Authoritative credential lifecycle management and secure access control plane."""

    def __init__(
        self,
        persistence: Optional[SecretPersistence] = None,
        node_id: str = "local_node"
    ):
        self.node_id = node_id
        self.persistence = persistence or SecretPersistence()
        self.enc_engine = encryption_engine

        # Subsystems
        self.provider_manager = ProviderManager()
        self.local_provider = LocalEncryptedStoreProvider(self.persistence, self.enc_engine)
        self.env_provider = EnvironmentSecretProvider()
        self.mem_provider = MemoryVaultProvider()

        self.provider_manager.register_provider(self.local_provider, is_primary=True)
        self.provider_manager.register_provider(self.env_provider)
        self.provider_manager.register_provider(self.mem_provider)

        self.authorizer = SecretAccessAuthorizer()
        self.authorizer.set_node_trust(self.node_id, TrustLevel.TRUSTED)
        self.lease_mgr = LeaseManager(self.persistence)
        self.rotation_engine = RotationEngine(self.persistence)
        self.revocation_engine = RevocationEngine(self.persistence, self.lease_mgr)
        self.redaction_engine = redaction_engine
        self.audit_logger = SecretAuditLogger(self.persistence)
        self.telemetry_collector = SecretTelemetryCollector(self.persistence)

    def _emit_event(self, event_type: str, payload: Dict[str, Any]):
        """Publishes typed metadata events to Event Fabric with zero plaintext secrets."""
        try:
            import asyncio
            from events.models import Event, EventEnvelope
            from events.fabric import event_fabric
            evt = Event(
                envelope=EventEnvelope(
                    event_type=event_type,
                    source=f"secrets_control_plane_{self.node_id}"
                ),
                payload=payload
            )
            async def _pub():
                await event_fabric.publish(evt)
                await event_fabric._dispatch_lanes()

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(_pub())
                else:
                    loop.run_until_complete(_pub())
            except RuntimeError:
                asyncio.run(_pub())
        except Exception as e:
            logger.debug(f"Event emission for '{event_type}' bypassed: {e}")

    # --- Secret Registration & Creation ---
    def register_secret(
        self,
        secret_id: str,
        name: str,
        secret_type: SecretType,
        plaintext: str,
        scope: str = "CLUSTER",
        provider_name: str = "local_encrypted",
        expires_at: Optional[float] = None,
        access_policy: Optional[Dict[str, Any]] = None,
        rotation_policy: Optional[Dict[str, Any]] = None
    ) -> SecretRecord:
        """Registers and encrypts a new secret into the authoritative provider."""
        provider = self.provider_manager.get_provider(provider_name)
        if not provider:
            raise ValueError(f"Unknown secret provider: '{provider_name}'.")

        now = time.time()
        # Register in redaction engine to prevent casual logging or prompt exposure
        self.redaction_engine.register_secret_value(plaintext)

        # Store encrypted version
        ver_record = provider.store_secret(secret_id, plaintext, version=1)

        meta = SecretRecord(
            secret_id=secret_id,
            name=name,
            secret_type=secret_type,
            provider=provider_name,
            scope=scope,
            version=1,
            status=SecretStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
            last_rotated_at=now,
            last_used_at=None,
            rotation_policy=rotation_policy or {},
            access_policy=access_policy or {},
            integrity_hash=ver_record.fingerprint
        )
        self.persistence.save_secret_metadata(meta)

        self.audit_logger.log_event(
            secret_id=secret_id,
            version=1,
            requester="admin",
            action="CREATE",
            result="SUCCESS",
            scope=scope,
            node_id=self.node_id,
            details={"type": secret_type.value, "provider": provider_name}
        )

        self._emit_event("secret.created", {
            "secret_id": secret_id,
            "version": 1,
            "secret_type": secret_type.value,
            "scope": scope,
            "provider": provider_name
        })

        return meta

    # --- Contextual Secret Acquisition ---
    def acquire_secret(
        self,
        uri_or_id: str,
        requester: str,
        purpose: str,
        capability: str,
        scope: str = "CLUSTER",
        node_id: Optional[str] = None,
        task_id: Optional[str] = None,
        mission_id: Optional[str] = None,
        ttl_seconds: float = 300.0
    ) -> SecretHandle:
        """
        Contextual credential acquisition:
        Validates identity, purpose binding, capability boundaries, node trust, and lease.
        Returns scoped SecretHandle.
        """
        target_node = node_id or self.node_id

        # Parse reference URI if provided
        version_override = None
        preferred_provider = None
        if uri_or_id.startswith("secret://"):
            ref = SecretReference.parse(uri_or_id)
            secret_id = ref.path
            version_override = ref.version
            preferred_provider = ref.provider
        else:
            secret_id = uri_or_id

        meta = self.persistence.get_secret_metadata(secret_id)
        if not meta:
            self.telemetry_collector.record_access_denied()
            self._emit_event("secret.access_denied", {
                "secret_id": secret_id,
                "requester": requester,
                "purpose": purpose,
                "reason": "SECRET_NOT_FOUND"
            })
            raise SecretUnavailableError(f"Secret '{secret_id}' not found in metadata catalog.")

        req = SecretAccessRequest(
            requester_identity=requester,
            secret_id=secret_id,
            purpose=purpose,
            capability=capability,
            scope=scope,
            node_id=target_node,
            task_id=task_id,
            mission_id=mission_id,
            version=version_override,
            ttl_seconds=ttl_seconds
        )

        # Authorize access request
        authorized, reason = self.authorizer.authorize_request(req, meta)
        if not authorized:
            self.telemetry_collector.record_access_denied()
            self.audit_logger.log_event(
                secret_id=secret_id,
                version=meta.version,
                requester=requester,
                action="ACQUIRE",
                result="DENIED",
                purpose=purpose,
                capability=capability,
                scope=scope,
                node_id=target_node,
                details={"reason": reason}
            )
            self._emit_event("secret.access_denied", {
                "secret_id": secret_id,
                "requester": requester,
                "purpose": purpose,
                "reason": reason or "DENIED"
            })
            raise AccessDeniedError(f"Access denied to '{secret_id}': {reason}")

        # Resolve plaintext from secure provider
        plaintext, ver, prov_name = self.provider_manager.resolve_secret(
            secret_id=secret_id,
            preferred_provider=preferred_provider or meta.provider,
            version=version_override or meta.version
        )

        # Issue lease
        lease = self.lease_mgr.issue_lease(
            request=req,
            secret_id=secret_id,
            version=ver,
            ttl_seconds=ttl_seconds
        )

        # Update last used timestamp
        meta.last_used_at = time.time()
        self.persistence.save_secret_metadata(meta)

        self.telemetry_collector.record_access_granted()
        self.audit_logger.log_event(
            secret_id=secret_id,
            version=ver,
            requester=requester,
            action="ACQUIRE",
            result="GRANTED",
            purpose=purpose,
            capability=capability,
            scope=scope,
            node_id=target_node,
            details={"lease_id": lease.lease_id, "provider": prov_name}
        )

        self._emit_event("secret.access_granted", {
            "lease_id": lease.lease_id,
            "secret_id": secret_id,
            "version": ver,
            "requester": requester,
            "expires_at": lease.expires_at
        })

        return SecretHandle(
            secret_id=secret_id,
            version=ver,
            lease=lease,
            plaintext_value=plaintext,
            release_cb=self.release_secret,
            is_valid_cb=self.lease_mgr.validate_lease
        )

    def release_secret(self, lease_id: str) -> bool:
        """Releases and revokes an active secret lease."""
        return self.lease_mgr.revoke_lease(lease_id)

    # --- Zero-Downtime Rotation ---
    def rotate_secret(
        self,
        secret_id: str,
        new_plaintext: str,
        validation_probe: Optional[Callable[[str], bool]] = None
    ) -> Tuple[bool, Optional[SecretVersionRecord], str]:
        meta = self.persistence.get_secret_metadata(secret_id)
        if not meta:
            return False, None, f"Secret '{secret_id}' not found."

        provider = self.provider_manager.get_provider(meta.provider)
        if not provider:
            return False, None, f"Provider '{meta.provider}' unavailable for secret '{secret_id}'."

        self.redaction_engine.register_secret_value(new_plaintext)

        self._emit_event("secret.rotation_started", {
            "secret_id": secret_id,
            "from_version": meta.version,
            "to_version": meta.version + 1,
            "strategy": "ZERO_DOWNTIME_STAGED"
        })

        ok, new_ver, msg = self.rotation_engine.rotate_credential(
            secret=meta,
            provider=provider,
            new_plaintext=new_plaintext,
            validation_probe=validation_probe
        )

        self.telemetry_collector.record_rotation_result(ok)

        if ok and new_ver:
            self.audit_logger.log_event(
                secret_id=secret_id,
                version=new_ver.version,
                requester="rotation_engine",
                action="ROTATE",
                result="SUCCESS",
                scope=meta.scope,
                node_id=self.node_id
            )
            self._emit_event("secret.rotation_completed", {
                "secret_id": secret_id,
                "active_version": new_ver.version
            })
        else:
            self.audit_logger.log_event(
                secret_id=secret_id,
                version=meta.version,
                requester="rotation_engine",
                action="ROTATE",
                result="FAILED",
                scope=meta.scope,
                node_id=self.node_id,
                details={"reason": msg}
            )
            self._emit_event("secret.rotation_failed", {
                "secret_id": secret_id,
                "failed_version": meta.version + 1,
                "reason": msg
            })

        return ok, new_ver, msg

    # --- Revocation & Compromise Response ---
    def revoke_secret(self, secret_id: str, reason: str = "Operator revoked") -> Tuple[bool, str]:
        meta = self.persistence.get_secret_metadata(secret_id)
        ver = meta.version if meta else 0

        ok, msg = self.revocation_engine.revoke_credential(secret_id, reason=reason)
        if ok:
            self.audit_logger.log_event(
                secret_id=secret_id,
                version=ver,
                requester="operator",
                action="REVOKE",
                result="SUCCESS",
                node_id=self.node_id,
                details={"reason": reason}
            )
            self._emit_event("secret.revoked", {
                "secret_id": secret_id,
                "version": ver,
                "reason": reason
            })
        return ok, msg

    def mark_compromised(self, secret_id: str, incident_id: str, details: str = "") -> Tuple[bool, str]:
        meta = self.persistence.get_secret_metadata(secret_id)
        ver = meta.version if meta else 0

        ok, msg = self.revocation_engine.mark_compromised(secret_id, incident_id=incident_id, details=details)
        if ok:
            self.audit_logger.log_event(
                secret_id=secret_id,
                version=ver,
                requester="security_incident_responder",
                action="COMPROMISE",
                result="SUCCESS",
                node_id=self.node_id,
                details={"incident_id": incident_id, "details": details}
            )
            self._emit_event("secret.compromised", {
                "secret_id": secret_id,
                "version": ver,
                "incident_id": incident_id,
                "action_taken": "IMMEDIATE_QUARANTINE_AND_REVOCATION"
            })
        return ok, msg

    # --- Querying & Telemetry ---
    def get_secret_metadata(self, secret_id: str) -> Optional[SecretRecord]:
        return self.persistence.get_secret_metadata(secret_id)

    def list_secrets(self, scope: Optional[str] = None) -> List[SecretRecord]:
        return self.persistence.list_secrets_metadata(scope=scope)

    def get_telemetry(self) -> SecretTelemetry:
        return self.telemetry_collector.get_telemetry()
