import re
import logging
from enum import Enum
from typing import Tuple, Dict, Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Omnia.PolicyEngine")

class RiskLevel(Enum):
    SAFE = 1
    MODERATE = 2
    CRITICAL = 3

class PolicyEngine:
    """Enforces execution boundaries and identifies destructive operation patterns."""

    def __init__(self):
        # Destructive patterns for shell commands
        self.critical_shell_patterns = [
            r"\brm\s+-[rf]{1,2}\b",
            r"\bmkfs\b",
            r"\bdd\s+if=",
            r"\bpm\s+clear\b",
            r"\bpm\s+uninstall\b",
            r"\breboot\b",
            r"\bshutdown\b",
            r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\};\s*:", # Forkbomb
        ]

        # Sensitive keywords for browser actions
        self.critical_web_patterns = [
            r"checkout",
            r"confirm payment",
            r"delete account",
            r"transfer funds",
            r"cvv",
            r"card number"
        ]

    def assess_shell_command(self, cmd: str) -> Tuple[RiskLevel, str]:
        """Assesses the risk level of an OS or ADB shell string."""
        for pattern in self.critical_shell_patterns:
            if re.search(pattern, cmd, re.IGNORECASE):
                return RiskLevel.CRITICAL, f"Blocked: Matches restricted pattern '{pattern}'"
        return RiskLevel.SAFE, "Permitted"

    def assess_web_task(self, url: str, objective: str) -> Tuple[RiskLevel, str]:
        """Assesses the risk level of an autonomous browser action."""
        for pattern in self.critical_web_patterns:
            if re.search(pattern, objective, re.IGNORECASE):
                return RiskLevel.CRITICAL, f"Intervention required: Objective involves financial or destructive web action: '{pattern}'"
        return RiskLevel.SAFE, "Permitted"

    def verify_action(self, tool_name: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        """Validates tool execution against current security policy."""
        if tool_name == "execute_mesh_shell_command":
            cmd = params.get("shell_command", "")
            risk, reason = self.assess_shell_command(cmd)
            if risk == RiskLevel.CRITICAL:
                logger.error(f"[SECURITY ALERT] Tool '{tool_name}' blocked. Reason: {reason}")
                return False, reason

        elif tool_name == "execute_web_task":
            objective = params.get("objective", "")
            url = params.get("target_url", "")
            risk, reason = self.assess_web_task(url, objective)
            if risk == RiskLevel.CRITICAL:
                logger.warning(f"[POLICY INTERVENTION] Tool '{tool_name}' requires human override. Reason: {reason}")
                return False, reason

        return True, "Execution Approved"

policy_engine = PolicyEngine()
