"""
Rate Limiting & Concurrency Manager for Omnia Module 26:
External Integration & Connector Gateway

Features:
1. Token bucket rate limiting (requests/second, requests/minute, burst capacity).
2. Concurrency limiting (max concurrent in-flight requests).
3. Provider Retry-After header parsing and backoff tracking.
4. Fail-safe throttler preventing infinite hammering of external APIs.
"""

import time
import asyncio
import logging
from typing import Dict, Optional, Tuple

from connectors.models import RateLimitPolicy

logger = logging.getLogger("Omnia.Connectors.RateLimiter")


class RateLimitExceededError(Exception):
    """Raised when request is throttled due to connector rate limits or upstream 429."""
    def __init__(self, message: str, retry_after_sec: float = 1.0):
        super().__init__(message)
        self.retry_after_sec = retry_after_sec


class TokenBucketLimiter:
    """Token bucket rate limiter supporting continuous replenishment and burst capacity."""

    def __init__(self, policy: RateLimitPolicy):
        self.policy = policy
        self.tokens: float = float(policy.burst_limit)
        self.last_refill: float = time.time()
        self.active_concurrency: int = 0
        self.throttled_until: float = 0.0

    def _refill(self):
        now = time.time()
        elapsed = now - self.last_refill
        if elapsed > 0:
            # Replenish based on requests_per_second
            refill_rate = self.policy.requests_per_second
            self.tokens = min(float(self.policy.burst_limit), self.tokens + (elapsed * refill_rate))
            self.last_refill = now

    def acquire(self) -> Tuple[bool, float]:
        """
        Attempts to acquire a request slot.
        Returns (allowed, wait_seconds_if_not_allowed).
        """
        now = time.time()

        # Check explicit upstream Retry-After throttle
        if now < self.throttled_until:
            wait_sec = self.throttled_until - now
            return False, wait_sec

        # Check concurrency bounds
        if self.active_concurrency >= self.policy.max_concurrent_requests:
            return False, 0.2

        self._refill()

        if self.tokens >= 1.0:
            self.tokens -= 1.0
            self.active_concurrency += 1
            return True, 0.0
        else:
            # Calculate wait time for at least 1 token
            wait_sec = (1.0 - self.tokens) / max(0.1, self.policy.requests_per_second)
            return False, wait_sec

    def release(self):
        """Releases active concurrency slot upon request completion."""
        if self.active_concurrency > 0:
            self.active_concurrency -= 1

    def handle_retry_after(self, retry_after_sec: float):
        """Sets an upstream throttle block based on provider 429 Retry-After response."""
        now = time.time()
        self.throttled_until = max(self.throttled_until, now + retry_after_sec)
        logger.warning(f"RATE_LIMIT_BACKOFF: Upstream requested backoff for {retry_after_sec:.2f}s.")


class RateLimiterRegistry:
    """Manages rate limiters per connector and instance."""

    def __init__(self):
        self._limiters: Dict[str, TokenBucketLimiter] = {}

    def get_limiter(self, key: str, policy: Optional[RateLimitPolicy] = None) -> TokenBucketLimiter:
        if key not in self._limiters:
            self._limiters[key] = TokenBucketLimiter(policy or RateLimitPolicy())
        return self._limiters[key]


rate_limiter_registry = RateLimiterRegistry()
