"""
Retry Policy & Decision Engine for Omnia Module 26:
External Integration & Connector Gateway

Enforces:
1. SAFE_TO_RETRY vs CONDITIONALLY_RETRYABLE vs NOT_SAFE_TO_RETRY classification.
2. Exponential backoff with jitter and deadline awareness.
3. Upstream Retry-After header integration.
4. Absolute rejection of blind retries for unsafe or financial side effects.
"""

import time
import random
import logging
from typing import Optional, Tuple

from connectors.models import RetryPolicy, ConnectorOperation, OperationType

logger = logging.getLogger("Omnia.Connectors.Retries")


class RetryDecisionEngine:
    """Calculates whether and when a failed connector operation may be safely retried."""

    @staticmethod
    def is_retryable_operation(operation: ConnectorOperation, has_idempotency_key: bool) -> Tuple[bool, str]:
        """
        Evaluates whether an operation's semantics permit safe retries.
        """
        # READ operations are inherently safe
        if operation.operation_type == OperationType.READ or operation.method.upper() == "GET":
            return True, "SAFE_TO_RETRY: Read operation"

        # Explicitly idempotent operations
        if operation.idempotent:
            return True, "SAFE_TO_RETRY: Declared idempotent operation"

        # WRITE or ACTION with valid idempotency token
        if has_idempotency_key:
            return True, "CONDITIONALLY_RETRYABLE: Idempotency token present"

        # Financial or destructive writes without idempotency token MUST NEVER be blindly retried
        if operation.risk_level in ("HIGH", "CRITICAL") or operation.operation_type in (OperationType.WRITE, OperationType.ACTION):
            return False, "NOT_SAFE_TO_RETRY: Non-idempotent write/action side effect"

        return False, "NOT_SAFE_TO_RETRY: Default non-idempotent policy"

    @staticmethod
    def should_retry(
        status_code: int,
        attempt: int,
        policy: RetryPolicy,
        deadline_ts: Optional[float] = None,
        retry_after_header: Optional[str] = None
    ) -> Tuple[bool, float, str]:
        """
        Determines if a retry should occur, returning (should_retry, delay_seconds, reason).
        """
        if attempt >= policy.max_attempts:
            return False, 0.0, f"MAX_ATTEMPTS_EXCEEDED ({attempt}/{policy.max_attempts})"

        # Check status code eligibility
        if status_code not in policy.retryable_status_codes:
            return False, 0.0, f"NON_RETRYABLE_STATUS_CODE ({status_code})"

        # Check deadline bounds
        now = time.time()
        if deadline_ts and now >= deadline_ts:
            return False, 0.0, "DEADLINE_EXCEEDED"

        # Calculate backoff delay
        delay = policy.initial_backoff_sec * (policy.backoff_multiplier ** (attempt - 1))
        delay = min(delay, policy.max_backoff_sec)

        # Apply jitter
        if policy.jitter:
            delay = delay * (0.75 + random.random() * 0.5)

        # Check explicit Retry-After header
        if retry_after_header:
            try:
                header_delay = float(retry_after_header)
                delay = max(delay, header_delay)
            except ValueError:
                pass  # Ignore non-integer or date format for now, use calculated delay

        # Check if delay would overshoot deadline
        if deadline_ts and (now + delay) > deadline_ts:
            return False, 0.0, "DELAY_WOULD_EXCEED_DEADLINE"

        return True, delay, f"RETRYABLE_FAILURE (Attempt {attempt+1}/{policy.max_attempts} in {delay:.2f}s)"


retry_engine = RetryDecisionEngine()
