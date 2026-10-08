import hashlib
import json
import time
import uuid
import logging
from typing import Optional, Dict, Any, List

from persistence.models import (
    PersistedCheckpoint,
    CheckpointPolicy,
    CheckpointValidity
)
from persistence.store import persistence_store, sanitize_payload

logger = logging.getLogger("Omnia.Persistence.Checkpoints")

class CheckpointManager:
    """Creates, verifies, and restores atomic, tamper-evident execution checkpoints."""

    def __init__(self, store=persistence_store):
        self.store = store

    def compute_checkpoint_checksum(self, task_id: str, timestamp: float, task_state: str, node_states: Dict[str, str], variables: Dict[str, Any]) -> str:
        """Generates SHA-256 integrity checksum across critical checkpoint state."""
        hasher = hashlib.sha256()
        canonical_str = f"{task_id}|{timestamp:.4f}|{task_state}|{json.dumps(node_states, sort_keys=True)}|{json.dumps(variables, sort_keys=True)}"
        hasher.update(canonical_str.encode("utf-8"))
        return hasher.hexdigest()

    def create_checkpoint(
        self,
        task_id: str,
        node_id: Optional[str],
        task_state: str,
        node_states: Dict[str, str],
        variables: Dict[str, Any],
        resource_state: List[str],
        last_verified_observations: List[Dict[str, Any]],
        policy_trigger: CheckpointPolicy = CheckpointPolicy.CHECKPOINT_NODE_COMPLETE,
        browser_state_ref: Optional[str] = None,
        device_state_ref: Optional[str] = None,
        vision_frame_ref: Optional[str] = None
    ) -> PersistedCheckpoint:
        """Captures and atomically saves a durable state checkpoint."""
        now = time.time()
        clean_vars = sanitize_payload(variables)
        clean_obs = sanitize_payload(last_verified_observations)

        chk_id = f"chk_{str(uuid.uuid4())[:8]}"
        checksum = self.compute_checkpoint_checksum(
            task_id=task_id,
            timestamp=now,
            task_state=task_state,
            node_states=node_states,
            variables=clean_vars
        )

        checkpoint = PersistedCheckpoint(
            checkpoint_id=chk_id,
            task_id=task_id,
            node_id=node_id,
            timestamp=now,
            task_state=task_state,
            node_states=node_states,
            variables=clean_vars,
            resource_state=resource_state,
            last_verified_observations=clean_obs,
            policy_trigger=policy_trigger.value,
            browser_state_ref=browser_state_ref,
            device_state_ref=device_state_ref,
            vision_frame_ref=vision_frame_ref,
            checksum=checksum
        )

        try:
            self.store.save_checkpoint(checkpoint)
            self.store.append_event(task_id, "CHECKPOINT_CREATED", {
                "checkpoint_id": chk_id,
                "node_id": node_id,
                "trigger": policy_trigger.value,
                "checksum": checksum[:12]
            })
            logger.info(f"Checkpoint '{chk_id}' created for task '{task_id}' (Trigger: {policy_trigger.value})")
            return checkpoint
        except Exception as e:
            logger.error(f"CHECKPOINT_WRITE_FAILED: Could not persist checkpoint: {e}")
            raise RuntimeError(f"CHECKPOINT_WRITE_FAILED: {e}")

    def verify_checkpoint_integrity(self, checkpoint: PersistedCheckpoint) -> bool:
        """Validates that checkpoint data has not been modified or corrupted on disk."""
        expected = self.compute_checkpoint_checksum(
            task_id=checkpoint.task_id,
            timestamp=checkpoint.timestamp,
            task_state=checkpoint.task_state,
            node_states=checkpoint.node_states,
            variables=checkpoint.variables
        )
        return expected == checkpoint.checksum

    def evaluate_checkpoint_validity(
        self,
        checkpoint: PersistedCheckpoint,
        max_age_sec: float = 3600.0,
        required_resources_active: bool = True
    ) -> CheckpointValidity:
        """Evaluates whether the checkpoint is still fresh and applicable to current reality."""
        # 1. Check data integrity
        if not self.verify_checkpoint_integrity(checkpoint):
            logger.warning(f"Checkpoint '{checkpoint.checkpoint_id}' failed cryptographic integrity check!")
            return CheckpointValidity.INVALID

        # 2. Check age
        age = time.time() - checkpoint.timestamp
        if age > max_age_sec:
            logger.warning(f"Checkpoint '{checkpoint.checkpoint_id}' is stale (Age: {age:.1f}s > {max_age_sec}s)")
            return CheckpointValidity.STALE

        # 3. Check hardware / environment requirements if noted
        if not required_resources_active:
            return CheckpointValidity.INVALID

        return CheckpointValidity.VALID

checkpoint_manager = CheckpointManager()
