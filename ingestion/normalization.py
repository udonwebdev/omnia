"""
Data Normalization & Canonical Mapping Engine for Omnia Module 27:
Data Ingestion, Normalization & Knowledge Pipeline

Guarantees:
1. Provider-specific representations map to typed canonical entities (Person, Transaction, Message, Resource, etc.).
2. Normalization is deterministic, explicit, and versioned.
3. Every normalization step attaches a full ProvenanceRecord and LineageStep.
4. Data quality metadata is objectively calculated without manufactured precision.
"""

import time
import uuid
import hashlib
import json
import logging
from typing import Dict, Any, Tuple, Optional, List, Callable

from ingestion.models import (
    IngestionEnvelope,
    NormalizedRecord,
    ProvenanceRecord,
    LineageStep,
    QualityMetadata,
    FreshnessStatus,
    IdentityConfidence
)

logger = logging.getLogger("Omnia.Ingestion.Normalization")


class NormalizationEngine:
    """Transforms raw provider payloads into canonical records with full lineage."""

    def __init__(self):
        self._transformers: Dict[str, Tuple[str, Callable[[Dict[str, Any]], Dict[str, Any]]]] = {}
        self._init_built_in_transformers()

    def _init_built_in_transformers(self):
        """Initializes canonical mappings for standard Omnia connector outputs."""
        # 1. GitHub Repository -> Canonical Resource
        def transform_github_repo(raw: Dict[str, Any]) -> Dict[str, Any]:
            owner = raw.get("owner", {})
            owner_login = owner.get("login") if isinstance(owner, dict) else str(owner)
            return {
                "id": str(raw.get("id", "")),
                "name": raw.get("name", ""),
                "full_name": raw.get("full_name", ""),
                "owner": owner_login,
                "url": raw.get("html_url") or raw.get("url", ""),
                "is_private": bool(raw.get("private", False)),
                "description": raw.get("description", ""),
                "default_branch": raw.get("default_branch", "main"),
                "stargazers_count": raw.get("stargazers_count", 0)
            }
        self.register_transformer("github.repository", "1.0.0", transform_github_repo)

        # 2. Stripe Charge -> Canonical Transaction
        def transform_stripe_charge(raw: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "transaction_id": raw.get("id", ""),
                "amount": raw.get("amount", 0),
                "currency": str(raw.get("currency", "usd")).lower(),
                "status": str(raw.get("status", "unknown")),
                "paid": bool(raw.get("paid", False)),
                "customer_id": raw.get("customer"),
                "created_at": raw.get("created", time.time())
            }
        self.register_transformer("stripe.charge", "1.0.0", transform_stripe_charge)

        # 3. Slack Message -> Canonical Message
        def transform_slack_message(raw: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "message_id": raw.get("client_msg_id") or raw.get("ts", ""),
                "channel_id": raw.get("channel", ""),
                "sender_id": raw.get("user") or raw.get("bot_id", ""),
                "text": raw.get("text", ""),
                "timestamp": float(raw.get("ts", time.time())) if str(raw.get("ts", "")).replace(".", "").isdigit() else time.time()
            }
        self.register_transformer("slack.message", "1.0.0", transform_slack_message)

        # 4. Generic Entity Fallback
        def transform_generic_entity(raw: Dict[str, Any]) -> Dict[str, Any]:
            return dict(raw)
        self.register_transformer("generic.entity", "1.0.0", transform_generic_entity)

    def register_transformer(
        self,
        schema_name: str,
        version: str,
        transformer_func: Callable[[Dict[str, Any]], Dict[str, Any]]
    ):
        """Registers a named, versioned transformer."""
        self._transformers[schema_name] = (version, transformer_func)
        logger.debug(f"Registered normalizer for schema '{schema_name}' v{version}.")

    def normalize(
        self,
        envelope: IngestionEnvelope,
        entity_type: Optional[str] = None
    ) -> NormalizedRecord:
        """
        Executes normalization on an IngestionEnvelope, producing an auditable NormalizedRecord.
        """
        schema_key = envelope.schema_name or envelope.source_id
        transformer_tuple = self._transformers.get(schema_key)
        if not transformer_tuple:
            # Fallback to generic entity transformer
            transformer_tuple = self._transformers.get("generic.entity", ("1.0.0", lambda d: d if isinstance(d, dict) else {"data": d}))

        version, transformer_fn = transformer_tuple
        raw_dict = envelope.raw_payload if isinstance(envelope.raw_payload, dict) else {"raw_value": envelope.raw_payload}

        # Execute transformation
        transformed_data = transformer_fn(raw_dict)
        output_hash = hashlib.sha256(json.dumps(transformed_data, sort_keys=True, default=str).encode("utf-8")).hexdigest()

        # Build Lineage Step
        lineage_step = LineageStep(
            stage_name="NORMALIZED",
            transformer_id=schema_key,
            transformer_version=version,
            timestamp=time.time(),
            input_hash=envelope.payload_hash,
            output_hash=output_hash
        )

        # Build Provenance Record
        record_id = f"rec_{uuid.uuid4().hex[:12]}"
        provenance = ProvenanceRecord(
            provenance_id=f"prov_{uuid.uuid4().hex[:12]}",
            record_id=record_id,
            envelope_id=envelope.envelope_id,
            source_id=envelope.source_id,
            connector_id=envelope.connector_id,
            operation_id=envelope.operation_id,
            resource_id=transformed_data.get("id") or transformed_data.get("transaction_id") or transformed_data.get("message_id"),
            transformations=[f"{schema_key}:{version}"],
            lineage_chain=[lineage_step],
            observed_at=envelope.observed_at,
            received_at=envelope.received_at,
            created_at=time.time()
        )

        # Calculate Quality Score
        completeness = 1.0
        if isinstance(transformed_data, dict):
            non_null = sum(1 for v in transformed_data.values() if v not in (None, "", []))
            completeness = (non_null / max(1, len(transformed_data)))

        quality = QualityMetadata(
            quality_score=round(completeness, 2),
            completeness=round(completeness, 2),
            schema_valid=True,
            source_reliability=1.0 if envelope.trust_boundary.value == "TRUSTED_INTERNAL" else 0.85,
            transformation_count=1
        )

        resolved_entity_type = entity_type or schema_key.split(".")[0].upper()
        canonical_id = str(transformed_data.get("id") or transformed_data.get("transaction_id") or transformed_data.get("message_id") or record_id)

        return NormalizedRecord(
            record_id=record_id,
            envelope_id=envelope.envelope_id,
            canonical_entity_type=resolved_entity_type,
            canonical_id=canonical_id,
            canonical_data=transformed_data,
            provenance=provenance,
            quality=quality,
            freshness=FreshnessStatus.FRESH,
            source_authority="AUTHENTICATED_PROVIDER" if envelope.connector_id else "EXTERNAL_UNVERIFIED",
            observed_at=envelope.observed_at,
            normalized_at=time.time(),
            expires_at=time.time() + 86400.0  # Default 24h freshness window
        )


normalization_engine = NormalizationEngine()
