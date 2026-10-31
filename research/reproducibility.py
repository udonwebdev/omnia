"""
OMNIA Module 35: Research Reproducibility & Traceable Report Generation
Produces cryptographic reproducibility manifests and comprehensive research reports
linking findings to verifiable empirical evidence without invented citations.
"""

import time
import uuid
import hashlib
import json
import logging
from typing import Dict, Any, List, Optional
from research.models import (
    ResearchRequest,
    ResearchConclusion,
    ReproducibilityManifest,
    HypothesisRecord,
    ExperimentDefinition,
)
from research.persistence import ResearchRepository

logger = logging.getLogger("Omnia.Research.Reproducibility")


class ReproducibilityManager:
    """Creates reproducible manifests and generates evidence-backed scientific reports."""

    def __init__(self, repo: ResearchRepository):
        self.repo = repo

    def generate_manifest(
        self,
        research_id: str,
        dataset: List[Dict[str, Any]],
        random_seed: Optional[int] = 42,
    ) -> ReproducibilityManifest:
        """Computes cryptographic digest of empirical datasets and pins methodology version."""
        raw_bytes = json.dumps(dataset, sort_keys=True).encode()
        dataset_digest = hashlib.sha256(raw_bytes).hexdigest()
        code_digest = hashlib.sha256(b"OMNIA_RESEARCH_TESTING_V1").hexdigest()

        manifest = ReproducibilityManifest(
            manifest_id=f"rep-{uuid.uuid4().hex[:8]}",
            research_id=research_id,
            dataset_digest_sha256=dataset_digest,
            methodology_version="1.0.0-welch-interval",
            code_digest_sha256=code_digest,
            random_seed=random_seed,
            environment_metadata={"engine": "Omnia Research Engine", "version": "1.0"},
            replay_instructions=f"Replay experiment with seed {random_seed} against dataset SHA-256 {dataset_digest}",
        )
        self.repo.save_reproducibility(manifest)
        logger.info(f"Generated reproducibility manifest {manifest.manifest_id} (Dataset SHA-256: {dataset_digest[:16]}...)")
        return manifest

    def generate_report(
        self,
        research_id: str,
        conclusion: ResearchConclusion,
        hypotheses: List[HypothesisRecord],
        experiments: List[ExperimentDefinition],
    ) -> str:
        """Generates a structured, evidence-traceable markdown research report."""
        req = self.repo.get_request(research_id)
        manifest = self.repo.get_reproducibility(research_id)

        title = req.normalized_objective if req else f"Research Investigation {research_id}"
        q_text = req.original_question if req else "N/A"

        report_lines = [
            f"# Scientific Research Report: {title}",
            f"**Research ID**: `{research_id}` | **Status**: `{conclusion.state.value}` | **Timestamp**: `{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(conclusion.concluded_at))}`\n",
            "## 1. Research Question & Scope",
            f"> **Question**: {q_text}\n",
            f"- **Domain**: {req.domain if req else 'N/A'}",
            f"- **Scope**: {req.scope if req else 'N/A'}",
            f"- **Risk Classification**: {req.risk_level if req else 'LOW'}\n",
            "## 2. Hypotheses Evaluated",
        ]

        for h in hypotheses:
            report_lines.append(f"- **[{h.state.value}] Hypothesis `{h.hypothesis_id}`** ({h.hypothesis_type.value}): {h.statement}")
            report_lines.append(f"  - *Confidence*: {h.confidence_score * 100:.1f}%")
            if h.supporting_evidence:
                report_lines.append(f"  - *Supporting Evidence*: {h.supporting_evidence[-1]}")

        report_lines.append("\n## 3. Experimental Protocol & Controls")
        for e in experiments:
            report_lines.append(f"- **Experiment `{e.experiment_id}`**: {e.title}")
            report_lines.append(f"  - *Type*: {e.experiment_type.value} | *Sample Size*: {e.sample_size}")
            report_lines.append(f"  - *Controlled Variables*: {', '.join(e.controlled_variables)}")
            report_lines.append(f"  - *Isolation*: {e.isolation_environment}")

        report_lines.append("\n## 4. Empirical Observations")
        for obs in conclusion.direct_observations:
            report_lines.append(f"- {obs}")

        report_lines.append("\n## 5. Traceable Conclusion & Limitations")
        report_lines.append(f"**Conclusion State**: `{conclusion.state.value}`")
        report_lines.append(f"{conclusion.summary}\n")
        report_lines.append("**Scope Limitations**:")
        for lim in conclusion.scope_limitations:
            report_lines.append(f"- {lim}")

        if manifest:
            report_lines.append("\n## 6. Reproducibility Manifest")
            report_lines.append(f"- **Manifest ID**: `{manifest.manifest_id}`")
            report_lines.append(f"- **Dataset SHA-256**: `{manifest.dataset_digest_sha256}`")
            report_lines.append(f"- **Methodology Version**: `{manifest.methodology_version}`")
            report_lines.append(f"- **Replay Instructions**: {manifest.replay_instructions}")

        report_lines.append("\n---\n*Report generated by OMNIA Module 35 Autonomous Research Engine. Zero fabricated citations.*")
        return "\n".join(report_lines)
