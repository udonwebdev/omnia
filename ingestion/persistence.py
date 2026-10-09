"""
Persistence Repository for Omnia Module 27:
Data Ingestion, Normalization & Knowledge Pipeline

Under Migration Version 9:
- ingestion_envelopes
- ingestion_normalized_records
- ingestion_provenance
- ingestion_conflicts
- ingestion_checkpoints
"""

import sqlite3
import json
import time
import logging
from typing import Dict, Any, List, Optional

from ingestion.models import (
    IngestionEnvelope,
    NormalizedRecord,
    ProvenanceRecord,
    LineageStep,
    QualityMetadata,
    ConflictRecord,
    CheckpointRecord,
    ContentType,
    DataClassification,
    TrustBoundary,
    IngestionStatus,
    FreshnessStatus,
    ConflictResolutionStrategy
)
from persistence.migrations import apply_migrations

logger = logging.getLogger("Omnia.Ingestion.Persistence")


class IngestionPersistence:
    """Manages SQLite persistence for all ingestion pipeline artifacts."""

    def __init__(self, db_path: str = "persistence/omnia_tasks.db"):
        self.db_path = db_path
        apply_migrations(self.db_path)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        return conn

    # --- Envelopes ---
    def save_envelope(self, env: IngestionEnvelope):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO ingestion_envelopes (
                    envelope_id, source_id, source_type, connector_id, connector_instance_id,
                    operation_id, received_at, observed_at, content_type, schema_name,
                    schema_version, payload_reference, payload_hash, payload_size, classification,
                    trust_boundary, correlation_id, causation_id, trace_id, raw_payload_json,
                    status, quarantine_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                env.envelope_id, env.source_id, env.source_type, env.connector_id, env.connector_instance_id,
                env.operation_id, env.received_at, env.observed_at, env.content_type.value, env.schema_name,
                env.schema_version, env.payload_reference, env.payload_hash, env.payload_size, env.classification.value,
                env.trust_boundary.value, env.correlation_id, env.causation_id, env.trace_id,
                json.dumps(env.raw_payload, default=str), env.status.value, env.quarantine_reason, time.time()
            ))

    def get_envelope(self, envelope_id: str) -> Optional[IngestionEnvelope]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM ingestion_envelopes WHERE envelope_id = ?", (envelope_id,)).fetchone()
            if not row:
                return None
            return IngestionEnvelope(
                envelope_id=row["envelope_id"],
                source_id=row["source_id"],
                source_type=row["source_type"],
                connector_id=row["connector_id"],
                connector_instance_id=row["connector_instance_id"],
                operation_id=row["operation_id"],
                received_at=row["received_at"],
                observed_at=row["observed_at"],
                content_type=ContentType(row["content_type"]),
                schema_name=row["schema_name"],
                schema_version=row["schema_version"],
                payload_reference=row["payload_reference"],
                payload_hash=row["payload_hash"],
                payload_size=row["payload_size"],
                classification=DataClassification(row["classification"]),
                trust_boundary=TrustBoundary(row["trust_boundary"]),
                correlation_id=row["correlation_id"],
                causation_id=row["causation_id"],
                trace_id=row["trace_id"],
                raw_payload=json.loads(row["raw_payload_json"]),
                status=IngestionStatus(row["status"]),
                quarantine_reason=row["quarantine_reason"]
            )

    # --- Normalized Records ---
    def save_normalized_record(self, record: NormalizedRecord):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO ingestion_normalized_records (
                    record_id, envelope_id, canonical_entity_type, canonical_id, canonical_data_json,
                    quality_score, quality_metadata_json, freshness_status, source_authority,
                    observed_at, normalized_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.record_id, record.envelope_id, record.canonical_entity_type, record.canonical_id,
                json.dumps(record.canonical_data, default=str), record.quality.quality_score,
                json.dumps(record.quality.attributes, default=str), record.freshness.value,
                record.source_authority, record.observed_at, record.normalized_at, record.expires_at
            ))
            # Save provenance record alongside
            conn.execute("""
                INSERT OR REPLACE INTO ingestion_provenance (
                    provenance_id, record_id, envelope_id, source_id, connector_id,
                    operation_id, resource_id, transformations_json, lineage_chain_json,
                    observed_at, received_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.provenance.provenance_id, record.record_id, record.envelope_id, record.provenance.source_id,
                record.provenance.connector_id, record.provenance.operation_id, record.provenance.resource_id,
                json.dumps(record.provenance.transformations),
                json.dumps([{
                    "stage_name": step.stage_name,
                    "transformer_id": step.transformer_id,
                    "transformer_version": step.transformer_version,
                    "timestamp": step.timestamp,
                    "input_hash": step.input_hash,
                    "output_hash": step.output_hash,
                    "metadata": step.metadata
                } for step in record.provenance.lineage_chain]),
                record.provenance.observed_at, record.provenance.received_at, record.provenance.created_at
            ))

    def get_normalized_record(self, record_id: str) -> Optional[NormalizedRecord]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM ingestion_normalized_records WHERE record_id = ?", (record_id,)).fetchone()
            if not row:
                return None
            prov_row = conn.execute("SELECT * FROM ingestion_provenance WHERE record_id = ?", (record_id,)).fetchone()
            lineage = []
            if prov_row:
                for step_dict in json.loads(prov_row["lineage_chain_json"]):
                    lineage.append(LineageStep(
                        stage_name=step_dict.get("stage_name", "UNKNOWN"),
                        transformer_id=step_dict.get("transformer_id", ""),
                        transformer_version=step_dict.get("transformer_version", ""),
                        timestamp=step_dict.get("timestamp", 0.0),
                        input_hash=step_dict.get("input_hash"),
                        output_hash=step_dict.get("output_hash"),
                        metadata=step_dict.get("metadata", {})
                    ))
                prov = ProvenanceRecord(
                    provenance_id=prov_row["provenance_id"],
                    record_id=record_id,
                    envelope_id=row["envelope_id"],
                    source_id=prov_row["source_id"],
                    connector_id=prov_row["connector_id"],
                    operation_id=prov_row["operation_id"],
                    resource_id=prov_row["resource_id"],
                    transformations=json.loads(prov_row["transformations_json"]),
                    lineage_chain=lineage,
                    observed_at=prov_row["observed_at"],
                    received_at=prov_row["received_at"],
                    created_at=prov_row["created_at"]
                )
            else:
                prov = ProvenanceRecord("p0", record_id, row["envelope_id"], "unknown", None, None, None)

            return NormalizedRecord(
                record_id=row["record_id"],
                envelope_id=row["envelope_id"],
                canonical_entity_type=row["canonical_entity_type"],
                canonical_id=row["canonical_id"],
                canonical_data=json.loads(row["canonical_data_json"]),
                provenance=prov,
                quality=QualityMetadata(quality_score=row["quality_score"]),
                freshness=FreshnessStatus(row["freshness_status"]),
                source_authority=row["source_authority"],
                observed_at=row["observed_at"],
                normalized_at=row["normalized_at"],
                expires_at=row["expires_at"]
            )

    def get_provenance(self, record_id: str) -> Optional[ProvenanceRecord]:
        rec = self.get_normalized_record(record_id)
        return rec.provenance if rec else None

    # --- Conflicts ---
    def save_conflict(self, conf: ConflictRecord):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO ingestion_conflicts (
                    conflict_id, entity_id, field_name, source_a, value_a_json,
                    source_b, value_b_json, detected_at, resolution_strategy,
                    resolution_status, resolved_at, resolved_value_json, resolution_rationale
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                conf.conflict_id, conf.entity_id, conf.field_name, conf.source_a,
                json.dumps(conf.value_a, default=str), conf.source_b, json.dumps(conf.value_b, default=str),
                conf.detected_at, conf.resolution_strategy.value, conf.resolution_status,
                conf.resolved_at, json.dumps(conf.resolved_value, default=str) if conf.resolved_value is not None else None,
                conf.resolution_rationale
            ))

    def get_conflict(self, conflict_id: str) -> Optional[ConflictRecord]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM ingestion_conflicts WHERE conflict_id = ?", (conflict_id,)).fetchone()
            if not row:
                return None
            return ConflictRecord(
                conflict_id=row["conflict_id"],
                entity_id=row["entity_id"],
                field_name=row["field_name"],
                source_a=row["source_a"],
                value_a=json.loads(row["value_a_json"]),
                source_b=row["source_b"],
                value_b=json.loads(row["value_b_json"]),
                detected_at=row["detected_at"],
                resolution_strategy=ConflictResolutionStrategy(row["resolution_strategy"]),
                resolution_status=row["resolution_status"],
                resolved_at=row["resolved_at"],
                resolved_value=json.loads(row["resolved_value_json"]) if row["resolved_value_json"] else None,
                resolution_rationale=row["resolution_rationale"]
            )

    # --- Checkpoints ---
    def save_checkpoint(self, cp: CheckpointRecord):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO ingestion_checkpoints (
                    pipeline_id, source_id, cursor_val, last_envelope_id,
                    processed_count, watermark_ts, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                cp.pipeline_id, cp.source_id, cp.cursor_val, cp.last_envelope_id,
                cp.processed_count, cp.watermark_ts, time.time()
            ))

    def get_checkpoint(self, pipeline_id: str, source_id: str) -> Optional[CheckpointRecord]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM ingestion_checkpoints WHERE pipeline_id = ? AND source_id = ?",
                (pipeline_id, source_id)
            ).fetchone()
            if not row:
                return None
            return CheckpointRecord(
                pipeline_id=row["pipeline_id"],
                source_id=row["source_id"],
                cursor_val=row["cursor_val"],
                last_envelope_id=row["last_envelope_id"],
                processed_count=row["processed_count"],
                watermark_ts=row["watermark_ts"],
                updated_at=row["updated_at"]
            )
