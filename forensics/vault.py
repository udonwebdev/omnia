"""
forensics/vault.py
Cryptographic evidence preservation and tamper-evident storage vault for OMNIA Module 48:
Autonomous Digital Forensics, Evidence Preservation & Incident Investigation Intelligence.
"""

import hashlib
import os
import json
import logging
from typing import Tuple, Dict, Any

logger = logging.getLogger("omnia.forensics.vault")


class EvidenceVault:
    """
    Manages safe local or storage-referenced evidence preservation.
    Ensures artifacts are cryptographically hashed (SHA-256), non-executable,
    and verified against expected digests.
    """

    def __init__(self, storage_dir: str = "artifacts/forensics_vault"):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)

    @staticmethod
    def compute_sha256(data: bytes) -> str:
        """Compute standard SHA-256 hexadecimal hash over raw payload."""
        return hashlib.sha256(data).hexdigest()

    def store_artifact_bytes(
        self,
        artifact_id: str,
        data: bytes,
        extension: str = ".dat"
    ) -> Tuple[str, str, int]:
        """
        Store evidence bytes safely in the evidence vault.
        Returns: (sha256_hash, storage_uri, size_bytes)
        """
        sha256_hash = self.compute_sha256(data)
        size_bytes = len(data)
        safe_filename = f"{artifact_id}_{sha256_hash[:12]}{extension}"
        storage_path = os.path.join(self.storage_dir, safe_filename)

        with open(storage_path, "wb") as f:
            f.write(data)

        # Make file read-only on the filesystem if possible
        try:
            os.chmod(storage_path, 0o444)
        except Exception as e:
            logger.debug(f"Could not set read-only file permissions on {storage_path}: {e}")

        logger.info(f"Preserved forensic evidence artifact {artifact_id}: {size_bytes} bytes, SHA256={sha256_hash}")
        return sha256_hash, storage_path, size_bytes

    def read_artifact_bytes(self, storage_uri: str) -> bytes:
        """Read artifact content safely for non-executable inspection/parsing."""
        if not os.path.exists(storage_uri):
            raise FileNotFoundError(f"Evidence artifact at {storage_uri} does not exist.")
        with open(storage_uri, "rb") as f:
            return f.read()

    def verify_integrity(self, storage_uri: str, expected_sha256: str) -> Tuple[bool, str]:
        """
        Verifies that the artifact on disk matches the registered cryptographic digest.
        Returns (is_valid, current_sha256).
        """
        try:
            data = self.read_artifact_bytes(storage_uri)
            current_sha256 = self.compute_sha256(data)
            is_valid = (current_sha256.lower() == expected_sha256.lower())
            return is_valid, current_sha256
        except Exception as e:
            logger.error(f"Failed integrity verification for {storage_uri}: {e}")
            return False, f"ERROR: {e}"
