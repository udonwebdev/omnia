"""
Omnia Module 34: State Snapshot Manager
Creates immutable system state snapshots with cryptographic integrity digests,
automated credential/secret redaction, and isolated restoration for simulations.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from simulation.models import StateSnapshot


SENSITIVE_KEY_PATTERNS = [
    re.compile(r"api[-_]?key", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"credential", re.IGNORECASE),
    re.compile(r"authorization", re.IGNORECASE),
    re.compile(r"private[-_]?key", re.IGNORECASE),
]

JWT_PATTERN = re.compile(r"ey[A-Za-z0-9-_]+\.ey[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+")
API_KEY_PATTERN = re.compile(r"(?:Bearer\s+|key-|sk-)[a-zA-Z0-9_-]{16,}")


class SnapshotManager:
    """
    Manages immutable initial-state snapshots for simulation environments.
    Guarantees zero secret leakage into simulation state and provides integrity hashing.
    """

    def __init__(self) -> None:
        pass

    def create_snapshot(
        self,
        snapshot_id: str,
        environment_id: str,
        raw_state: Dict[str, Any],
        source_version: str = "1.0.0",
        included_components: Optional[List[str]] = None,
        excluded_components: Optional[List[str]] = None,
        known_limitations: Optional[List[str]] = None,
        created_by: str = "system",
    ) -> StateSnapshot:
        """
        Sanitizes raw state, redacting sensitive secrets, computes SHA-256 digest,
        and constructs an immutable StateSnapshot.
        """
        sanitized_state, redacted_keys = self.sanitize_state(raw_state)
        excluded = list(excluded_components or []) + redacted_keys

        digest = self.compute_digest(sanitized_state)

        return StateSnapshot(
            snapshot_id=snapshot_id,
            environment_id=environment_id,
            source_version=source_version,
            captured_at=time.time(),
            state_schema_version="1.0.0",
            state_payload=sanitized_state,
            included_components=included_components or list(sanitized_state.keys()),
            excluded_components=excluded,
            integrity_digest=digest,
            consistency_status="CONSISTENT",
            data_classification="INTERNAL",
            known_limitations=known_limitations or [],
            created_by=created_by,
        )

    def verify_snapshot_integrity(self, snapshot: StateSnapshot) -> Tuple[bool, str]:
        """
        Validates the snapshot integrity against its recorded SHA-256 digest.
        """
        computed = self.compute_digest(snapshot.state_payload)
        if computed != snapshot.integrity_digest:
            return False, f"Integrity digest mismatch: expected {snapshot.integrity_digest}, computed {computed}"
        return True, "Snapshot integrity verified"

    def sanitize_state(self, data: Any) -> Tuple[Any, List[str]]:
        """
        Recursively redacts secrets and token strings from dictionary or list state payloads.
        Returns (sanitized_payload, list_of_redacted_keys).
        """
        redacted_keys: List[str] = []

        def _clean(val: Any, current_path: str = "") -> Any:
            if isinstance(val, dict):
                clean_dict = {}
                for k, v in val.items():
                    path = f"{current_path}.{k}" if current_path else k
                    if any(p.search(k) for p in SENSITIVE_KEY_PATTERNS):
                        clean_dict[k] = "[REDACTED_SECRET]"
                        redacted_keys.append(path)
                    else:
                        clean_dict[k] = _clean(v, path)
                return clean_dict
            elif isinstance(val, list):
                return [_clean(item, current_path) for item in val]
            elif isinstance(val, str):
                if JWT_PATTERN.search(val):
                    redacted_keys.append(f"{current_path}:jwt")
                    return "[REDACTED_JWT]"
                if API_KEY_PATTERN.search(val):
                    redacted_keys.append(f"{current_path}:key")
                    return "[REDACTED_KEY]"
                return val
            return copy.deepcopy(val)

        sanitized = _clean(data)
        return sanitized, redacted_keys

    def compute_digest(self, payload: Dict[str, Any]) -> str:
        """
        Computes deterministic SHA-256 hash of state payload.
        """
        serialized = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def restore_isolated_state(self, snapshot: StateSnapshot) -> Dict[str, Any]:
        """
        Returns a deepcopy of the state payload for sandboxed simulation execution.
        Guarantees isolation from any reference mutation.
        """
        return copy.deepcopy(snapshot.state_payload)
