from typing import Dict, Any, List, Optional, Tuple
from config.models import ConfigChange, ConfigSchema, ConfigScope, RuntimeMutability

class ConfigDiffEngine:
    """Calculates granular, typed diffs between configuration sets with automatic secret masking."""

    @staticmethod
    def compute_diff(
        old_values: Dict[str, Any],
        new_values: Dict[str, Any],
        schemas: Dict[str, ConfigSchema],
        scope: ConfigScope = ConfigScope.CLUSTER,
        entity_id: str = "CLUSTER"
    ) -> List[ConfigChange]:
        changes: List[ConfigChange] = []
        all_keys = set(old_values.keys()).union(set(new_values.keys()))

        for key in sorted(all_keys):
            old_val = old_values.get(key)
            new_val = new_values.get(key)
            schema = schemas.get(key)

            requires_restart = schema.requires_restart if schema else False
            is_secret = schema.is_secret if schema else (
                (isinstance(old_val, str) and old_val.startswith("secret://")) or
                (isinstance(new_val, str) and new_val.startswith("secret://"))
            )

            if key not in old_values:
                changes.append(ConfigChange(
                    key=key,
                    old_value=None,
                    new_value=new_val,
                    scope=scope,
                    entity_id=entity_id,
                    change_type="ADDED",
                    requires_restart=requires_restart,
                    is_secret=is_secret
                ))
            elif key not in new_values:
                changes.append(ConfigChange(
                    key=key,
                    old_value=old_val,
                    new_value=None,
                    scope=scope,
                    entity_id=entity_id,
                    change_type="REMOVED",
                    requires_restart=requires_restart,
                    is_secret=is_secret
                ))
            elif old_val != new_val:
                changes.append(ConfigChange(
                    key=key,
                    old_value=old_val,
                    new_value=new_val,
                    scope=scope,
                    entity_id=entity_id,
                    change_type="MODIFIED",
                    requires_restart=requires_restart,
                    is_secret=is_secret
                ))

        return changes

    @staticmethod
    def format_diff_report(changes: List[ConfigChange], mask_secrets: bool = True) -> str:
        """Renders an executive human-readable diff table."""
        if not changes:
            return "No configuration changes detected."

        lines = [
            "=" * 76,
            f"{'KEY':<35} | {'ACTION':<8} | {'OLD VALUE':<12} -> {'NEW VALUE':<12}",
            "-" * 76
        ]

        restart_keys = []
        for ch in changes:
            d = ch.to_dict(mask_secrets=mask_secrets)
            old_str = str(d["old_value"])[:12] if d["old_value"] is not None else "<none>"
            new_str = str(d["new_value"])[:12] if d["new_value"] is not None else "<none>"
            lines.append(f"{ch.key:<35} | {ch.change_type:<8} | {old_str:<12} -> {new_str:<12}")
            if ch.requires_restart:
                restart_keys.append(ch.key)

        lines.append("=" * 76)
        if restart_keys:
            lines.append(f"WARNING: The following keys require process/node restart: {restart_keys}")
        return "\n".join(lines)

    @staticmethod
    def assess_risk(changes: List[ConfigChange]) -> Tuple[str, List[str]]:
        """Assesses risk tier (LOW, MEDIUM, HIGH, CRITICAL) for human approval triggers."""
        critical_prefixes = ["security.", "coordination.", "approval."]
        high_keys = ["execution.safe_mode", "mesh.max_nodes"]

        reasons = []
        max_risk = "LOW"

        for ch in changes:
            if any(ch.key.startswith(p) for p in critical_prefixes):
                max_risk = "CRITICAL"
                reasons.append(f"Modifies critical security or consensus parameter: '{ch.key}'.")
            elif ch.key in high_keys and max_risk not in ["CRITICAL"]:
                max_risk = "HIGH"
                reasons.append(f"Modifies core safety or capacity threshold: '{ch.key}'.")
            elif ch.requires_restart and max_risk == "LOW":
                max_risk = "MEDIUM"
                reasons.append(f"Requires node restart: '{ch.key}'.")

        return max_risk, reasons
