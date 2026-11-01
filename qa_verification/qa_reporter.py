"""
Autonomous Quality Assurance — Comprehensive Quality Reporter
Compiles evidence-backed verification summaries, coverage gaps, and quality posture HUDs.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from .persistence import QAVerificationRepository
from .models import QualityAssessment, QualityTier, DefectSeverity


class QAReporter:
    def __init__(self, repository: Optional[QAVerificationRepository] = None):
        self.repo = repository or QAVerificationRepository()

    def compile_project_quality_report(self, project_id: str) -> Dict[str, Any]:
        project = self.repo.get_project(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found.")

        requirements = self.repo.list_requirements(project_id)
        test_cases = self.repo.list_test_cases(project_id)
        unresolved_defects = self.repo.list_unresolved_defects(project_id)
        blocker_defects = [d for d in unresolved_defects if d.severity in (DefectSeverity.CRITICAL, DefectSeverity.BLOCKER)]

        return {
            "project_id": project_id,
            "project_name": project.name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "metrics": {
                "requirements_total": len(requirements),
                "test_cases_total": len(test_cases),
                "unresolved_defects_total": len(unresolved_defects),
                "blocker_defects_count": len(blocker_defects),
            },
            "gate_recommendation": {
                "promotable_to_production": len(blocker_defects) == 0,
                "blocking_reasons": [f"Unresolved {d.severity.value} defect: {d.title}" for d in blocker_defects]
            }
        }
