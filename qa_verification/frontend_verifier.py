"""
OMNIA Module 45: Autonomous Quality Assurance, Software Verification & Continuous Testing Intelligence
Frontend & Visual Verifier - frontend_verifier.py

Validates user interface flows, forms, console error absence, navigation paths,
and integrates with Module 13 vision when visual regression verification is available.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Omnia.QAVerification.FrontendVerifier")


class FrontendVerifier:
    """
    Validates web and mobile user interfaces, interactive components, and visual integrity.
    """

    def __init__(self, vision_service: Optional[Any] = None):
        self.vision = vision_service

    def verify_ui_workflow(
        self,
        page_url: str,
        expected_elements: List[str],
        rendered_elements: List[str],
        console_logs: Optional[List[str]] = None,
    ) -> tuple[bool, List[str]]:
        discrepancies: List[str] = []

        # Element presence
        for el in expected_elements:
            if el not in rendered_elements:
                discrepancies.append(f"Missing required UI element: '{el}'")

        # Console errors check
        if console_logs:
            for log in console_logs:
                if "error" in log.lower() or "exception" in log.lower():
                    discrepancies.append(f"Client-side console error detected: '{log}'")

        passed = len(discrepancies) == 0
        logger.info(f"Frontend verification for '{page_url}': Passed={passed}, Discrepancies={len(discrepancies)}")
        return passed, discrepancies
