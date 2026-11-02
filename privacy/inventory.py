"""
privacy/inventory.py
Enterprise Data Inventory managing registration, discovery, classification roll-up,
and lifecycle of enterprise data assets across databases, tables, files, streams,
caches, AI inference models, and backups.
"""

import uuid
import time
import logging
from typing import List, Optional, Dict, Any

from privacy.models import DataAsset, AssetType, SensitivityTier
from privacy.persistence import PrivacyRepository

logger = logging.getLogger("omnia.privacy.inventory")


class EnterpriseDataInventory:
    def __init__(self, repo: PrivacyRepository):
        self.repo = repo

    def register_asset(
        self,
        name: str,
        asset_type: str,
        storage_location: str,
        owner: str,
        residency_country: str = "US",
        sensitivity_tier: str = "INTERNAL",
        metadata: Optional[Dict[str, Any]] = None,
        asset_id: Optional[str] = None
    ) -> DataAsset:
        """Registers a new data asset into the enterprise inventory."""
        a_id = asset_id or f"ast_{uuid.uuid4().hex[:12]}"
        now = time.time()

        # Parse enums safely
        atype = AssetType(asset_type.upper()) if asset_type.upper() in AssetType._value2member_map_ else AssetType.DATABASE
        stier = SensitivityTier(sensitivity_tier.upper()) if sensitivity_tier.upper() in SensitivityTier._value2member_map_ else SensitivityTier.INTERNAL

        asset = DataAsset(
            asset_id=a_id,
            name=name,
            asset_type=atype,
            storage_location=storage_location,
            owner=owner,
            residency_country=residency_country.upper(),
            sensitivity_tier=stier,
            is_active=True,
            created_at=now,
            updated_at=now,
            metadata=metadata or {}
        )
        saved = self.repo.save_asset(asset)
        self.repo.log_audit("ASSET_REGISTERED", owner, {"asset_id": a_id, "name": name, "tier": stier.value})
        logger.info(f"Asset registered: {a_id} ({name}, tier={stier.value})")
        return saved

    def update_asset(
        self,
        asset_id: str,
        name: Optional[str] = None,
        storage_location: Optional[str] = None,
        owner: Optional[str] = None,
        residency_country: Optional[str] = None,
        sensitivity_tier: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        is_active: Optional[bool] = None
    ) -> Optional[DataAsset]:
        """Updates attributes of an existing registered data asset."""
        asset = self.repo.get_asset(asset_id)
        if not asset:
            return None

        if name is not None:
            asset.name = name
        if storage_location is not None:
            asset.storage_location = storage_location
        if owner is not None:
            asset.owner = owner
        if residency_country is not None:
            asset.residency_country = residency_country.upper()
        if sensitivity_tier is not None:
            stier = SensitivityTier(sensitivity_tier.upper()) if sensitivity_tier.upper() in SensitivityTier._value2member_map_ else asset.sensitivity_tier
            asset.sensitivity_tier = stier
        if metadata is not None:
            asset.metadata.update(metadata)
        if is_active is not None:
            asset.is_active = is_active
        asset.updated_at = time.time()

        saved = self.repo.save_asset(asset)
        self.repo.log_audit("ASSET_UPDATED", asset.owner, {"asset_id": asset_id, "tier": asset.sensitivity_tier.value})
        return saved

    def get_asset(self, asset_id: str) -> Optional[DataAsset]:
        return self.repo.get_asset(asset_id)

    def list_assets(
        self,
        residency: Optional[str] = None,
        sensitivity_tier: Optional[str] = None,
        active_only: bool = True
    ) -> List[DataAsset]:
        return self.repo.list_assets(residency=residency, sensitivity_tier=sensitivity_tier, active_only=active_only)

    def recalculate_asset_sensitivity(self, asset_id: str) -> SensitivityTier:
        """Computes the overall asset sensitivity tier based on its most sensitive field classification."""
        asset = self.repo.get_asset(asset_id)
        if not asset:
            return SensitivityTier.INTERNAL

        classifications = self.repo.get_classifications_by_asset(asset_id)
        if not classifications:
            return asset.sensitivity_tier

        highest_rank = 1
        highest_tier = SensitivityTier.PUBLIC
        for c in classifications:
            rank = SensitivityTier.rank(c.sensitivity_tier)
            if rank > highest_rank:
                highest_rank = rank
                highest_tier = c.sensitivity_tier

        if highest_tier != asset.sensitivity_tier:
            asset.sensitivity_tier = highest_tier
            asset.updated_at = time.time()
            self.repo.save_asset(asset)
            self.repo.log_audit("ASSET_TIER_ESCALATED", "system", {"asset_id": asset_id, "new_tier": highest_tier.value})
        return highest_tier
