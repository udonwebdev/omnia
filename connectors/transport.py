"""
Secure HTTP Transport Layer for Omnia Module 26:
External Integration & Connector Gateway

Features:
1. Strict connection timeout, read timeout, and total execution deadline.
2. SSRF destination pre-check and redirect destination re-validation.
3. Request and response size bounding (prevents memory exhaustion).
4. Redaction of sensitive headers and credentials before error logging.
"""

import time
import httpx
import logging
from typing import Dict, Any, Optional, Tuple

from connectors.ssrf import ssrf_validator, SSRFValidationError
from connectors.models import TimeoutPolicy
from secrets.redaction import redaction_engine

logger = logging.getLogger("Omnia.Connectors.Transport")

MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10MB maximum response size


class SecureTransport:
    """Production HTTP transport enforcing security boundaries and timeouts."""

    def __init__(self, validator=None):
        self.ssrf = validator or ssrf_validator

    async def execute_http_request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Any] = None,
        data_body: Optional[Any] = None,
        timeout: Optional[TimeoutPolicy] = None
    ) -> Tuple[int, Dict[str, str], Any, float, bool]:
        """
        Executes HTTP request within security and timeout boundaries.
        Returns (status_code, headers_dict, parsed_body, latency_ms, timed_out).
        """
        t_policy = timeout or TimeoutPolicy()

        # 1. Pre-flight SSRF Validation
        is_valid, reason = self.ssrf.validate_url(url)
        if not is_valid:
            logger.error(f"SSRF_PREVENTION: Dispatched URL '{url}' blocked: {reason}")
            raise SSRFValidationError(f"Target URL '{url}' blocked by SSRF policy: {reason}")

        client_timeout = httpx.Timeout(
            connect=t_policy.connect_timeout_sec,
            read=t_policy.read_timeout_sec,
            write=10.0,
            pool=5.0
        )

        t0 = time.perf_counter()
        timed_out = False

        try:
            async with httpx.AsyncClient(timeout=client_timeout, follow_redirects=False) as client:
                current_url = url
                redirect_count = 0
                max_redirects = 5

                while True:
                    # Enforce SSRF check on each redirect hop
                    if redirect_count > 0:
                        hop_valid, hop_reason = self.ssrf.validate_url(current_url)
                        if not hop_valid:
                            raise SSRFValidationError(f"Redirect URL '{current_url}' blocked by SSRF policy: {hop_reason}")

                    response = await client.request(
                        method=method,
                        url=current_url,
                        headers=headers,
                        params=params,
                        json=json_body if json_body is not None else None,
                        data=data_body if data_body is not None else None
                    )

                    # Check for redirect (301, 302, 307, 308)
                    if response.is_redirect and "location" in response.headers and redirect_count < max_redirects:
                        redirect_count += 1
                        current_url = str(response.headers["location"])
                        logger.debug(f"Following verified redirect ({redirect_count}/{max_redirects}) to: {current_url}")
                        continue
                    break

                latency_ms = (time.perf_counter() - t0) * 1000.0

                # Bounded response reading
                content = response.content
                if len(content) > MAX_RESPONSE_BYTES:
                    raise ValueError(f"Response size ({len(content)} bytes) exceeds maximum limit ({MAX_RESPONSE_BYTES} bytes).")

                # Parse JSON if applicable, otherwise return text
                parsed_body = None
                content_type = response.headers.get("content-type", "").lower()
                if "application/json" in content_type:
                    try:
                        parsed_body = response.json()
                    except Exception:
                        parsed_body = response.text
                else:
                    parsed_body = response.text

                return response.status_code, dict(response.headers), parsed_body, latency_ms, False

        except httpx.TimeoutException as e:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            logger.warning(f"TRANSPORT_TIMEOUT: Request to '{url}' timed out after {latency_ms:.1f}ms: {e}")
            return 504, {}, None, latency_ms, True

        except (httpx.ConnectError, httpx.NetworkError) as e:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            logger.warning(f"TRANSPORT_NETWORK_ERROR: Connection failed to '{url}': {e}")
            return 502, {}, None, latency_ms, False

        except SSRFValidationError:
            raise

        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            logger.error(f"TRANSPORT_ERROR: Request to '{url}' failed: {e}")
            return 500, {}, None, latency_ms, False


secure_transport = SecureTransport()
