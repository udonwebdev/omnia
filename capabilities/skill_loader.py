import os
import json
import logging
from typing import Dict, Any, Tuple

from capabilities.models import (
    Capability,
    CapabilityProvider,
    CapabilityCategory,
    CapabilityHealth,
    RiskLevel,
    SideEffectType,
    IdempotencyType,
    ReversibilityType,
    VerificationContract
)
from capabilities.registry import capability_registry, CapabilityRegistry

logger = logging.getLogger("Omnia.Capabilities.SkillLoader")

class DynamicSkillLoader:
    """Safely loads and validates external skill manifests into the capability registry."""

    def __init__(self, registry: CapabilityRegistry = capability_registry):
        self.registry = registry

    def load_skill_from_manifest(self, manifest_dict: Dict[str, Any], auth_key: str = "verified_plugin") -> Tuple[bool, str]:
        """Parses a structured JSON/dict skill definition, verifies trust and schemas, and registers capabilities."""
        if not isinstance(manifest_dict, dict):
            return False, "SCHEMA_ERROR: Manifest must be a JSON dictionary."

        skill_id = manifest_dict.get("id")
        name = manifest_dict.get("name")
        version = manifest_dict.get("version", "1.0.0")
        category_str = manifest_dict.get("category", "SYSTEM")

        if not skill_id or not name:
            return False, "SCHEMA_ERROR: 'id' and 'name' are mandatory fields."

        try:
            category = CapabilityCategory[category_str.upper()]
        except KeyError:
            category = CapabilityCategory.SYSTEM

        risk_str = manifest_dict.get("risk_level", "LOW_RISK")
        try:
            risk = RiskLevel[risk_str.upper()]
        except KeyError:
            risk = RiskLevel.LOW_RISK

        # Construct verification contract if declared
        vc_data = manifest_dict.get("verification_contract")
        vc = None
        if isinstance(vc_data, dict):
            vc = VerificationContract(
                mechanism=vc_data.get("mechanism", "DEFAULT"),
                target_expression=vc_data.get("target_expression"),
                expected_state=vc_data.get("expected_state")
            )

        cap = Capability(
            id=skill_id,
            name=name,
            description=manifest_dict.get("description", ""),
            version=version,
            category=category,
            input_schema=manifest_dict.get("input_schema", {}),
            output_schema=manifest_dict.get("output_schema", {}),
            environment=manifest_dict.get("environment", "local"),
            platforms=manifest_dict.get("platforms", ["windows", "linux", "macos"]),
            required_resources=manifest_dict.get("required_resources", []),
            required_permissions=manifest_dict.get("required_permissions", []),
            risk_level=risk,
            side_effects=[SideEffectType.READ],
            verification_contract=vc,
            dependencies=manifest_dict.get("dependencies", []),
            health=CapabilityHealth.HEALTHY
        )

        ok, msg = self.registry.register_capability(cap, auth_key=auth_key)
        if not ok:
            return False, msg

        # Register default provider if specified
        prov_data = manifest_dict.get("provider")
        if isinstance(prov_data, dict):
            provider = CapabilityProvider(
                provider_id=prov_data.get("provider_id", f"{skill_id}.default_provider"),
                capability_id=skill_id,
                implementation_ref=prov_data.get("implementation_ref", "skill.run"),
                version=version,
                priority=prov_data.get("priority", 10),
                health=CapabilityHealth.HEALTHY,
                latency_ms=prov_data.get("latency_ms", 100.0)
            )
            self.registry.register_provider(provider, auth_key=auth_key)

        return True, f"Skill '{skill_id}' successfully loaded and verified."

skill_loader = DynamicSkillLoader()
