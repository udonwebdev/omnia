import time
import logging
from typing import Dict, Any, List, Optional, Tuple

from config.models import (
    ConfigSchema,
    ConfigType,
    ConfigScope,
    RuntimeMutability,
    ConfigValue,
    ConfigVersion,
    ConfigVersionStatus,
    ConfigChange,
    ConfigRollout,
    RolloutStrategy,
    RolloutStatus,
    DriftRecord,
    DriftType,
    ConfigTelemetry
)
from config.defaults import DEFAULT_CONFIG_SCHEMAS, get_default_schemas_dict, get_default_values_dict
from config.persistence import ConfigPersistence
from config.validation import ConfigValidator
from config.diff import ConfigDiffEngine
from config.rollout import RolloutOrchestrator
from config.rollback import RollbackEngine
from config.drift import DriftDetector

logger = logging.getLogger("Omnia.Config.ControlPlane")

class ConfigControlPlaneService:
    """Authoritative distributed configuration and runtime control plane service."""

    def __init__(
        self,
        persistence: Optional[ConfigPersistence] = None,
        node_id: str = "local_node"
    ):
        self.persistence = persistence or ConfigPersistence()
        self.node_id = node_id
        self.validator = ConfigValidator()
        self.diff_engine = ConfigDiffEngine()
        self.rollout_orchestrator = RolloutOrchestrator(self.persistence)
        self.rollback_engine = RollbackEngine(self.persistence)
        self.drift_detector = DriftDetector(self.persistence)

        self._schemas: Dict[str, ConfigSchema] = {}
        self._init_schemas()

    def _init_schemas(self):
        """Initializes default domain schemas into memory and database."""
        for s in DEFAULT_CONFIG_SCHEMAS:
            self._schemas[s.key] = s
            self.persistence.save_schema(s)

        # Load any additional saved schemas from DB
        db_schemas = self.persistence.list_schemas()
        for ds in db_schemas:
            self._schemas[ds.key] = ds

        # Ensure at least version 1 exists with default values if no versions exist
        if self.persistence.get_latest_version_num() == 0:
            default_vals = {s.key: s.default_value for s in self._schemas.values()}
            v1_hash = ConfigVersion.compute_hash(default_vals, ConfigScope.CLUSTER.value, "CLUSTER", None)
            v1 = ConfigVersion(
                version=1,
                parent_version=None,
                scope=ConfigScope.CLUSTER,
                target_entity="CLUSTER",
                content_hash=v1_hash,
                values=default_vals,
                author="system_bootstrap",
                justification="Initial cluster baseline configuration",
                status=ConfigVersionStatus.ACTIVE,
                created_at=time.time(),
                activated_at=time.time()
            )
            self.persistence.save_version(v1)
            for k, val in default_vals.items():
                cv = ConfigValue(
                    key=k,
                    scope=ConfigScope.CLUSTER,
                    entity_id="CLUSTER",
                    value=val,
                    version=1,
                    is_secret_ref=self._schemas[k].is_secret if k in self._schemas else False
                )
                self.persistence.save_value(cv)
            logger.info("Initialized baseline configuration Version 1.")

    def _emit_event(self, event_type: str, payload: Dict[str, Any]):
        """Emits event to event fabric if available."""
        try:
            from events.models import Event
            from events.fabric import event_fabric
            evt = Event(
                type=event_type,
                source=f"config_control_plane_{self.node_id}",
                payload=payload
            )
            event_fabric.publish(evt)
        except Exception as e:
            logger.debug(f"Event emission for '{event_type}' bypassed: {e}")

    # --- Schema Management ---
    def register_schema(self, schema: ConfigSchema) -> bool:
        self._schemas[schema.key] = schema
        self.persistence.save_schema(schema)
        return True

    def get_schema(self, key: str) -> Optional[ConfigSchema]:
        return self._schemas.get(key)

    def list_schemas(self, domain: Optional[str] = None) -> List[ConfigSchema]:
        if domain:
            return [s for s in self._schemas.values() if s.domain == domain]
        return list(self._schemas.values())

    # --- Effective Value Resolution ---
    def resolve_effective_value(
        self,
        key: str,
        node_id: Optional[str] = None,
        device_id: Optional[str] = None
    ) -> Any:
        """Resolves configuration value using strict precedence hierarchy: DEVICE > NODE > CLUSTER > GLOBAL > SCHEMA_DEFAULT."""
        schema = self.get_schema(key)
        
        # 1. Device Override
        if device_id:
            val_device = self.persistence.get_value(key, ConfigScope.DEVICE, device_id)
            if val_device is not None:
                return val_device.value

        # 2. Node Override
        if node_id:
            val_node = self.persistence.get_value(key, ConfigScope.NODE, node_id)
            if val_node is not None:
                return val_node.value

        # 3. Cluster Active Value
        val_cluster = self.persistence.get_value(key, ConfigScope.CLUSTER, "CLUSTER")
        if val_cluster is not None:
            return val_cluster.value

        # 4. Global Value
        val_global = self.persistence.get_value(key, ConfigScope.GLOBAL, "GLOBAL")
        if val_global is not None:
            return val_global.value

        # 5. Schema Default
        if schema:
            return schema.default_value

        return None

    def get_effective_configuration(
        self,
        node_id: Optional[str] = None,
        device_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Returns the full resolved effective configuration dictionary for a given node/device."""
        resolved = {}
        for key in self._schemas.keys():
            resolved[key] = self.resolve_effective_value(key, node_id=node_id, device_id=device_id)
        return resolved

    # --- Versioning & Creation ---
    def propose_version(
        self,
        values: Dict[str, Any],
        author: str,
        scope: ConfigScope = ConfigScope.CLUSTER,
        target_entity: str = "CLUSTER",
        justification: Optional[str] = None,
        parent_version: Optional[int] = None
    ) -> Tuple[bool, Optional[ConfigVersion], List[str]]:
        """Proposes and stages a new immutable configuration snapshot with optimistic concurrency checks."""
        # Check optimistic concurrency
        active_version = self.persistence.get_active_version(scope=scope, target_entity=target_entity)
        expected_parent = active_version.version if active_version else 0

        if parent_version is not None and parent_version != expected_parent:
            err = f"CONCURRENCY_CONFLICT: Specified parent_version {parent_version} does not match active version {expected_parent}."
            logger.warning(err)
            return False, None, [err]

        # Merge proposed changes over current active configuration
        base_values = dict(active_version.values) if active_version else {s.key: s.default_value for s in self._schemas.values()}
        merged_values = dict(base_values)
        merged_values.update(values)

        # Validate proposed configuration
        valid, errors = self.validator.validate_configuration(merged_values, self._schemas)
        if not valid:
            logger.error(f"Configuration proposal rejected due to validation errors: {errors}")
            return False, None, errors

        # Compute diff and assess risk
        changes = self.diff_engine.compute_diff(base_values, merged_values, self._schemas, scope=scope, entity_id=target_entity)
        risk_level, risk_reasons = self.diff_engine.assess_risk(changes)

        next_version_num = self.persistence.get_latest_version_num() + 1
        content_hash = ConfigVersion.compute_hash(merged_values, scope.value, target_entity, expected_parent)

        new_version = ConfigVersion(
            version=next_version_num,
            parent_version=expected_parent,
            scope=scope,
            target_entity=target_entity,
            content_hash=content_hash,
            values=merged_values,
            author=author,
            justification=justification,
            status=ConfigVersionStatus.STAGED,
            created_at=time.time()
        )

        self.persistence.save_version(new_version)
        logger.info(f"Staged configuration Version {new_version.version} (Hash: {content_hash[:8]}). Risk: {risk_level}")

        self._emit_event("config.created", {
            "version": new_version.version,
            "scope": scope.value,
            "content_hash": content_hash,
            "author": author
        })
        self._emit_event("config.validated", {
            "version": new_version.version,
            "key_count": len(merged_values),
            "status": "VALID"
        })
        self._emit_event("config.staged", {
            "version": new_version.version,
            "scope": scope.value
        })

        if risk_level in ["HIGH", "CRITICAL"]:
            self._emit_event("config.approval_required", {
                "version": new_version.version,
                "risk_level": risk_level,
                "changes": [c.to_dict() for c in changes]
            })

        return True, new_version, []

    # --- Activation & Rollout ---
    def activate_version(
        self,
        version_num: int,
        target_nodes: List[str],
        strategy: RolloutStrategy = RolloutStrategy.ALL_AT_ONCE,
        batch_size: int = 1,
        failure_threshold_pct: float = 0.0
    ) -> Tuple[bool, Optional[ConfigRollout], str]:
        """Activates a staged version and orchestrates rollout across cluster nodes."""
        version = self.persistence.get_version(version_num)
        if not version:
            return False, None, f"Version {version_num} not found."

        # Mark previously active version as SUPERSEDED
        prev_active = self.persistence.get_active_version(scope=version.scope, target_entity=version.target_entity)
        if prev_active and prev_active.version != version_num:
            self.persistence.set_version_status(prev_active.version, ConfigVersionStatus.SUPERSEDED)

        # Mark this version as ACTIVE
        self.persistence.set_version_status(version_num, ConfigVersionStatus.ACTIVE, activated_at=time.time())

        # Update persisted config_values table
        for k, v in version.values.items():
            schema = self.get_schema(k)
            cv = ConfigValue(
                key=k,
                scope=version.scope,
                entity_id=version.target_entity,
                value=v,
                version=version_num,
                is_secret_ref=schema.is_secret if schema else False
            )
            self.persistence.save_value(cv)

        # Create Rollout
        rollout = self.rollout_orchestrator.create_rollout(
            version=version_num,
            target_nodes=target_nodes,
            strategy=strategy,
            batch_size=batch_size,
            failure_threshold_pct=failure_threshold_pct
        )

        self._emit_event("config.rollout_started", {
            "rollout_id": rollout.rollout_id,
            "version": version_num,
            "strategy": strategy.value,
            "target_nodes": target_nodes
        })

        # Apply rollout function
        def _apply_to_node(node_id: str, ver_num: int) -> Tuple[bool, Optional[str]]:
            # Node activation simulation or hook
            self._emit_event("config.node_activated", {
                "node_id": node_id,
                "version": ver_num,
                "applied_keys": len(version.values)
            })
            return True, None

        # Execute batches
        batches = self.rollout_orchestrator.compute_batches(rollout)
        for _ in range(len(batches)):
            rollout = self.rollout_orchestrator.advance_rollout(rollout.rollout_id, _apply_to_node)
            if rollout.status in [RolloutStatus.FAILED, RolloutStatus.PAUSED]:
                break

        if rollout.status == RolloutStatus.COMPLETED:
            self._emit_event("config.rollout_completed", {
                "rollout_id": rollout.rollout_id,
                "version": version_num,
                "strategy": strategy.value
            })
            return True, rollout, "Rollout completed successfully."
        else:
            return False, rollout, rollout.failure_reason or f"Rollout status: {rollout.status.value}"

    # --- Rollback ---
    def rollback_version(
        self,
        current_version_num: int,
        target_version_num: Optional[int],
        reason: str,
        target_nodes: List[str]
    ) -> Tuple[bool, Optional[ConfigVersion], str]:
        """Rolls back to a prior version."""
        self._emit_event("config.rollback_started", {
            "rollout_id": f"rollback_{current_version_num}",
            "from_version": current_version_num,
            "to_version": target_version_num or 0,
            "reason": reason
        })

        def _apply_to_node(node_id: str, ver_num: int) -> Tuple[bool, Optional[str]]:
            self._emit_event("config.node_activated", {
                "node_id": node_id,
                "version": ver_num,
                "applied_keys": 0
            })
            return True, None

        ok, target_ver, msg = self.rollback_engine.execute_rollback(
            current_version_num=current_version_num,
            target_version_num=target_version_num,
            reason=reason,
            target_nodes=target_nodes,
            apply_fn=_apply_to_node
        )

        if ok and target_ver:
            # Sync config_values table back to restored version values
            for k, v in target_ver.values.items():
                schema = self.get_schema(k)
                cv = ConfigValue(
                    key=k,
                    scope=target_ver.scope,
                    entity_id=target_ver.target_entity,
                    value=v,
                    version=target_ver.version,
                    is_secret_ref=schema.is_secret if schema else False
                )
                self.persistence.save_value(cv)

            self._emit_event("config.rollback_completed", {
                "rollout_id": f"rollback_{current_version_num}",
                "restored_version": target_ver.version
            })

        return ok, target_ver, msg

    # --- Drift Detection ---
    def detect_node_drift(
        self,
        node_id: str,
        actual_values: Dict[str, Any],
        actual_version: int,
        authorized_overrides: Optional[Dict[str, Any]] = None
    ) -> List[DriftRecord]:
        active_ver = self.persistence.get_active_version()
        expected_ver_num = active_ver.version if active_ver else 1
        expected_vals = active_ver.values if active_ver else {}

        drifts = self.drift_detector.inspect_node_drift(
            node_id=node_id,
            expected_version=expected_ver_num,
            expected_values=expected_vals,
            actual_values=actual_values,
            actual_version=actual_version,
            authorized_overrides=authorized_overrides
        )

        for d in drifts:
            self._emit_event("config.drift_detected", {
                "drift_id": d.drift_id,
                "node_id": d.node_id,
                "key": d.key,
                "expected_version": d.expected_version
            })

        return drifts

    def resolve_drift(self, drift_id: str, strategy: str = "FORCE_SYNC") -> bool:
        ok = self.drift_detector.resolve_drift(drift_id, strategy=strategy)
        if ok:
            self._emit_event("config.drift_resolved", {
                "drift_id": drift_id,
                "node_id": self.node_id,
                "key": "resolved"
            })
        return ok

    # --- Telemetry ---
    def get_telemetry(self) -> ConfigTelemetry:
        active_ver = self.persistence.get_active_version()
        ver_num = active_ver.version if active_ver else 0
        drifts = self.persistence.list_active_drifts()
        active_rollout = self.persistence.get_active_rollout()
        all_vals = self.persistence.get_all_active_values()
        overrides = [v for v in all_vals if v.scope in [ConfigScope.NODE, ConfigScope.DEVICE]]

        # Nodes requiring restart
        pending_restart = []
        if active_ver:
            for k in active_ver.values.keys():
                sch = self.get_schema(k)
                if sch and sch.requires_restart:
                    pending_restart.append(k)

        return ConfigTelemetry(
            current_version=ver_num,
            total_keys=len(self._schemas),
            active_rollout=active_rollout.to_dict() if active_rollout else None,
            pending_restart_nodes=list(set(pending_restart)),
            active_drift_count=len(drifts),
            overrides_count=len(overrides),
            last_updated=time.time()
        )
