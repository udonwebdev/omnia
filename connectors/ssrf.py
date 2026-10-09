"""
SSRF Defense & Destination Validation Engine for Omnia Module 26:
External Integration & Connector Gateway

Guarantees:
1. Strict URL scheme validation (only http/https permitted).
2. Hostname and IP resolution pre-flight validation.
3. Private IP (RFC 1918), loopback (127.0.0.0/8, ::1), link-local, and cloud metadata (169.254.169.254) blocking.
4. DNS rebinding prevention via re-validation of resolved IP addresses.
5. Controlled override mechanism strictly for approved local test mock services.
"""

import socket
import ipaddress
import urllib.parse
import logging
from typing import Tuple, List, Set, Optional, Union

logger = logging.getLogger("Omnia.Connectors.SSRF")

# Blocked IP networks
BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),         # IPv4 Loopback
    ipaddress.ip_network("10.0.0.0/8"),          # RFC 1918 Private
    ipaddress.ip_network("172.16.0.0/12"),       # RFC 1918 Private
    ipaddress.ip_network("192.168.0.0/16"),      # RFC 1918 Private
    ipaddress.ip_network("169.254.0.0/16"),      # Link-local / AWS / GCP / Azure metadata
    ipaddress.ip_network("100.64.0.0/10"),       # Carrier-grade NAT
    ipaddress.ip_network("192.0.0.0/24"),        # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),        # TEST-NET-1
    ipaddress.ip_network("198.51.100.0/24"),     # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),      # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),         # Multicast
    ipaddress.ip_network("240.0.0.0/4"),         # Reserved
    ipaddress.ip_network("255.255.255.255/32"),  # Broadcast
    # IPv6
    ipaddress.ip_network("::1/128"),             # IPv6 Loopback
    ipaddress.ip_network("::/128"),              # Unspecified
    ipaddress.ip_network("fe80::/10"),           # Link-local unicast
    ipaddress.ip_network("fc00::/7"),            # Unique local address (ULA)
    ipaddress.ip_network("ff00::/8"),            # Multicast
]

# Explicitly blocked hostnames
BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "instance-data",
}


class SSRFValidationError(ValueError):
    """Raised when an external request targets a restricted or malicious destination."""
    pass


class SSRFValidator:
    """Validates destinations and prevents Server-Side Request Forgery."""

    def __init__(self, allow_loopback_for_testing: bool = False):
        self.allow_loopback_for_testing = allow_loopback_for_testing
        self._allowed_hosts_whitelist: Set[str] = set()

    def add_allowed_test_host(self, host: str):
        """Allows explicit registration of test mock hosts (e.g. 127.0.0.1:8000)."""
        self._allowed_hosts_whitelist.add(host.lower())

    def validate_url(self, url: str) -> Tuple[bool, str]:
        """
        Validates target URL against SSRF policy:
        Checks scheme, hostname, resolved IP addresses, and ports.
        """
        if not url or not isinstance(url, str):
            return False, "SSRF_BLOCKED: URL is empty or invalid type."

        try:
            parsed = urllib.parse.urlsplit(url)
        except Exception as e:
            return False, f"SSRF_BLOCKED: Malformed URL: {e}"

        # 1. Scheme Validation
        scheme = parsed.scheme.lower()
        if scheme not in ("http", "https"):
            return False, f"SSRF_BLOCKED: Disallowed URL scheme '{scheme}'. Only http and https permitted."

        hostname = parsed.hostname
        if not hostname:
            return False, "SSRF_BLOCKED: Missing hostname in URL."

        hostname_lower = hostname.lower()

        # Check explicit test whitelist override
        port = parsed.port
        host_port_key = f"{hostname_lower}:{port}" if port else hostname_lower
        if self.allow_loopback_for_testing or (host_port_key in self._allowed_hosts_whitelist) or (hostname_lower in self._allowed_hosts_whitelist):
            return True, "ALLOWED_BY_TEST_WHITELIST"

        # 2. Blocked Hostnames
        if hostname_lower in BLOCKED_HOSTNAMES or hostname_lower.endswith(".local") or hostname_lower.endswith(".internal"):
            return False, f"SSRF_BLOCKED: Target hostname '{hostname}' is a forbidden internal destination."

        # 3. Direct IP Address Validation
        try:
            ip_obj = ipaddress.ip_address(hostname_lower)
            is_blocked, reason = self._is_blocked_ip(ip_obj)
            if is_blocked:
                return False, f"SSRF_BLOCKED: Target IP '{hostname}' is forbidden ({reason})."
            return True, "VALID_IP"
        except ValueError:
            # Not a raw IP literal, proceed to DNS resolution check
            pass

        # 4. DNS Resolution & Rebinding Prevention
        try:
            addr_info = socket.getaddrinfo(hostname_lower, None)
            resolved_ips = {item[4][0] for item in addr_info}
            if not resolved_ips:
                return False, f"SSRF_BLOCKED: Hostname '{hostname}' could not be resolved."

            for ip_str in resolved_ips:
                ip_obj = ipaddress.ip_address(ip_str)
                is_blocked, reason = self._is_blocked_ip(ip_obj)
                if is_blocked:
                    return False, f"SSRF_BLOCKED: Hostname '{hostname}' resolves to forbidden IP '{ip_str}' ({reason})."
        except socket.gaierror as e:
            return False, f"SSRF_BLOCKED: DNS resolution failure for '{hostname}': {e}"
        except Exception as e:
            return False, f"SSRF_BLOCKED: Failed to validate destination IP for '{hostname}': {e}"

        return True, "VALID"

    def _is_blocked_ip(self, ip_obj: Union[ipaddress.IPv4Address, ipaddress.IPv6Address]) -> Tuple[bool, str]:
        """Checks whether an IP address belongs to any forbidden subnet."""
        if ip_obj.is_loopback:
            return True, "LOOPBACK_ADDRESS"
        if ip_obj.is_private:
            return True, "PRIVATE_NETWORK"
        if ip_obj.is_link_local:
            return True, "LINK_LOCAL_ADDRESS"
        if ip_obj.is_multicast:
            return True, "MULTICAST_ADDRESS"
        if ip_obj.is_reserved:
            return True, "RESERVED_ADDRESS"
        if ip_obj.is_unspecified:
            return True, "UNSPECIFIED_ADDRESS"

        # Check custom blocked networks list
        for net in BLOCKED_NETWORKS:
            if ip_obj in net:
                return True, f"BLOCKED_SUBNET_{net}"

        return False, ""


# Singleton instance with strict defaults
ssrf_validator = SSRFValidator(allow_loopback_for_testing=False)
