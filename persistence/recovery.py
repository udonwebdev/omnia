import time
import logging
from typing import Optional, Dict, Any, List, Tuple

from persistence.models import (
    RecoveryCondition,
    ResumeStrategy,
    CheckpointValidity,
    PersistedTaskRecord,
    PersistedCheckpoint
)
from persistence.store import persistence_store
from persistence.checkpoints import checkpoint_manager, CheckpointManager

logger = logging.getLogger("Omnia.Persistence.CrashRecovery")

class CrashRecoveryEngine:
    """Classifies interrupted tasks, validates real-world environment, and decides recovery paths."""

    def __init__(self, store=persistence_store, chk_mgr=None):
        self.store = store
        if chk_mgr is not None:
            self.chk_mgr = chk_mgr
        else:
            self.chk_mgr = CheckpointManager(store=self.store)

    def scan_for_crashes(self, heartbeat_timeout_sec: float = 30.0) -> List[Dict[str, Any]]:
        """Identifies interrupted tasks abandoned by crashes or dead processes."""
        interrupted = self.store.list_interrupted_tasks(heartbeat_timeout_sec=heartbeat_timeout_sec)
        reclaimed_locks = self.store.reclaim_stale_locks(timeout_sec=heartbeat_timeout_sec)
        if reclaimed_locks:
            logger.info(f"Reclaimed {len(reclaimed_locks)} stale resource locks: {reclaimed_locks}")
        return interrupted

    def classify_interrupted_task(self, task_id: str) -> Tuple[RecoveryCondition, ResumeStrategy, str]:
        """Examines last checkpoint, node idempotency, and journal events to determine recovery safety."""
        task = self.store.load_task(task_id)
        if not task:
            return RecoveryCondition.CORRUPTED, ResumeStrategy.ABORT_TASK, "Task not found in store"

        nodes = self.store.load_nodes_for_task(task_id)
        current_node = next((n for n in nodes if n.node_id == task.current_node_id), None)
        latest_chk = self.chk_mgr.store.get_latest_checkpoint(task_id)

        if not latest_chk:
            # Started but never reached a single verified checkpoint
            return RecoveryCondition.UNCERTAIN, ResumeStrategy.REPLAN_FROM_CURRENT_STATE, "No checkpoint established before crash"

        # Validate checkpoint integrity
        val = self.chk_mgr.evaluate_checkpoint_validity(latest_chk)
        if val == CheckpointValidity.INVALID:
            return RecoveryCondition.CORRUPTED, ResumeStrategy.ABORT_TASK, "Checkpoint checksum mismatch or corrupted data"
        if val == CheckpointValidity.STALE:
            return RecoveryCondition.STALE, ResumeStrategy.REVALIDATE_AND_RESUME, "Checkpoint is older than freshness threshold"

        # Check current node's idempotency contract & capability availability
        if current_node:
            # Module 17: Revalidate capability presence, health, and compatibility
            cap_id = current_node.metadata.get("capability") if hasattr(current_node, "metadata") and isinstance(current_node.metadata, dict) else None
            if cap_id:
                try:
                    from capabilities.registry import capability_registry
                    from capabilities.models import CapabilityHealth
                    cap = capability_registry.get_capability(cap_id)
                    if not cap or cap.health in [CapabilityHealth.UNAVAILABLE, CapabilityHealth.FAILED, CapabilityHealth.DISABLED]:
                        return (
                            RecoveryCondition.UNCERTAIN,
                            ResumeStrategy.REPLAN_FROM_CURRENT_STATE,
                            f"CAPABILITY_CHANGED: Capability '{cap_id}' is no longer healthy or available."
                        )
                except Exception as e:
                    logger.warning(f"Error checking capability '{cap_id}': {e}")

            if current_node.idempotency == "NOT_SAFE_TO_RETRY":
                # E.g. payment, submit button, deletion, file destruction
                return (
                    RecoveryCondition.UNCERTAIN,
                    ResumeStrategy.REVALIDATE_AND_RESUME,
                    f"Interrupted during non-idempotent action '{current_node.name}'. Mandatory revalidation required before retrying."
                )
            elif current_node.idempotency == "CONDITIONALLY_RETRYABLE":
                return (
                    RecoveryCondition.RECOVERABLE,
                    ResumeStrategy.ROLLBACK_TO_CHECKPOINT,
                    f"Interrupted in state that can safely re-sync from checkpoint."
                )

        # Standard safe retry / read actions
        return (
            RecoveryCondition.RECOVERABLE,
            ResumeStrategy.RESUME_FROM_CHECKPOINT,
            "Interrupted during safe idempotent step with valid checkpoint."
        )

    async def validate_real_world_state(
        self,
        task_id: str,
        expected_state: Optional[str] = None,
        revalidation_checker: Optional[Any] = None
    ) -> Tuple[bool, str]:
        """Inspects actual reality (DOM, Vision, device, or API) to check if the action completed while offline."""
        if not revalidation_checker:
            # Default fallback: assuming valid unless evidence exists
            return True, "No specific validator registered; assuming state unchanged"

        try:
            if callable(revalidation_checker):
                import inspect
                if inspect.iscoroutinefunction(revalidation_checker):
                    is_ok = await revalidation_checker(task_id, expected_state)
                else:
                    is_ok = revalidation_checker(task_id, expected_state)
                return bool(is_ok), "Real-world revalidation passed" if is_ok else "Real-world state contradicts checkpoint expectations"
            return False, "Invalid validator provided"
        except Exception as e:
            logger.warning(f"Revalidation error: {e}")
            return False, f"Revalidation inspection failed: {e}"

    def record_recovery_decision(self, task_id: str, condition: RecoveryCondition, strategy: ResumeStrategy, reason: str, success: bool):
        """Durable record of crash recovery attempt for audit and HUD visibility."""
        import uuid
        import uuid
        conn = self.store._get_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT INTO recovery_attempts (
                        attempt_id, task_id, timestamp, condition, strategy, decision_reason, success, evidence_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(uuid.uuid4())[:8], task_id, time.time(), condition.value,
                    strategy.value, reason, 1 if success else 0, "{}"
                ))
        finally:
            conn.close()

        self.store.append_event(task_id, "RECOVERY_DECISION", {
            "condition": condition.value,
            "strategy": strategy.value,
            "reason": reason,
            "success": success
        })

crash_recovery_engine = CrashRecoveryEngine()
