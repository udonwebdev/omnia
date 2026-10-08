import asyncio
import random
import logging
from typing import Optional, Tuple
from task_graph.models import (
    TaskNode,
    TaskFailure,
    FailureCategory,
    RecoveryStrategy,
    IdempotencyLevel,
    ExecutionContext
)

logger = logging.getLogger("Omnia.TaskGraph.Recovery")

class RecoveryEngine:
    """Classifies execution errors, calculates backoff delays, and decides recovery workflows."""

    @staticmethod
    def classify_exception(exc: Exception, node: TaskNode) -> TaskFailure:
        """Categorizes an exception into a structured TaskFailure."""
        msg = str(exc)
        exc_type = type(exc).__name__
        cat = FailureCategory.UNKNOWN
        retryable = False
        suggested = RecoveryStrategy.ABORT

        if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
            cat = FailureCategory.TIMEOUT
            retryable = node.idempotency != IdempotencyLevel.NOT_SAFE_TO_RETRY
            suggested = RecoveryStrategy.RETRY if retryable else RecoveryStrategy.ABORT

        elif isinstance(exc, PermissionError) or "POLICY_REJECTION" in msg:
            cat = FailureCategory.POLICY_BLOCK
            retryable = False
            suggested = RecoveryStrategy.ABORT

        elif "DEVICE_NOT_FOUND" in msg or "ADB" in msg or "127.0.0.1:5037" in msg:
            cat = FailureCategory.DEVICE_UNAVAILABLE
            retryable = True
            suggested = RecoveryStrategy.RECONNECT

        elif "net::ERR" in msg or "ECONNREFUSED" in msg or "navigation" in msg.lower():
            cat = FailureCategory.NETWORK_FAILURE
            retryable = True
            suggested = RecoveryStrategy.REFRESH

        elif "UNEXPECTED_UI_STATE" in msg:
            cat = FailureCategory.UNEXPECTED_STATE
            retryable = True
            suggested = RecoveryStrategy.RECAPTURE

        elif "BROWSER" in msg.upper():
            cat = FailureCategory.BROWSER_FAILURE
            retryable = True
            suggested = RecoveryStrategy.RECONNECT

        elif "VISION" in msg.upper() or "TARGET_NOT_FOUND" in msg:
            cat = FailureCategory.VISION_FAILURE
            retryable = True
            suggested = RecoveryStrategy.RECAPTURE

        else:
            cat = FailureCategory.TOOL_FAILURE
            retryable = node.idempotency == IdempotencyLevel.SAFE_TO_RETRY
            suggested = RecoveryStrategy.RETRY if retryable else RecoveryStrategy.ABORT

        return TaskFailure(
            node_id=node.node_id,
            category=cat,
            message=f"{exc_type}: {msg}",
            evidence=msg,
            retryable=retryable,
            suggested_recovery=suggested
        )

    @staticmethod
    def calculate_backoff(attempt: int, policy) -> float:
        """Calculates exponential backoff with random jitter."""
        if not policy.exponential_backoff:
            delay = policy.base_delay_sec
        else:
            delay = min(policy.max_delay_sec, policy.base_delay_sec * (2 ** (attempt - 1)))

        if policy.jitter:
            delay = delay * (0.5 + random.random())

        return max(0.1, delay)

    async def execute_recovery(
        self,
        strategy: RecoveryStrategy,
        node: TaskNode,
        context: ExecutionContext
    ) -> bool:
        """Executes targeted recovery action. Returns True if recovery succeeded and step can be retried."""
        logger.info(f"Executing recovery strategy '{strategy.value}' for node '{node.name}'")

        if strategy == RecoveryStrategy.ABORT:
            return False

        elif strategy == RecoveryStrategy.RETRY:
            delay = self.calculate_backoff(node.attempts, node.retry_policy)
            logger.info(f"Backing off for {delay:.2f}s before retry...")
            await asyncio.sleep(delay)
            return True

        elif strategy == RecoveryStrategy.REFRESH:
            try:
                from browser_driver import browser_driver
                if browser_driver.active_page:
                    logger.info("Recovery action: Reloading active browser page...")
                    await browser_driver.active_page.reload(wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(1.0)
                    return True
            except Exception as e:
                logger.warning(f"Browser refresh recovery failed: {e}")
            return False

        elif strategy == RecoveryStrategy.RECONNECT:
            try:
                from browser_driver import browser_driver
                logger.info("Recovery action: Reinitializing browser driver...")
                await browser_driver.initialize()
                return True
            except Exception as e:
                logger.warning(f"Browser reconnect recovery failed: {e}")
            return False

        elif strategy == RecoveryStrategy.RECAPTURE:
            try:
                from vision import vision_engine, VisionSource
                logger.info("Recovery action: Re-capturing fresh screen frame...")
                await vision_engine.capture(source=VisionSource.BROWSER)
                await asyncio.sleep(1.0)
                return True
            except Exception as e:
                logger.warning(f"Screen recapture recovery failed: {e}")
            return False

        elif strategy == RecoveryStrategy.SKIP_OPTIONAL:
            node.state = NodeState.SKIPPED
            return True

        return False

recovery_engine = RecoveryEngine()
