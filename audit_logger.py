import time
import json
import hashlib
from pathlib import Path
from typing import Dict, Any

class AuditLogger:
    """Maintains a cryptographically linked JSONL audit log for all agent actions."""

    def __init__(self, log_path: str = "./omnia_audit.jsonl"):
        self.log_file = Path(log_path)
        self.last_hash = self._get_last_hash()

    def _get_last_hash(self) -> str:
        """Retrieves the cryptographic hash of the latest log entry or returns genesis hash."""
        if not self.log_file.exists() or self.log_file.stat().st_size == 0:
            return "0" * 64
        with open(self.log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            if not lines:
                return "0" * 64
            last_entry = json.loads(lines[-1].strip())
            return last_entry.get("hash", "0" * 64)

    def log_event(self, tool_name: str, params: Dict[str, Any], allowed: bool, outcome: str) -> None:
        """Appends a new hashed entry to the audit log."""
        timestamp = time.time()
        record_payload = {
            "timestamp": timestamp,
            "prev_hash": self.last_hash,
            "tool": tool_name,
            "params": params,
            "authorized": allowed,
            "outcome": outcome
        }
        
        # Calculate SHA-256 for chain integrity
        payload_serialized = json.dumps(record_payload, sort_keys=True)
        record_hash = hashlib.sha256(payload_serialized.encode("utf-8")).hexdigest()
        
        record_payload["hash"] = record_hash
        self.last_hash = record_hash

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record_payload) + "\n")

audit_logger = AuditLogger()
