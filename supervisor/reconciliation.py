import time
import logging
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple

from persistence.store import persistence_store
from persistence.checkpoints import checkpoint_manager
from persistence.models import PersistedTaskRecord, CheckpointValidity
from events.journal import event_journal
from capabilities.registry import capability_registry
from supervisor.models import Mission, MissionState

logger = logging.getLogger("Omnia.Supervisor.Reconciliation")

class StateConsistency(Enum):
    CONSISTENT = "CONSISTENT"
    INCONSISTENT = "INCONSISTENT"
    UNCERTAIN = "UNCERTAIN"
    CORRUPTED = "CORRUPTED"
    STALE = "STALE"

class StateReconciler:
    """Reconciles persisted database checkpoints, event journal, and live reality after restart."""

    def __init__(self, store=persistence_store, chk_mgr=checkpoint_manager, journal=event_journal):
        self.store = store
        self.chk_mgr = chk_mgr
        self.journal = journal

    def reconcile_task_state(
        self,
        task_id: str,
        is_runtime_active: bool
    ) -> Tuple[StateConsistency, str, Optional[Dict[str, Any]]]:
        """Validates alignment between persisted task state, checkpoints, and runtime reality."""
        task_rec = self.store.load_task(task_id)
        if not task_rec:
            return StateConsistency.INCONSISTENT, f"Task '{task_id}' not found in persistence store", None

        # 1. Inspect recent checkpoint
        chk = self.store.get_latest_checkpoint(task_id)
        if chk:
            is_valid = self.chk_mgr.verify_checkpoint_integrity(chk)
            if not is_valid:
                return StateConsistency.CORRUPTED, "Latest checkpoint integrity check failed", None

        # 2. Crash scenario: Persisted as RUNNING but not currently executing in memory
        if task_rec.status == "RUNNING" and not is_runtime_active:
            # Check heartbeat age
            hb = self.store.get_heartbeat(task_id)
            now = time.time()
            if not hb or (now - hb.timestamp > 30.0):
                logger.warning(f"Reconciliation: Task '{task_id}' recorded as RUNNING but process was dead. State is UNCERTAIN.")
                return StateConsistency.UNCERTAIN, "Process was interrupted mid-flight; task was recorded as RUNNING but is inactive", {
                    "last_checkpoint_id": chk.checkpoint_id if chk else None,
                    "persisted_node_id": task_rec.current_node_id
                }

        # 3. Check for expired deadline
        if task_rec.status == "RUNNING" and time.time() > task_rec.deadline_ts:
            return StateConsistency.STALE, f"Task deadline exceeded at {task_rec.deadline_ts}", None

        return StateConsistency.CONSISTENT, "Task state matches persistent records", {
            "checkpoint_id": chk.checkpoint_id if chk else None,
            "status": task_rec.status
        }

    def reconcile_mission_on_startup(self, mission: Mission) -> MissionState:
        """Inspects mission and its referenced tasks on supervisor restart to safely determine state."""
        if mission.is_terminal():
            return mission.status

        # If mission has active task, reconcile that task
        if mission.active_task_id:
            consistency, reason, details = self.reconcile_task_state(mission.active_task_id, is_runtime_active=False)
            if consistency == StateConsistency.UNCERTAIN:
                logger.info(f"Mission '{mission.mission_id}' state uncertain due to previous process crash. Transitioning to RECOVERING.")
                return MissionState.RECOVERING
            elif consistency in {StateConsistency.CORRUPTED, StateConsistency.INCONSISTENT}:
                logger.error(f"Mission '{mission.mission_id}' inconsistent: {reason}. Transitioning to DEGRADED.")
                return MissionState.DEGRADED
            elif consistency == StateConsistency.STALE:
                return MissionState.TIMED_OUT

        return mission.status

state_reconciler = StateReconciler()
