"""
Data Ingestion, Normalization & Knowledge Pipeline Service for Omnia Module 27:
Structured External Data Processing, Validation, Transformation, Provenance & Knowledge Materialization

Guarantees:
1. RAW DATA ≠ NORMALIZED DATA ≠ DERIVED DATA ≠ KNOWLEDGE ≠ MEMORY ≠ TRUTH.
2. Every transformed record preserves an unbroken provenance chain.
3. Secret-bearing and injection-bearing external inputs are actively quarantined or tagged.
4. Backpressure-aware streaming with durable checkpoints and bounded enrichment.
5. Integration with Module 05 (Memory), Module 09 (Policy), Module 17 (Capabilities), Module 18 (Event Fabric), and Module 22 (Distributed Fencing).
"""

import time
import uuid
import hashlib
import json
import logging
from typing import Dict, Any, List, Optional, Tuple

from ingestion.models import (
    DataCategory,
    ContentType,
    SchemaValidationStatus,
    TrustBoundary,
    DataClassification,
    FreshnessStatus,
    DeduplicationStatus,
    IngestionStatus,
    PipelineState,
    ConflictResolutionStrategy,
    IngestionEnvelope,
    NormalizedRecord,
    ProvenanceRecord,
    ConflictRecord,
    CheckpointRecord,
    IngestionTelemetry
)
from ingestion.security import ingestion_security_guard, IngestionSecurityGuard
from ingestion.validation import schema_validator, SchemaValidator
from ingestion.normalization import normalization_engine, NormalizationEngine
from ingestion.deduplication import deduplication_engine, DeduplicationEngine
from ingestion.conflicts import conflict_manager, ConflictManager
from ingestion.enrichment import enrichment_engine, EnrichmentEngine
from ingestion.freshness import freshness_evaluator, FreshnessEvaluator
from ingestion.persistence import IngestionPersistence
from events.models import Event
from events.fabric import event_fabric
from memory_engine import memory

logger = logging.getLogger("Omnia.Ingestion.Service")


