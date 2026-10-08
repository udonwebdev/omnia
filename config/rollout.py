import uuid
import time
import logging
from typing import Dict, Any, List, Optional, Callable, Tuple
from config.models import ConfigRollout, RolloutStrategy, RolloutStatus, ConfigVersion
from config.persistence import ConfigPersistence

logger = logging.getLogger("Omnia.Config.Rollout")

class RolloutOrchestrator:
    """Manages staged, multi-strategy configuration rollouts across cluster nodes with failure gating."""

    def __init__(self, persistence: Optional[ConfigPersistence] = None):
        self.persistence = persistence or ConfigPersistence()

    def create_rollout(
        self,
        version: int,
        target_nodes: List[str],
        strategy: RolloutStrategy = RolloutStrategy.ROLLING,
        batch_size: int = 1,
        failure_threshold_pct: float = 0.0
    ) -> ConfigRollout:
        rollout_id = f"rollout_{version}_{uuid.uuid4().hex[:6]}"
        rollout = ConfigRollout(
            rollout_id=rollout_id,
            version=version,
            strategy=strategy,
            status=RolloutStatus.PENDING,
            batch_size=max(1, batch_size),
            failure_threshold_pct=failure_threshold_pct,
            target_nodes=list(target_nodes),
            completed_nodes=[],
            failed_nodes=[],
            current_batch=0
        )
        self.persistence.save_rollout(rollout)
        return rollout

    def compute_batches(self, rollout: ConfigRollout) -> List[List[str]]:
        nodes = rollout.target_nodes
        if not nodes:
            return []

        if rollout.strategy == RolloutStrategy.ALL_AT_ONCE:
            return [nodes]

        elif rollout.strategy == RolloutStrategy.CANARY:
            # First batch is canary (1 node), subsequent batches take remainder
            canary = [nodes[0]]
            remainder = nodes[1:]
            batches = [canary]
            if remainder:
                b_size = rollout.batch_size
                for i in range(0, len(remainder), b_size):
                    batches.append(remainder[i:i + b_size])
            return batches

        elif rollout.strategy == RolloutStrategy.ROLLING:
            b_size = rollout.batch_size
            batches = []
            for i in range(0, len(nodes), b_size):
                batches.append(nodes[i:i + b_size])
            return batches

        elif rollout.strategy == RolloutStrategy.MANUAL:
            # In manual mode, each node is handled individually
            return [[n] for n in nodes]

        return [nodes]

    def advance_rollout(
        self,
        rollout_id: str,
        apply_fn: Callable[[str, int], Tuple[bool, Optional[str]]]
    ) -> ConfigRollout:
        """Executes next batch in rollout. apply_fn(node_id, version) -> (success, error_msg)."""
        rollout = self.persistence.get_rollout(rollout_id)
        if not rollout:
            raise ValueError(f"Rollout '{rollout_id}' not found.")

        if rollout.status in [RolloutStatus.COMPLETED, RolloutStatus.FAILED, RolloutStatus.ROLLED_BACK]:
            return rollout

        batches = self.compute_batches(rollout)
        if not batches:
            rollout.status = RolloutStatus.COMPLETED
            rollout.updated_at = time.time()
            self.persistence.save_rollout(rollout)
            return rollout

        if rollout.current_batch >= len(batches):
            rollout.status = RolloutStatus.COMPLETED
            rollout.updated_at = time.time()
            self.persistence.save_rollout(rollout)
            return rollout

        rollout.status = RolloutStatus.IN_PROGRESS
        current_nodes = batches[rollout.current_batch]
        logger.info(f"Advancing rollout '{rollout_id}' batch {rollout.current_batch + 1}/{len(batches)}: {current_nodes}")

        batch_failed = []
        for node in current_nodes:
            success, err = apply_fn(node, rollout.version)
            if success:
                if node not in rollout.completed_nodes:
                    rollout.completed_nodes.append(node)
            else:
                if node not in rollout.failed_nodes:
                    rollout.failed_nodes.append(node)
                batch_failed.append((node, err))

        rollout.current_batch += 1
        rollout.updated_at = time.time()

        # Check failure threshold
        total_attempted = len(rollout.completed_nodes) + len(rollout.failed_nodes)
        failure_pct = (len(rollout.failed_nodes) / max(1, len(rollout.target_nodes))) * 100.0

        if failure_pct > rollout.failure_threshold_pct and len(rollout.failed_nodes) > 0:
            rollout.status = RolloutStatus.FAILED
            rollout.failure_reason = f"Failure threshold exceeded ({failure_pct:.1f}% > {rollout.failure_threshold_pct}%): {batch_failed}"
            logger.error(f"Rollout '{rollout_id}' halted: {rollout.failure_reason}")
        elif rollout.current_batch >= len(batches):
            rollout.status = RolloutStatus.COMPLETED
            logger.info(f"Rollout '{rollout_id}' successfully completed for all {len(rollout.completed_nodes)} nodes.")

        self.persistence.save_rollout(rollout)
        return rollout

    def pause_rollout(self, rollout_id: str, reason: str = "Operator paused") -> Optional[ConfigRollout]:
        rollout = self.persistence.get_rollout(rollout_id)
        if not rollout:
            return None
        rollout.status = RolloutStatus.PAUSED
        rollout.failure_reason = reason
        rollout.updated_at = time.time()
        self.persistence.save_rollout(rollout)
        return rollout

    def resume_rollout(self, rollout_id: str) -> Optional[ConfigRollout]:
        rollout = self.persistence.get_rollout(rollout_id)
        if not rollout or rollout.status != RolloutStatus.PAUSED:
            return rollout
        rollout.status = RolloutStatus.IN_PROGRESS
        rollout.updated_at = time.time()
        self.persistence.save_rollout(rollout)
        return rollout

    def abort_rollout(self, rollout_id: str, reason: str = "Operator aborted") -> Optional[ConfigRollout]:
        rollout = self.persistence.get_rollout(rollout_id)
        if not rollout:
            return None
        rollout.status = RolloutStatus.FAILED
        rollout.failure_reason = reason
        rollout.updated_at = time.time()
        self.persistence.save_rollout(rollout)
        return rollout
