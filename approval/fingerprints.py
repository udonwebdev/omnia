import hashlib
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("Omnia.Approval.Fingerprints")

class FingerprintGenerator:
    """Computes and validates deterministic fingerprints for actions, plans, and contexts.
    
    Invariant: An approval token is strictly bound to its action parameters, target resources,
    and plan context. Any mutation in the parameters or context produces a hash mismatch
    and rejects execution.
    """

    @staticmethod
    def _normalize_dict(d: Any) -> Any:
        if isinstance(d, dict):
            return {k: FingerprintGenerator._normalize_dict(v) for k, v in sorted(d.items())}
        elif isinstance(d, (list, tuple, set)):
            return [FingerprintGenerator._normalize_dict(x) for x in d]
        elif isinstance(d, (int, float, str, bool)) or d is None:
            return d
        else:
            return str(d)

    @classmethod
    def compute_action_fingerprint(
        cls,
        action: str,
        params: Dict[str, Any],
        target_resource: Optional[str] = None,
        target_device: Optional[str] = None,
        task_id: Optional[str] = None,
        task_node_id: Optional[str] = None,
        plan_version: int = 1
    ) -> str:
        """Generates deterministic SHA-256 hash for an action invocation."""
        normalized_params = cls._normalize_dict(params or {})
        canonical_payload = {
            "action": (action or "").strip(),
            "params": normalized_params,
            "target_resource": (target_resource or "").strip(),
            "target_device": (target_device or "").strip(),
            "task_id": (task_id or "").strip(),
            "task_node_id": (task_node_id or "").strip(),
            "plan_version": plan_version
        }
        encoded = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def verify_action_fingerprint(
        cls,
        expected_fingerprint: str,
        action: str,
        params: Dict[str, Any],
        target_resource: Optional[str] = None,
        target_device: Optional[str] = None,
        task_id: Optional[str] = None,
        task_node_id: Optional[str] = None,
        plan_version: int = 1
    ) -> bool:
        """Verifies if the current action context matches the approved fingerprint."""
        if not expected_fingerprint:
            return False
        current_fp = cls.compute_action_fingerprint(
            action=action,
            params=params,
            target_resource=target_resource,
            target_device=target_device,
            task_id=task_id,
            task_node_id=task_node_id,
            plan_version=plan_version
        )
        return current_fp.lower() == expected_fingerprint.lower()

fingerprint_generator = FingerprintGenerator()
