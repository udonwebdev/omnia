import logging
from typing import List, Optional, Tuple, Dict, Any

from capabilities.models import (
    Capability,
    CapabilityProvider,
    CapabilityMatchQuery,
    CapabilityHealth,
    RiskLevel
)
from capabilities.registry import capability_registry, CapabilityRegistry

logger = logging.getLogger("Omnia.Capabilities.Matcher")

class CapabilityMatcher:
    """Matches requirements from Module 16 to the most suitable capabilities and providers."""

    def __init__(self, registry: CapabilityRegistry = capability_registry):
        self.registry = registry

    def find_matching_capabilities(self, query: CapabilityMatchQuery) -> List[Tuple[Capability, float, str]]:
        """Searches and scores capabilities based on environmental compatibility, risk constraints, and health."""
        candidates: List[Tuple[Capability, float, str]] = []
        all_caps = self.registry.list_capabilities(category=query.intent_category)

        # Risk level hierarchy
        risk_hierarchy = {
            RiskLevel.READ_ONLY: 1,
            RiskLevel.LOW_RISK: 2,
            RiskLevel.MODERATE_RISK: 3,
            RiskLevel.HIGH_RISK: 4,
            RiskLevel.CRITICAL: 5
        }

        for cap in all_caps:
            # Check ID match if specified
            if query.capability_id and cap.id != query.capability_id:
                continue

            # Check environment compatibility
            if query.environment and query.environment != cap.environment and cap.environment != "local":
                continue

            # Check platform compatibility
            if query.required_platforms:
                if not any(p in cap.platforms for p in query.required_platforms):
                    continue

            # Check risk level constraint
            if query.max_risk_level:
                if risk_hierarchy.get(cap.risk_level, 3) > risk_hierarchy.get(query.max_risk_level, 3):
                    continue

            # Check permissions
            if query.available_permissions and cap.required_permissions:
                missing_perms = set(cap.required_permissions) - set(query.available_permissions)
                if missing_perms:
                    continue

            # Score candidate: 1.0 base
            score = 1.0
            reasons = []

            # Health weight
            if cap.health == CapabilityHealth.HEALTHY:
                score += 0.5
                reasons.append("HEALTHY")
            elif cap.health == CapabilityHealth.DEGRADED:
                score += 0.1
                reasons.append("DEGRADED")
            elif cap.health in [CapabilityHealth.UNAVAILABLE, CapabilityHealth.FAILED, CapabilityHealth.BLOCKED, CapabilityHealth.DISABLED]:
                score -= 0.8
                reasons.append(f"{cap.health.value}")

            # Idempotency bonus
            if cap.idempotent.value == "IDEMPOTENT":
                score += 0.2
                reasons.append("IDEMPOTENT")

            # Verification contract bonus
            if cap.verification_contract:
                score += 0.2
                reasons.append("VERIFIABLE")

            candidates.append((cap, round(score, 2), ", ".join(reasons)))

        # Sort descending by match score
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates

    def resolve_best_capability_and_provider(
        self,
        capability_id: str,
        target_environment: Optional[str] = None
    ) -> Tuple[Optional[Capability], Optional[CapabilityProvider], str]:
        """Resolves an authoritative capability and provider pair with explanation."""
        cap = self.registry.get_capability(capability_id)
        if not cap:
            return None, None, f"CAPABILITY_NOT_FOUND: No capability registered for ID '{capability_id}'."

        if cap.health in [CapabilityHealth.UNAVAILABLE, CapabilityHealth.FAILED, CapabilityHealth.BLOCKED, CapabilityHealth.DISABLED]:
            return cap, None, f"CAPABILITY_UNAVAILABLE: Capability '{capability_id}' is currently {cap.health.value}."

        provider = self.registry.resolve_provider(capability_id, environment=target_environment)
        if not provider:
            return cap, None, f"NO_HEALTHY_PROVIDER: Capability '{capability_id}' has no active/healthy provider."

        explanation = f"Matched {cap.id} v{cap.version} with provider '{provider.provider_id}' [Priority: {provider.priority}, Latency: {provider.latency_ms}ms]."
        return cap, provider, explanation

capability_matcher = CapabilityMatcher()
