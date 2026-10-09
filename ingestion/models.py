"""
Core Data Models & Invariants for Omnia Module 27:
Data Ingestion, Normalization & Knowledge Pipeline

Guarantees:
1. Raw external data is never automatically trusted as fact or system instruction.
2. Every materialized record preserves an unbroken provenance chain (source, connector, operation, observed_at, received_at).
3. Secret-bearing material is strictly detected, quarantined, or redacted.
4. Prompt injections embedded in documents or payloads are quarantined or preserved strictly as untrusted content.
5. Ingestion pipeline handles backpressure, checkpoints, deduplication, conflict preservation, and bounded enrichment.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set, Union
import time
import uuid


class DataCategory(str, Enum):
    DOCUMENT = "DOCUMENT"
    RECORD = "RECORD"
    EVENT = "EVENT"
    ENTITY = "ENTITY"
    OBSERVATION = "OBSERVATION"
    MEASUREMENT = "MEASUREMENT"
    MESSAGE = "MESSAGE"
    TRANSACTION = "TRANSACTION"
    MEDIA = "MEDIA"
    STRUCTURED_DATA = "STRUCTURED_DATA"
    UNSTRUCTURED_DATA = "UNSTRUCTURED_DATA"
    LOG = "LOG"
    TELEMETRY = "TELEMETRY"


class ContentType(str, Enum):
    APPLICATION_JSON = "application/json"
    APPLICATION_XML = "application/xml"
    TEXT_PLAIN = "text/plain"
    TEXT_CSV = "text/csv"
    TEXT_HTML = "text/html"
    APPLICATION_PDF = "application/pdf"
    IMAGE = "image/*"
    AUDIO = "audio/*"
    VIDEO = "video/*"
    UNKNOWN = "application/octet-stream"


class SchemaValidationStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    PARTIALLY_VALID = "PARTIALLY_VALID"
    UNSUPPORTED_SCHEMA = "UNSUPPORTED_SCHEMA"
    UNKNOWN_SCHEMA = "UNKNOWN_SCHEMA"


class TrustBoundary(str, Enum):
    TRUSTED_INTERNAL = "TRUSTED_INTERNAL"
    AUTHENTICATED_EXTERNAL = "AUTHENTICATED_EXTERNAL"
    UNTRUSTED_EXTERNAL = "UNTRUSTED_EXTERNAL"
    USER_PROVIDED = "USER_PROVIDED"
    UNKNOWN = "UNKNOWN"


class DataClassification(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    SENSITIVE = "SENSITIVE"
    SECRET = "SECRET"


class FreshnessStatus(str, Enum):
    FRESH = "FRESH"
    AGING = "AGING"
    STALE = "STALE"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class DeduplicationStatus(str, Enum):
    NOT_DUPLICATE = "NOT_DUPLICATE"
    EXACT_DUPLICATE = "EXACT_DUPLICATE"
    LIKELY_DUPLICATE = "LIKELY_DUPLICATE"
    UNKNOWN = "UNKNOWN"


class IdentityConfidence(str, Enum):
    EXACT = "EXACT"
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
    POSSIBLE = "POSSIBLE"
    AMBIGUOUS = "AMBIGUOUS"
    UNKNOWN = "UNKNOWN"


class IngestionStatus(str, Enum):
    INGESTED = "INGESTED"
    VALIDATED = "VALIDATED"
    NORMALIZED = "NORMALIZED"
    ENRICHED = "ENRICHED"
    ROUTED = "ROUTED"
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class PipelineState(str, Enum):
    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    BACKPRESSURED = "BACKPRESSURED"
    DEGRADED = "DEGRADED"
    RECOVERING = "RECOVERING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ConflictResolutionStrategy(str, Enum):
    PRESERVE_CONFLICT = "PRESERVE_CONFLICT"
    AUTHORITATIVE_SOURCE_WINS = "AUTHORITATIVE_SOURCE_WINS"
    LATEST_VERIFIED = "LATEST_VERIFIED"
    MERGE = "MERGE"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    RECONSTRUCT = "RECONSTRUCT"


# --- Envelopes & Raw Data Wrappers ---

@dataclass
class IngestionEnvelope:
    """Universal typed envelope wrapping raw external information upon receipt."""
    envelope_id: str
    source_id: str  # e.g., "external.github.repository", "external.stripe.charges"
    source_type: str  # "REST", "WEBHOOK", "DEVICE", "BROWSER", "DOCUMENT"
    content_type: ContentType
    raw_payload: Any
    payload_hash: str
    payload_size: int
    received_at: float = field(default_factory=time.time)
    observed_at: float = field(default_factory=time.time)
    connector_id: Optional[str] = None
    connector_instance_id: Optional[str] = None
    operation_id: Optional[str] = None
    schema_name: Optional[str] = None
    schema_version: Optional[str] = None
    payload_reference: Optional[str] = None
    classification: DataClassification = DataClassification.INTERNAL
    trust_boundary: TrustBoundary = TrustBoundary.UNTRUSTED_EXTERNAL
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    trace_id: Optional[str] = None
    security_context: Dict[str, Any] = field(default_factory=dict)
    status: IngestionStatus = IngestionStatus.INGESTED
    quarantine_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# --- Provenance & Lineage ---

@dataclass
class LineageStep:
    """Individual atomic stage of processing recorded for full transformation audibility."""
    stage_name: str  # e.g., "RAW", "PARSED", "NORMALIZED", "ENRICHED", "INDEXED"
    transformer_id: str
    transformer_version: str
    timestamp: float = field(default_factory=time.time)
    input_hash: Optional[str] = None
    output_hash: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProvenanceRecord:
    """Unbroken provenance certificate attached to every normalized or derived entity."""
    provenance_id: str
    record_id: str
    envelope_id: str
    source_id: str
    connector_id: Optional[str]
    operation_id: Optional[str]
    resource_id: Optional[str]
    transformations: List[str] = field(default_factory=list)
    lineage_chain: List[LineageStep] = field(default_factory=list)
    observed_at: float = field(default_factory=time.time)
    received_at: float = field(default_factory=time.time)
    created_at: float = field(default_factory=time.time)


# --- Quality Metadata ---

@dataclass
class QualityMetadata:
    """Objective, non-manufactured indicators of data quality and reliability."""
    quality_score: float = 1.0  # 0.0 to 1.0
    completeness: float = 1.0
    schema_valid: bool = True
    source_reliability: float = 1.0
    transformation_count: int = 0
    verification_status: str = "UNVERIFIED"
    has_conflicts: bool = False
    attributes: Dict[str, Any] = field(default_factory=dict)


# --- Canonical Entity Models ---

@dataclass
class CanonicalEntity:
    """Base class for unified Omnia cross-subsystem entities."""
    entity_id: str
    entity_type: str
    canonical_data: Dict[str, Any]
    source_references: List[str] = field(default_factory=list)
    identity_confidence: IdentityConfidence = IdentityConfidence.EXACT


@dataclass
class NormalizedRecord:
    """Validated, normalized, provenance-backed record produced by Module 27."""
    record_id: str
    envelope_id: str
    canonical_entity_type: str
    canonical_id: str
    canonical_data: Dict[str, Any]
    provenance: ProvenanceRecord
    quality: QualityMetadata = field(default_factory=QualityMetadata)
    freshness: FreshnessStatus = FreshnessStatus.FRESH
    source_authority: str = "EXTERNAL_UNVERIFIED"
    observed_at: float = field(default_factory=time.time)
    normalized_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    untrusted_content_tags: List[str] = field(default_factory=list)
    routing_targets: List[str] = field(default_factory=list)


# --- Conflict & Checkpoint Models ---

@dataclass
class ConflictRecord:
    """Explicit, unsuppressed disagreement between multiple sources regarding an entity."""
    conflict_id: str
    entity_id: str
    field_name: str
    source_a: str
    value_a: Any
    source_b: str
    value_b: Any
    detected_at: float = field(default_factory=time.time)
    resolution_strategy: ConflictResolutionStrategy = ConflictResolutionStrategy.PRESERVE_CONFLICT
    resolution_status: str = "UNRESOLVED"
    resolved_at: Optional[float] = None
    resolved_value: Optional[Any] = None
    resolution_rationale: Optional[str] = None


@dataclass
class CheckpointRecord:
    """Resumable position marker for streaming and batch pipelines."""
    pipeline_id: str
    source_id: str
    cursor_val: str
    last_envelope_id: Optional[str]
    processed_count: int
    watermark_ts: float
    updated_at: float = field(default_factory=time.time)


@dataclass
class IngestionTelemetry:
    """Operational telemetry counters for Module 27."""
    records_received: int = 0
    records_validated: int = 0
    records_rejected: int = 0
    records_normalized: int = 0
    records_quarantined: int = 0
    duplicates_detected: int = 0
    conflicts_detected: int = 0
    transformations_executed: int = 0
    enrichment_operations: int = 0
    backpressure_events: int = 0
    pipeline_latency_ms_total: float = 0.0
