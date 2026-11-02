"""
privacy/ai_governance.py
AI & Machine Learning Privacy Governor:
Enforces prompt redaction, verifies model provider training bans (opt-out of training),
and audits inference retention policies (zero-day vs persistent).
"""

import uuid
import logging
from typing import Dict, Any, Optional

from privacy.models import AIGovernanceConfig
from privacy.persistence import PrivacyRepository
from privacy.transformations import PrivacyTransformationEngine

logger = logging.getLogger("omnia.privacy.ai_governance")


class AIPrivacyGovernor:
    def __init__(self, repo: PrivacyRepository, transformer: PrivacyTransformationEngine):
        self.repo = repo
        self.transformer = transformer

    def configure_model(
        self,
        model_id: str,
        provider: str,
        inference_logging_allowed: bool = False,
        training_permitted: bool = False,
        prompt_redaction_enabled: bool = True,
        retention_policy: str = "ZERO_DAY",
        ai_gov_id: Optional[str] = None
    ) -> AIGovernanceConfig:
        """Registers privacy governance rules for an AI model or external LLM provider."""
        gid = ai_gov_id or f"aig_{uuid.uuid4().hex[:12]}"
        config = AIGovernanceConfig(
            ai_gov_id=gid,
            model_id=model_id,
            provider=provider,
            inference_logging_allowed=inference_logging_allowed,
            training_permitted=training_permitted,
            prompt_redaction_enabled=prompt_redaction_enabled,
            retention_policy=retention_policy
        )
        saved = self.repo.save_ai_governance(config)
        self.repo.log_audit("AI_GOVERNANCE_CONFIGURED", "ai_lead", {
            "model_id": model_id,
            "provider": provider,
            "training_permitted": training_permitted,
            "prompt_redaction": prompt_redaction_enabled
        })
        logger.info(f"AI Governance configured for {model_id} ({provider})")
        return saved

    def sanitize_prompt(self, model_id: str, raw_prompt: str) -> str:
        """Sanitizes user prompts by redacting sensitive PII/secrets before external LLM dispatch."""
        config = self.repo.get_ai_governance(model_id)
        if config and not config.prompt_redaction_enabled:
            return raw_prompt
        return self.transformer.redact(raw_prompt)

    def verify_model_compliance(self, model_id: str) -> Dict[str, Any]:
        """Audits model configuration against enterprise AI privacy mandates."""
        config = self.repo.get_ai_governance(model_id)
        if not config:
            return {"compliant": False, "reason": "MODEL_NOT_GOVERNED"}

        violations = []
        if config.training_permitted:
            violations.append("NON_COMPLIANT: External provider agreement must strictly prohibit training on enterprise prompts.")
        if config.retention_policy not in ("ZERO_DAY", "EPHEMERAL_LOG_ONLY"):
            violations.append(f"HIGH_RISK_RETENTION: Provider retention policy is '{config.retention_policy}'; zero-day retention required.")

        return {
            "model_id": config.model_id,
            "provider": config.provider,
            "compliant": len(violations) == 0,
            "violations": violations,
            "prompt_redaction_enabled": config.prompt_redaction_enabled,
            "training_permitted": config.training_permitted,
            "retention_policy": config.retention_policy
        }
