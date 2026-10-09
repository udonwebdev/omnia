"""
Circuit Breaker Pattern Engine for Omnia Module 26:
External Integration & Connector Gateway

Prevents cascading failures and catastrophic thrashing of degraded or failing external services.
States:
- CLOSED: Normal operations. Failures increment counter.
- OPEN: Calls fast-fail immediately without network transmission.
- HALF_OPEN: Trial probe requests test upstream provider recovery.
"""

import time
import logging
from typing import Dict, Optional, Tuple

from connectors.models import CircuitState, CircuitBreakerConfig

logger = logging.getLogger("Omnia.Connectors.CircuitBreaker")


class CircuitOpenError(Exception):
    """Raised when an operation is attempted while the connector circuit is OPEN."""
    pass


class CircuitBreaker:
    """Manages circuit state transitions for a connector or instance."""

    def __init__(self, connector_id: str, config: Optional[CircuitBreakerConfig] = None):
        self.connector_id = connector_id
        self.config = config or CircuitBreakerConfig()
        self.state: CircuitState = CircuitState.CLOSED
        self.failure_count: int = 0
        self.success_count: int = 0
        self.last_failure_time: Optional[float] = None
        self.last_state_change: float = time.time()
        self.half_open_in_flight: bool = False

    def can_execute(self) -> Tuple[bool, str]:
        """
        Evaluates whether a new external request is permitted.
        Returns (is_allowed, reason).
        """
        now = time.time()

        if self.state == CircuitState.CLOSED:
            return True, "CIRCUIT_CLOSED"

        elif self.state == CircuitState.OPEN:
            # Check if recovery probe interval has elapsed
            time_open = now - self.last_state_change
            if time_open >= self.config.recovery_probe_interval_sec:
                logger.info(f"Circuit for '{self.connector_id}' transitioning OPEN -> HALF_OPEN (probe interval elapsed: {time_open:.1f}s).")
                self.state = CircuitState.HALF_OPEN
                self.last_state_change = now
                self.success_count = 0
                self.half_open_in_flight = True
                return True, "CIRCUIT_HALF_OPEN_PROBE"
            else:
                remaining = self.config.recovery_probe_interval_sec - time_open
                return False, f"CIRCUIT_OPEN (probe available in {remaining:.1f}s)"

        elif self.state == CircuitState.HALF_OPEN:
            # Permit limited probe traffic
            if not self.half_open_in_flight:
                self.half_open_in_flight = True
                return True, "CIRCUIT_HALF_OPEN_PROBE"
            return False, "CIRCUIT_HALF_OPEN_BUSY"

        return False, f"CIRCUIT_UNKNOWN_STATE: {self.state}"

    def record_success(self):
        """Records a successful response from the external provider."""
        self.half_open_in_flight = False

        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.consecutive_success_threshold:
                logger.info(f"Circuit for '{self.connector_id}' RECOVERED. Transitioning HALF_OPEN -> CLOSED.")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                self.last_state_change = time.time()

        elif self.state == CircuitState.CLOSED:
            # Gradually decay failure count on clean successes
            if self.failure_count > 0:
                self.failure_count = max(0, self.failure_count - 1)

    def record_failure(self, error_message: str = ""):
        """Records an upstream failure (e.g. timeout, 5xx server error, connection drop)."""
        now = time.time()
        self.last_failure_time = now
        self.half_open_in_flight = False

        if self.state == CircuitState.CLOSED:
            self.failure_count += 1
            if self.failure_count >= self.config.failure_threshold:
                logger.warning(
                    f"CIRCUIT_TRIPPED: Connector '{self.connector_id}' exceeded failure threshold "
                    f"({self.failure_count}/{self.config.failure_threshold}). Transitioning CLOSED -> OPEN. Cause: {error_message}"
                )
                self.state = CircuitState.OPEN
                self.last_state_change = now

        elif self.state == CircuitState.HALF_OPEN:
            logger.warning(
                f"CIRCUIT_PROBE_FAILED: Connector '{self.connector_id}' probe request failed. "
                f"Re-opening circuit HALF_OPEN -> OPEN. Cause: {error_message}"
            )
            self.state = CircuitState.OPEN
            self.success_count = 0
            self.last_state_change = now

    def reset(self):
        """Manually resets circuit back to CLOSED state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_state_change = time.time()
        self.half_open_in_flight = False
        logger.info(f"Circuit for '{self.connector_id}' manually reset to CLOSED.")


class CircuitBreakerRegistry:
    """Registry managing circuit breaker instances per connector."""

    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}

    def get_breaker(self, connector_id: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        if connector_id not in self._breakers:
            self._breakers[connector_id] = CircuitBreaker(connector_id, config)
        return self._breakers[connector_id]

    def reset_all(self):
        for b in self._breakers.values():
            b.reset()


circuit_breaker_registry = CircuitBreakerRegistry()
