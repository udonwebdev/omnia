import time
import logging
from typing import Dict, Any, Optional, Tuple, Callable

from secrets.models import SecretRecord, SecretVersionRecord, SecretStatus
from secrets.persistence import SecretPersistence
from secrets.providers import SecretProvider

logger = logging.getLogger("Omnia.Secrets.Rotation")

class RotationEngine:
    """Manages zero-downtime credential rotation with pre-activation validation and safe fallback."""

    def __init__(self, persistence: Optional[SecretPersistence] = None):
        self.persistence = persistence or SecretPersistence()

    def rotate_credential(
        self,
        secret: SecretRecord,
        provider: SecretProvider,
        new_plaintext: str,
        validation_probe: Optional[Callable[[str], bool]] = None,
        grace_period_sec: float = 0.0
    ) -> Tuple[bool, Optional[SecretVersionRecord], str]:
        """
        Executes zero-downtime rotation:
        Old ACTIVE -> New STAGED -> Validate -> New ACTIVE -> Old RETIRED.
        If validation fails, old version remains ACTIVE.
        """
        old_version_num = secret.version
        new_version_num = old_version_num + 1

        logger.info(f"Initiating credential rotation for '{secret.secret_id}' (v{old_version_num} -> v{new_version_num}).")

        # 1. Stage new version
        new_ver_record = provider.store_secret(secret.secret_id, new_plaintext, version=new_version_num)
        new_ver_record.status = SecretStatus.STAGED
        self.persistence.save_secret_version(new_ver_record)

        # 2. Validate new version
        if validation_probe:
            try:
                is_valid = validation_probe(new_plaintext)
            except Exception as e:
                is_valid = False
                logger.error(f"Rotation validation probe threw exception: {e}")

            if not is_valid:
                # Validation failed: abort rotation, reject staged version, keep old version active
                new_ver_record.status = SecretStatus.DISABLED
                self.persistence.save_secret_version(new_ver_record)
                msg = f"ROTATION_FAILED: Validation probe rejected new credential for '{secret.secret_id}'. Old v{old_version_num} remains ACTIVE."
                logger.warning(msg)
                return False, new_ver_record, msg

        # 3. Activate new version
        now = time.time()
        new_ver_record.status = SecretStatus.ACTIVE
        new_ver_record.activated_at = now
        self.persistence.save_secret_version(new_ver_record)

        # 4. Retire old version
        old_ver_record = self.persistence.get_secret_version(secret.secret_id, old_version_num)
        if old_ver_record:
            old_ver_record.status = SecretStatus.RETIRED
            old_ver_record.retired_at = now
            self.persistence.save_secret_version(old_ver_record)

        # 5. Update secret metadata
        secret.version = new_version_num
        secret.last_rotated_at = now
        secret.updated_at = now
        self.persistence.save_secret_metadata(secret)

        msg = f"ROTATION_SUCCESS: Secret '{secret.secret_id}' rotated to v{new_version_num}."
        logger.info(msg)
        return True, new_ver_record, msg
