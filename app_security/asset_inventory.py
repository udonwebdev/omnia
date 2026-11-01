"""
OMNIA Module 46: Autonomous Application Security Testing, Vulnerability Intelligence & Defensive Validation
Security Asset Inventory - asset_inventory.py

Tracks applications, services, APIs, repositories, containers, and infrastructure configurations.
Enforces that unverified discovered assets are never automatically authorized.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app_security.models import (
    AssetType, Criticality, EnvironmentTier, ExposureTier, SecurityAsset, SecurityAuditRecord
)
from app_security.persistence import AppSecurityRepository

logger = logging.getLogger("Omnia.AppSecurity.AssetInventory")


class AssetInventory:
    """
    Maintains a security-focused inventory of all authorized and registered assets.
    """

    def __init__(self, repository: Optional[AppSecurityRepository] = None):
        self.repo = repository or AppSecurityRepository()

    def register_asset(
        self,
        name: str,
        asset_type: AssetType,
        owner: str,
        environment: EnvironmentTier = EnvironmentTier.STAGING,
        exposure_tier: ExposureTier = ExposureTier.INTERNAL,
        criticality: Criticality = Criticality.MEDIUM,
        technology_stack: Optional[List[str]] = None,
        discovery_source: str = "MANUAL",
        asset_id: Optional[str] = None
    ) -> SecurityAsset:
        aid = asset_id or f"asset-{uuid.uuid4().hex[:8]}"
        asset = SecurityAsset(
            asset_id=aid,
            name=name,
            asset_type=asset_type,
            owner=owner,
            environment=environment,
            exposure_tier=exposure_tier,
            criticality=criticality,
            technology_stack=technology_stack or [],
            discovery_source=discovery_source
        )
        self.repo.save_asset(asset)
        self.repo.save_audit_record(
            SecurityAuditRecord(
                audit_id=f"audit-{uuid.uuid4().hex[:8]}",
                authorization_id=None,
                asset_id=aid,
                action_type="ASSET_REGISTERED",
                actor=owner,
                details={"name": name, "type": asset_type.value, "env": environment.value}
            )
        )
        logger.info(f"Registered security asset {aid} ('{name}', Type={asset_type.value}, Env={environment.value})")
        return asset

    def get_asset(self, asset_id: str) -> Optional[SecurityAsset]:
        return self.repo.get_asset(asset_id)

    def list_assets(self) -> List[SecurityAsset]:
        return self.repo.list_assets()

    def update_asset_posture(self, asset_id: str, new_score: float) -> None:
        asset = self.repo.get_asset(asset_id)
        if asset:
            asset.security_posture_score = max(0.0, min(100.0, new_score))
            asset.last_assessed_at = datetime.now(timezone.utc).isoformat()
            self.repo.save_asset(asset)
