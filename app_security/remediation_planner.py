"""
OMNIA Module 46: Autonomous Application Security Testing, Vulnerability Intelligence & Defensive Validation
Remediation Planning Engine - remediation_planner.py

Generates actionable corrective actions, dependency upgrades, AST pattern refactorings,
and patch diffs. Never automatically modifies production without explicit authorization.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

from app_security.models import FindingCategory, RemediationPlan, SecurityFinding
from app_security.persistence import AppSecurityRepository

logger = logging.getLogger("Omnia.AppSecurity.RemediationPlanner")


class RemediationPlanner:
    """
    Synthesizes concrete remediation plans and code patches for confirmed security findings.
    """

    def __init__(self, repository: Optional[AppSecurityRepository] = None):
        self.repo = repository or AppSecurityRepository()

    def generate_plan_for_finding(self, finding_id: str) -> RemediationPlan:
        finding = self.repo.get_finding(finding_id)
        if not finding:
            raise ValueError(f"Finding {finding_id} not found.")

        pid = f"plan-{uuid.uuid4().hex[:8]}"

        action = "REMEDIATION_GENERIC"
        details: Dict[str, Any] = {}
        breaking_risk = "LOW"
        complexity = "SIMPLE"
        diff = None

        if finding.category == FindingCategory.SECRET_LEAK:
            action = "ROTATE_SECRET_AND_PURGE_HISTORY"
            details = {
                "step_1": "Revoke exposed credential in credential provider immediately",
                "step_2": "Provision new secret into Module 25 Vault",
                "step_3": "Rewrite git history to remove secret commitment if present"
            }
            complexity = "MODERATE"
            diff = f"- API_KEY = \"{finding.evidence_redacted.get('masked_sample', 'SECRET')}\"\n+ API_KEY = os.environ.get(\"API_KEY\")"

        elif finding.category == FindingCategory.VULN_DEPENDENCY:
            pkg = finding.evidence_redacted.get("package", "package")
            fixed_ver = finding.evidence_redacted.get("fixed_version", "latest")
            action = "UPGRADE_DEPENDENCY"
            details = {
                "package": pkg,
                "target_version": fixed_ver,
                "instruction": f"Bump {pkg} to >= {fixed_ver} in requirements.txt"
            }
            diff = f"- {pkg}=={finding.evidence_redacted.get('installed_version', '0.0.0')}\n+ {pkg}>={fixed_ver}"

        elif finding.category == FindingCategory.INJECTION:
            action = "PARAMETERIZE_QUERY"
            details = {
                "recommendation": "Replace dynamic string interpolation with parameterized queries.",
                "cwe": finding.cwe_id
            }
            breaking_risk = "MEDIUM"
            complexity = "MODERATE"
            diff = "- cursor.execute(f\"SELECT * FROM t WHERE id = '{user_id}'\")\n+ cursor.execute(\"SELECT * FROM t WHERE id = ?\", (user_id,))"

        elif finding.category == FindingCategory.MISCONFIG:
            action = "HARDEN_CONFIGURATION"
            details = {"recommendation": "Configure non-root user and restrict permissive bindings."}
            diff = "+ USER appuser\n"

        plan = RemediationPlan(
            plan_id=pid,
            finding_id=finding_id,
            recommended_action=action,
            action_details=details,
            breaking_change_risk=breaking_risk,
            estimated_complexity=complexity,
            patch_diff=diff
        )
        self.repo.save_remediation_plan(plan)
        logger.info(f"Generated remediation plan {pid} for finding {finding_id} ({action})")
        return plan
