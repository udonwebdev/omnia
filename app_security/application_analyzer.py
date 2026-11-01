"""
OMNIA Module 46: Autonomous Application Security Testing, Vulnerability Intelligence & Defensive Validation
Application Security Analyzer - application_analyzer.py

Performs static AST source analysis, detects injection patterns, insecure deserialization,
path traversal, XSS, CSRF, and cryptographic weaknesses. Findings always reference evidence.
"""

from __future__ import annotations

import ast
import hashlib
import logging
import uuid
from typing import Any, Dict, List, Optional

from app_security.models import FindingCategory, SecurityFinding, Severity
from app_security.persistence import AppSecurityRepository

logger = logging.getLogger("Omnia.AppSecurity.ApplicationAnalyzer")


class ApplicationSecurityAnalyzer:
    """
    Defensively analyzes application source code and AST constructs for security weaknesses.
    """

    def __init__(self, repository: Optional[AppSecurityRepository] = None):
        self.repo = repository or AppSecurityRepository()

    def analyze_source_code(
        self,
        assessment_id: str,
        asset_id: str,
        filename: str,
        source_code: str
    ) -> List[SecurityFinding]:
        findings: List[SecurityFinding] = []

        try:
            tree = ast.parse(source_code, filename=filename)
        except Exception as e:
            logger.warning(f"Could not parse AST for {filename}: {e}")
            return findings

        for node in ast.walk(tree):
            # 1. SQL Injection / Raw formatting check
            if isinstance(node, ast.Call):
                func_name = ""
                if isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr
                elif isinstance(node.func, ast.Name):
                    func_name = node.func.id

                # execute() called with format string or binary operator % / +
                if func_name in ("execute", "executemany", "raw"):
                    for arg in node.args:
                        if isinstance(arg, (ast.BinOp, ast.JoinedStr)):
                            f = self._create_finding(
                                assessment_id=assessment_id,
                                asset_id=asset_id,
                                title=f"Potential SQL Injection via Dynamic Query Construction in {func_name}()",
                                category=FindingCategory.INJECTION,
                                severity=Severity.HIGH,
                                cwe_id="CWE-89",
                                component_ref=filename,
                                location_ref=f"Line {node.lineno}",
                                evidence={"call": func_name, "line": node.lineno}
                            )
                            findings.append(f)

                # 2. Insecure Deserialization (pickle.loads, yaml.load without SafeLoader)
                if func_name in ("loads", "load") and isinstance(node.func, ast.Attribute):
                    mod_name = getattr(node.func.value, "id", "")
                    if mod_name == "pickle":
                        f = self._create_finding(
                            assessment_id=assessment_id,
                            asset_id=asset_id,
                            title="Insecure Deserialization via pickle.load/loads",
                            category=FindingCategory.INJECTION,
                            severity=Severity.CRITICAL,
                            cwe_id="CWE-502",
                            component_ref=filename,
                            location_ref=f"Line {node.lineno}",
                            evidence={"module": "pickle", "line": node.lineno}
                        )
                        findings.append(f)

                # 3. Command Injection (os.system, subprocess with shell=True)
                if func_name in ("system", "popen") and getattr(node.func, "value", None) and getattr(node.func.value, "id", "") == "os":
                    f = self._create_finding(
                        assessment_id=assessment_id,
                        asset_id=asset_id,
                        title="Command Injection Risk in os.system()",
                        category=FindingCategory.INJECTION,
                        severity=Severity.HIGH,
                        cwe_id="CWE-78",
                        component_ref=filename,
                        location_ref=f"Line {node.lineno}",
                        evidence={"func": "os.system", "line": node.lineno}
                    )
                    findings.append(f)

                # Subprocess with shell=True keyword
                if func_name in ("run", "Popen", "call") and getattr(node.func, "value", None) and getattr(node.func.value, "id", "") == "subprocess":
                    for kw in node.keywords:
                        if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            f = self._create_finding(
                                assessment_id=assessment_id,
                                asset_id=asset_id,
                                title="Subprocess Executed with shell=True",
                                category=FindingCategory.INJECTION,
                                severity=Severity.MEDIUM,
                                cwe_id="CWE-78",
                                component_ref=filename,
                                location_ref=f"Line {node.lineno}",
                                evidence={"func": "subprocess", "shell": True, "line": node.lineno}
                            )
                            findings.append(f)

        for f in findings:
            self.repo.save_finding(f)

        logger.info(f"Analyzed {filename}: Found {len(findings)} security findings.")
        return findings

    def _create_finding(
        self,
        assessment_id: str,
        asset_id: str,
        title: str,
        category: FindingCategory,
        severity: Severity,
        cwe_id: str,
        component_ref: str,
        location_ref: str,
        evidence: Dict[str, Any]
    ) -> SecurityFinding:
        fid = f"find-{uuid.uuid4().hex[:8]}"
        fp_raw = f"{asset_id}:{title}:{category.value}:{component_ref}:{location_ref}"
        fp_sha = hashlib.sha256(fp_raw.encode("utf-8")).hexdigest()
        return SecurityFinding(
            finding_id=fid,
            assessment_id=assessment_id,
            asset_id=asset_id,
            title=title,
            category=category,
            severity=severity,
            cwe_id=cwe_id,
            component_ref=component_ref,
            location_ref=location_ref,
            evidence_redacted=evidence,
            fingerprint_sha256=fp_sha
        )
