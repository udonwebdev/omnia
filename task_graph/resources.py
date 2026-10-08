import asyncio
import time
import logging
from typing import Dict, Optional, Set

logger = logging.getLogger("Omnia.TaskGraph.Resources")

class ResourceLockManager:
    """Manages exclusive and non-blocking resource locks across concurrent tasks."""

    def __init__(self):
        self._locks: Dict[str, str] = {} # resource_name -> owning_task_id
        self._timestamps: Dict[str, float] = {}
        self._cond = asyncio.Condition()

    async def acquire_locks(self, task_id: str, resources: list, timeout_sec: float = 10.0) -> bool:
        """Acquires all specified resource locks atomically. Releases all on failure/timeout."""
        if not resources:
            return True

        deadline = time.time() + timeout_sec
        async with self._cond:
            while True:
                # Check for expired locks (> 60s)
                now = time.time()
                expired = [r for r, ts in self._timestamps.items() if now - ts > 60.0]
                for r in expired:
                    logger.warning(f"Releasing stale resource lock: {r}")
                    del self._locks[r]
                    del self._timestamps[r]

                # Check availability
                available = all(r not in self._locks or self._locks[r] == task_id for r in resources)
                if available:
                    for r in resources:
                        self._locks[r] = task_id
                        self._timestamps[r] = now
                    logger.info(f"Task {task_id} acquired resource lock(s): {resources}")
                    return True

                remaining = deadline - time.time()
                if remaining <= 0:
                    logger.warning(f"Task {task_id} timed out waiting for locks: {resources}")
                    return False

                try:
                    await asyncio.wait_for(self._cond.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    return False

    async def release_locks(self, task_id: str, resources: Optional[list] = None):
        """Releases locks owned by task_id."""
        async with self._cond:
            to_release = []
            for r, owner in list(self._locks.items()):
                if owner == task_id and (resources is None or r in resources):
                    to_release.append(r)
                    del self._locks[r]
                    if r in self._timestamps:
                        del self._timestamps[r]

            if to_release:
                logger.info(f"Task {task_id} released resource lock(s): {to_release}")
                self._cond.notify_all()

    def get_lock_owner(self, resource: str) -> Optional[str]:
        return self._locks.get(resource)

resource_manager = ResourceLockManager()
