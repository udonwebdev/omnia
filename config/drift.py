import uuid
import time
import logging
from typing import Dict, Any, List, Tuple, Optional
from config.models import DriftRecord, DriftType, ConfigScope, ConfigValue
from config.persistence import ConfigPersistence

logger = logging.getLogger("Omnia.Config.Drift")

class DriftDetector:
    """Detects, categorizes, and audits runtime configuration drift between cluster authority and nodes."""

    def __init__(self, persistence: Optional[ConfigPersistence] = None):
        self.persistence = persistence or ConfigPersistence()

    def inspect_node_drift(
        self,
        node_id: str,
        expected_version: int,
        expected_values: Dict[str, Any],
        actual_values: Dict[str, Any],
        actual_version: int,
        authorized_overrides: Optional[Dict[str, Any]] = None
    ) -> List[DriftRecord]:
        """Compares node runtime state against cluster authority, factoring in authorized overrides."""
        drifts: List[DriftRecord] = []
        overrides = authorized_overrides or {}

        # 1. Version Mismatch
        if actual_version != expected_version and actual_version != 0:
            drift = DriftRecord(
                drift_id=f"drift_ver_{node_id}_{uuid.uuid4().hex[:6]}",
                node_id=node_id,
                detected_at=time.time(),
                key="_version_",
                expected_version=expected_version,
                expected_value=expected_version,
                actual_value=actual_version,
                drift_type=DriftType.VERSION_MISMATCH
            )
            drifts.append(drift)
            self.persistence.record_drift(drift)

        # 2. Key-by-key inspection
        for key, exp_val in expected_values.items():
            # If an authorized override exists for this node, the effective expected value is the override
            target_val = overrides.get(key, exp_val)
            
            if key not in actual_values:
                drift = DriftRecord(
                    drift_id=f"drift_miss_{node_id}_{uuid.uuid4().hex[:6]}",
                    node_id=node_id,
                    detected_at=time.time(),
                    key=key,
                    expected_version=expected_version,
                    expected_value=target_val,
                    actual_value=None,
                    drift_type=DriftType.MISSING_KEY
                )
                drifts.append(drift)
                self.persistence.record_drift(drift)
            else:
                act_val = actual_values[key]
                if act_val != target_val:
                    # If it differs and there was no authorized override, it's either an unauthorized override or value mismatch
                    drift_type = DriftType.UNAUTHORIZED_OVERRIDE if key not in overrides else DriftType.VALUE_MISMATCH
                    drift = DriftRecord(
                        drift_id=f"drift_val_{node_id}_{uuid.uuid4().hex[:6]}",
                        node_id=node_id,
                        detected_at=time.time(),
                        key=key,
                        expected_version=expected_version,
                        expected_value=target_val,
                        actual_value=act_val,
                        drift_type=drift_type
                    )
                    drifts.append(drift)
                    self.persistence.record_drift(drift)

        return drifts

    def resolve_drift(self, drift_id: str, strategy: str = "FORCE_SYNC", notes: Optional[str] = None) -> bool:
        """Marks drift as resolved with specified strategy."""
        resolution_msg = f"Resolved via {strategy}. {notes or ''}".strip()
        return self.persistence.resolve_drift(drift_id, notes=resolution_msg)
