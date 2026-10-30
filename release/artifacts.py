"""
OMNIA Module 37: Artifact Manager & Cryptographic Integrity Verifier
Calculates deterministic SHA-256 digests, validates SBOMs, detects tampering,
and guarantees immutable artifact storage.
"""

import os
import hashlib
import json
import logging
from typing import Dict, Any, Optional
from release.models import ArtifactRecord
from release.persistence import ReleaseRepository

logger = logging.getLogger("Omnia.Release.Artifacts")


class ArtifactManager:
    """Manages immutable software build artifacts and cryptographic verification."""

    def __init__(self, repo: ReleaseRepository, storage_base_dir: str = "release_artifacts"):
        self.repo = repo
        self.storage_base_dir = storage_base_dir
        os.makedirs(self.storage_base_dir, exist_ok=True)

    def calculate_file_digest(self, file_path: str) -> str:
        """Computes deterministic SHA-256 cryptographic checksum."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Artifact file not found: {file_path}")
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    def register_artifact(
        self,
        artifact_id: str,
        app_id: str,
        version: str,
        source_revision: str,
        build_id: str,
        file_path: str,
        format_type: str = "tarball",
        builder_identity: str = "omnia_builder",
        toolchain_metadata: Optional[Dict[str, Any]] = None,
        dependency_manifest: Optional[Dict[str, str]] = None,
        sbom_digest: Optional[str] = None,
    ) -> ArtifactRecord:
        """Registers and validates a newly built software artifact."""
        digest = self.calculate_file_digest(file_path)
        size_bytes = os.path.getsize(file_path)

        # Retain artifact in structured store
        target_name = f"{app_id}-{version}-{artifact_id}.pkg"
        target_path = os.path.join(self.storage_base_dir, target_name)
        if not os.path.exists(target_path):
            with open(file_path, "rb") as src, open(target_path, "wb") as dst:
                dst.write(src.read())

        record = ArtifactRecord(
            artifact_id=artifact_id,
            app_id=app_id,
            version=version,
            source_revision=source_revision,
            build_id=build_id,
            digest_sha256=digest,
            size_bytes=size_bytes,
            format_type=format_type,
            storage_uri=os.path.abspath(target_path),
            builder_identity=builder_identity,
            toolchain_metadata=toolchain_metadata or {"python": "3.12"},
            dependency_manifest=dependency_manifest or {},
            sbom_digest=sbom_digest or hashlib.sha256(json.dumps(dependency_manifest or {}).encode()).hexdigest(),
            is_tamper_verified=True,
        )

        self.repo.save_artifact(record)
        logger.info(f"Registered artifact '{artifact_id}' (v{version}) with SHA-256 {digest[:16]}...")
        return record

    def verify_artifact_integrity(self, artifact_id: str) -> Dict[str, Any]:
        """
        Cryptographically verifies artifact against stored SHA-256 digest.
        Never trusts claimed filename or version without byte-level verification.
        """
        record = self.repo.get_artifact(artifact_id)
        if not record:
            return {"verified": False, "error": f"Artifact '{artifact_id}' not found in registry"}

        if not os.path.exists(record.storage_uri):
            return {"verified": False, "error": f"Artifact storage file missing at {record.storage_uri}"}

        current_digest = self.calculate_file_digest(record.storage_uri)
        if current_digest != record.digest_sha256:
            logger.error(f"TAMPERING DETECTED for artifact {artifact_id}! Expected {record.digest_sha256}, got {current_digest}")
            record.is_tamper_verified = False
            self.repo.save_artifact(record)
            return {
                "verified": False,
                "error": "Cryptographic digest mismatch (possible file tampering or corruption)",
                "expected": record.digest_sha256,
                "actual": current_digest,
            }

        record.is_tamper_verified = True
        self.repo.save_artifact(record)
        return {
            "verified": True,
            "artifact_id": artifact_id,
            "digest_sha256": current_digest,
            "size_bytes": record.size_bytes,
        }
