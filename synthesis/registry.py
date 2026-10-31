"""
OMNIA Module 36: Intelligence Product Registry
Manages registry of recurring and on-demand intelligence products with scope validation.
"""

import uuid
import time
import logging
from typing import Dict, Any, List, Optional
from synthesis.models import (
    IntelligenceProductRecord,
    ProductType,
    AudienceLevel,
    ProductLifecycleState,
)
from synthesis.persistence import SynthesisRepository

logger = logging.getLogger("Omnia.Synthesis.Registry")


class IntelligenceProductRegistry:
    """Manages creation, configuration, and scoping of intelligence products."""

    def __init__(self, repo: SynthesisRepository):
        self.repo = repo

    def register_product(
        self,
        name: str,
        purpose: str,
        product_type: ProductType,
        domain: str,
        intended_audience: AudienceLevel,
        authorized_scope: str,
        required_sources: List[str],
        update_cadence: str = "ON_DEMAND",
        max_length_words: int = 1500,
        freshness_window_sec: float = 86400.0,
        retention_days: int = 90,
        approval_required: bool = False,
    ) -> IntelligenceProductRecord:
        """Validates and registers an intelligence product definition."""
        if not name or len(name.strip()) < 3:
            raise ValueError("Product name must be at least 3 characters")
        if not authorized_scope:
            raise ValueError("Intelligence products must define an authorized scope")
        if not required_sources:
            raise ValueError("Intelligence products must require at least one verified evidence source")

        product_id = f"prod-{uuid.uuid4().hex[:8]}"
        record = IntelligenceProductRecord(
            product_id=product_id,
            name=name.strip(),
            purpose=purpose.strip(),
            product_type=product_type,
            domain=domain.strip(),
            intended_audience=intended_audience,
            authorized_scope=authorized_scope.strip(),
            required_sources=required_sources,
            update_cadence=update_cadence,
            max_length_words=max_length_words,
            freshness_window_sec=freshness_window_sec,
            retention_days=retention_days,
            approval_required=approval_required,
            version=1,
            state=ProductLifecycleState.ACTIVE,
        )
        self.repo.save_product(record)
        logger.info(f"Registered intelligence product '{product_id}': {record.name} [{record.product_type.value}]")
        return record

    def get_product(self, product_id: str) -> Optional[IntelligenceProductRecord]:
        return self.repo.get_product(product_id)

    def list_products(self, state: Optional[ProductLifecycleState] = None) -> List[IntelligenceProductRecord]:
        return self.repo.list_products(state=state)

    def update_product_state(self, product_id: str, new_state: ProductLifecycleState) -> bool:
        prod = self.repo.get_product(product_id)
        if not prod:
            return False
        prod.state = new_state
        prod.updated_at = time.time()
        self.repo.save_product(prod)
        logger.info(f"Updated intelligence product {product_id} state to {new_state.value}")
        return True