class DataIngestionService:
    """Production service coordinating Omnia's knowledge materialization and data ingestion."""

    def __init__(
        self,
        persistence: Optional[IngestionPersistence] = None,
        node_id: str = "local_node",
        security_guard: Optional[IngestionSecurityGuard] = None,
        validator: Optional[SchemaValidator] = None,
        normalizer: Optional[NormalizationEngine] = None,
        dedup_engine: Optional[DeduplicationEngine] = None,
        conflict_mgr: Optional[ConflictManager] = None,
        freshness_eval: Optional[FreshnessEvaluator] = None,
        enricher: Optional[EnrichmentEngine] = None
    ):
        self.node_id = node_id
        self.persistence = persistence or IngestionPersistence()
        self.security_guard = security_guard or ingestion_security_guard
        self.validator = validator or schema_validator
        self.normalizer = normalizer or normalization_engine
        self.deduplicator = dedup_engine or deduplication_engine
        self.conflict_mgr = conflict_mgr or conflict_manager
        self.enricher = enricher or enrichment_engine
        self.freshness_eval = freshness_eval or freshness_evaluator
        self.telemetry = IngestionTelemetry()

        # Wire persistence
        if hasattr(self.conflict_mgr, "persistence"):
            self.conflict_mgr.persistence = self.persistence
        if hasattr(self.deduplicator, "persistence"):
            self.deduplicator.persistence = self.persistence

        # Backpressure queue parameters
        self.max_queue_depth = 1000
        self._current_queue_size = 0
        self.pipeline_state = PipelineState.RUNNING

        # Register capabilities with Module 17
        self._register_capabilities()

    def _register_capabilities(self):
        """Registers Module 27 data processing capabilities with Module 17 CapabilityRegistry."""
        try:
            from capabilities.registry import capability_registry
            from capabilities.models import (
                Capability, CapabilityProvider, CapabilityCategory,
                CapabilityHealth, RiskLevel, SideEffectType, IdempotencyType
            )
            caps = [
                ("data.ingest", "Ingest Raw External Payload", "Wraps, validates, and envelopes external data"),
                ("data.normalize", "Normalize External Entity", "Transforms provider schema into canonical entity"),
                ("data.validate", "Validate Data Schema", "Validates payload types, nullability, and schema compliance"),
                ("data.enrich", "Enrich Normalized Record", "Appends bounded metadata within loop-safe constraints"),
                ("data.detect_conflicts", "Detect Data Discrepancies", "Detects and records field-level contradictions")
            ]
            for cid, name, desc in caps:
                cap = Capability(
                    id=cid,
                    name=name,
                    version="1.0.0",
                    description=desc,
                    category=CapabilityCategory.INGESTION,
                    provider=CapabilityProvider(provider_id="ingestion.service", name="Ingestion Pipeline", version="1.0.0"),
                    health=CapabilityHealth.HEALTHY,
                    risk_level=RiskLevel.LOW,
                    side_effect_type=SideEffectType.READ_ONLY if "detect" in cid or "validate" in cid else SideEffectType.IDEMPOTENT_WRITE,
                    idempotency=IdempotencyType.STRICTLY_IDEMPOTENT
                )
                capability_registry.register_capability(cap)
            logger.info("Registered 5 Data Ingestion capabilities into registry.")
        except Exception as e:
            logger.debug(f"Capability registration bypassed: {e}")

    # --- Core Pipeline Execution ---

    def ingest(
        self,
        source_id: str,
        raw_payload: Any,
        content_type: Optional[ContentType] = None,
        source_type: str = "REST",
        connector_id: Optional[str] = None,
        connector_instance_id: Optional[str] = None,
        operation_id: Optional[str] = None,
        schema_name: Optional[str] = None,
        schema_version: Optional[str] = "1.0.0",
        classification: DataClassification = DataClassification.INTERNAL,
        trust_boundary: TrustBoundary = TrustBoundary.UNTRUSTED_EXTERNAL,
        correlation_id: Optional[str] = None,
        route_to_memory: bool = False
    ) -> Tuple[bool, Optional[NormalizedRecord], Optional[IngestionEnvelope], str]:
        """
        Coordinates full ingestion lifecycle:
        ENVELOPE -> SECURITY -> DEDUPLICATION -> VALIDATION -> NORMALIZATION -> ENRICHMENT -> CONFLICTS -> ROUTING.
        Returns (success, NormalizedRecord, IngestionEnvelope, status_message).
        """
        t0 = time.perf_counter()
        self.telemetry.records_received += 1

        # 1. Backpressure Check
        if self._current_queue_size >= self.max_queue_depth:
            self.telemetry.backpressure_events += 1
            self.pipeline_state = PipelineState.BACKPRESSURED
            logger.warning(f"INGESTION_BACKPRESSURE: Queue depth {self._current_queue_size} exceeds limit {self.max_queue_depth}.")
            return False, None, None, "BACKPRESSURE_REJECTED: Ingestion queue saturated."

        # 2. Content Type Detection
        detected_ct = content_type or self.validator.detect_content_type(raw_payload)

        # 3. Payload Hashing & Size Calculation
        payload_bytes = json.dumps(raw_payload, sort_keys=True, default=str).encode("utf-8") if not isinstance(raw_payload, bytes) else raw_payload
        payload_hash = hashlib.sha256(payload_bytes).hexdigest()
        payload_size = len(payload_bytes)

        # 4. Construct Universal Ingestion Envelope
        envelope_id = f"env_{uuid.uuid4().hex[:12]}"
        envelope = IngestionEnvelope(
            envelope_id=envelope_id,
            source_id=source_id,
            source_type=source_type,
            content_type=detected_ct,
            raw_payload=raw_payload,
            payload_hash=payload_hash,
            payload_size=payload_size,
            connector_id=connector_id,
            connector_instance_id=connector_instance_id,
            operation_id=operation_id,
            schema_name=schema_name,
            schema_version=schema_version,
            classification=classification,
            trust_boundary=trust_boundary,
            correlation_id=correlation_id,
            status=IngestionStatus.INGESTED
        )

        self._emit_event("data.ingestion.started", {
            "envelope_id": envelope_id,
            "source_id": source_id,
            "content_type": detected_ct.value
        })

        # 5. Security & Quarantine Scan (Module 09 + Module 25 + Prompt Injection Defense)
        sec_allowed, quarantine_reason = self.security_guard.evaluate_envelope(envelope)
        if not sec_allowed:
            self.telemetry.records_quarantined += 1
            envelope.status = IngestionStatus.QUARANTINED
            envelope.quarantine_reason = quarantine_reason
            self.persistence.save_envelope(envelope)

            self._emit_event("data.quarantined", {
                "envelope_id": envelope_id,
                "source_id": source_id,
                "reason": quarantine_reason
            })
            return False, None, envelope, f"QUARANTINED: {quarantine_reason}"

        # 6. Deduplication Evaluation
        dedup_status, dedup_msg = self.deduplicator.check_duplicate_envelope(envelope)
        if dedup_status == DeduplicationStatus.EXACT_DUPLICATE:
            self.telemetry.duplicates_detected += 1
            envelope.status = IngestionStatus.ROUTED
            envelope.metadata["duplicate"] = True
            self.persistence.save_envelope(envelope)
            return True, None, envelope, f"DUPLICATE_ACCEPTED: {dedup_msg}"

        # 7. Schema Validation
        val_status, val_errors = self.validator.validate_schema(schema_name, schema_version, raw_payload)
        if val_status == SchemaValidationStatus.INVALID:
            self.telemetry.records_rejected += 1
            envelope.status = IngestionStatus.REJECTED
            self.persistence.save_envelope(envelope)

            self._emit_event("data.rejected", {
                "envelope_id": envelope_id,
                "reason": f"Schema validation failed: {val_errors}"
            })
            return False, None, envelope, f"SCHEMA_INVALID: {val_errors}"

        self.telemetry.records_validated += 1
        envelope.status = IngestionStatus.VALIDATED

        # 8. Normalization & Canonical Mapping
        norm_record = self.normalizer.normalize(envelope)
        self.telemetry.records_normalized += 1

        # 9. Bounded Enrichment
        norm_record = self.enricher.enrich(norm_record)
        self.telemetry.enrichment_operations += 1

        # 10. Conflict Detection
        # Check if an existing record with the same canonical ID exists to detect source disagreements
        existing_record = self.persistence.get_normalized_record(norm_record.record_id)
        if existing_record:
            conflicts = self.conflict_mgr.detect_conflicts(norm_record, existing_record)
            if conflicts:
                self.telemetry.conflicts_detected += 1
                norm_record.quality.has_conflicts = True

        # 11. Persistence
        envelope.status = IngestionStatus.NORMALIZED
        self.persistence.save_envelope(envelope)
        self.persistence.save_normalized_record(norm_record)

        # 12. Routing: Memory Integration (Module 05) & Event Fabric (Module 18)
        if route_to_memory and envelope.classification in (DataClassification.PUBLIC, DataClassification.INTERNAL):
            # Only store in vector memory if not confidential or secret
            try:
                doc_text = f"Source: {source_id}\nType: {norm_record.canonical_entity_type}\nData: {json.dumps(norm_record.canonical_data, default=str)}"
                memory.store_tab_context(
                    tab_id=hash(norm_record.canonical_id) % 100000,
                    url=f"omnia://knowledge/{source_id}/{norm_record.canonical_id}",
                    title=f"Normalized {norm_record.canonical_entity_type}",
                    content=doc_text
                )
                norm_record.routing_targets.append("MODULE_05_MEMORY")
            except Exception as e:
                logger.warning(f"Memory indexing failed: {e}")

        self._emit_event("data.normalized", {
            "record_id": norm_record.record_id,
            "canonical_entity_type": norm_record.canonical_entity_type,
            "canonical_id": norm_record.canonical_id
        })

        latency_ms = (time.perf_counter() - t0) * 1000.0
        self.telemetry.pipeline_latency_ms_total += latency_ms

        self._emit_event("data.ingestion.completed", {
            "envelope_id": envelope_id,
            "source_id": source_id,
            "records_count": 1
        })

        return True, norm_record, envelope, "INGESTION_COMPLETED"

    # --- Checkpoint Management ---

    def create_checkpoint(self, pipeline_id: str, source_id: str, cursor: str, last_envelope_id: Optional[str], count: int) -> CheckpointRecord:
        """Saves a durable watermark checkpoint for resumable pipelines."""
        cp = CheckpointRecord(
            pipeline_id=pipeline_id,
            source_id=source_id,
            cursor_val=cursor,
            last_envelope_id=last_envelope_id,
            processed_count=count,
            watermark_ts=time.time()
        )
        self.persistence.save_checkpoint(cp)
        logger.info(f"Checkpoint saved for pipeline '{pipeline_id}', source '{source_id}' at cursor '{cursor}'.")
        return cp

    def recover_pipeline(self, pipeline_id: str, source_id: str) -> Optional[CheckpointRecord]:
        """Loads the most recent durable checkpoint for crash recovery."""
        cp = self.persistence.get_checkpoint(pipeline_id, source_id)
        if cp:
            logger.info(f"Recovered pipeline '{pipeline_id}' at cursor '{cp.cursor_val}', processed {cp.processed_count} items.")
            self.pipeline_state = PipelineState.RUNNING
        return cp

    # --- Public Query APIs ---

    def get_provenance(self, record_id: str) -> Optional[ProvenanceRecord]:
        rec = self.persistence.get_normalized_record(record_id)
        return rec.provenance if rec else None

    def get_record(self, record_id: str) -> Optional[NormalizedRecord]:
        return self.persistence.get_normalized_record(record_id)

    def get_telemetry(self) -> IngestionTelemetry:
        return self.telemetry

    def list_conflicts(self, status: str = "OPEN") -> List[ConflictRecord]:
        return self.persistence.list_conflicts(status=status)

    def resolve_conflict(self, conflict_id: str, strategy: ConflictResolutionStrategy, winning_value: Any = None) -> Optional[ConflictRecord]:
        ok, val, msg = self.conflict_mgr.resolve_conflict(
            conflict_id=conflict_id,
            strategy=strategy,
            manual_override_value=winning_value
        )
        return self.persistence.get_conflict(conflict_id) if ok else None

    def _emit_event(self, event_type: str, payload: Dict[str, Any]):
        """Publishes typed metadata events to Event Fabric safely."""
        try:
            import asyncio
            from events.models import EventEnvelope
            evt = Event(
                envelope=EventEnvelope(
                    event_type=event_type,
                    source=f"ingestion.service.{self.node_id}"
                ),
                payload=payload
            )
            async def _pub():
                await event_fabric.publish(evt)
                await event_fabric._dispatch_lanes()

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(_pub())
                else:
                    loop.run_until_complete(_pub())
            except RuntimeError:
                asyncio.run(_pub())
        except Exception as e:
            logger.debug(f"Event publish ignored: {e}")


data_ingestion_service = DataIngestionService()
