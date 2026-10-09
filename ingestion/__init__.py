"""
Omnia Module 27: Data Ingestion, Normalization & Knowledge Pipeline Package
"""

from ingestion.models import (
    DataCategory,
    ContentType,
    SchemaValidationStatus,
    TrustBoundary,
    DataClassification,
    FreshnessStatus,
    DeduplicationStatus,
    IdentityConfidence,
    IngestionStatus,
    PipelineState,
    ConflictResolutionStrategy,
    IngestionEnvelope,
    NormalizedRecord,
    ProvenanceRecord,
    LineageStep,
    QualityMetadata,
    ConflictRecord,
    CheckpointRecord,
    IngestionTelemetry
)
from ingestion.security import (
    IngestionSecurityGuard,
    ingestion_security_guard
)
from ingestion.validation import (
    SchemaValidator,
    schema_validator
)
from ingestion.normalization import (
    NormalizationEngine,
    normalization_engine
)
from ingestion.deduplication import (
    DeduplicationEngine,
    deduplication_engine
)
from ingestion.conflicts import (
    ConflictManager,
    conflict_manager
)
from ingestion.enrichment import (
    EnrichmentEngine,
    enrichment_engine,
    EnrichmentLoopError
)
from ingestion.freshness import (
    FreshnessEvaluator,
    freshness_evaluator
)
from ingestion.persistence import IngestionPersistence
from ingestion.service import (
    DataIngestionService,
    data_ingestion_service
)

__all__ = [
    "DataCategory",
    "ContentType",
    "SchemaValidationStatus",
    "TrustBoundary",
    "DataClassification",
    "FreshnessStatus",
    "DeduplicationStatus",
    "IdentityConfidence",
    "IngestionStatus",
    "PipelineState",
    "ConflictResolutionStrategy",
    "IngestionEnvelope",
    "NormalizedRecord",
    "ProvenanceRecord",
    "LineageStep",
    "QualityMetadata",
    "ConflictRecord",
    "CheckpointRecord",
    "IngestionTelemetry",
    "IngestionSecurityGuard",
    "ingestion_security_guard",
    "SchemaValidator",
    "schema_validator",
    "NormalizationEngine",
    "normalization_engine",
    "DeduplicationEngine",
    "deduplication_engine",
    "ConflictManager",
    "conflict_manager",
    "EnrichmentEngine",
    "enrichment_engine",
    "EnrichmentLoopError",
    "FreshnessEvaluator",
    "freshness_evaluator",
    "IngestionPersistence",
    "DataIngestionService",
    "data_ingestion_service"
]
