import time
import logging
from typing import Dict, Any, List, Optional, Tuple, Callable
from config.models import ConfigVersion, ConfigVersionStatus, ConfigRollout, RolloutStatus, RolloutStrategy
from config.persistence import ConfigPersistence

logger = logging.getLogger("Omnia.Config.Rollback")

class RollbackEngine:
    """Orchestrates atomic and safe rollbacks to previous configuration versions upon failure or operator request."""

    def __init__(self, persistence: Optional[ConfigPersistence] = None):
        self.persistence = persistence or ConfigPersistence()

    def determine_rollback_target(self, current_version_num: int, target_version_num: Optional[int] = None) -> Optional[ConfigVersion]:
        """Identifies target version to restore."""
        if target_version_num is not None:
            target = self.persistence.get_version(target_version_num)
            if target:
                return target

        current = self.persistence.get_version(current_version_num)
        if current and current.parent_version:
            target = self.persistence.get_version(current.parent_version)
            if target:
                return target

        # Fallback to most recent previously active version
        versions = self.persistence.list_versions(limit=10)
        for v in versions:
            if v.version < current_version_num and v.status in [ConfigVersionStatus.ACTIVE, ConfigVersionStatus.SUPERSEDED]:
                return v

        return None

    def execute_rollback(
        self,
        current_version_num: int,
        target_version_num: Optional[int],
        reason: str,
        target_nodes: List[str],
        apply_fn: Callable[[str, int], Tuple[bool, Optional[str]]]
    ) -> Tuple[bool, Optional[ConfigVersion], str]:
        """Rolls back the cluster or entity to the target version."""
        target = self.determine_rollback_target(current_version_num, target_version_num)
        if not target:
            return False, None, f"No viable rollback target found for version {current_version_num}."

        logger.warning(f"ROLLBACK INITIATED: Rolling back from version {current_version_num} to {target.version}. Reason: {reason}")

        # Mark current version as ROLLED_BACK
        self.persistence.set_version_status(current_version_num, ConfigVersionStatus.ROLLED_BACK)

        # Reactivate target version
        self.persistence.set_version_status(target.version, ConfigVersionStatus.ACTIVE, activated_at=time.time())

        # Distribute target version to nodes
        failed_nodes = []
        for node in target_nodes:
            ok, err = apply_fn(node, target.version)
            if not ok:
                failed_nodes.append((node, err))

        if failed_nodes:
            msg = f"Rollback partially succeeded. Restored target version {target.version}, but failed on nodes: {failed_nodes}"
            logger.error(msg)
            return False, target, msg

        msg = f"Rollback successfully completed. Cluster restored to version {target.version}."
        logger.info(msg)
        return True, target, msg
