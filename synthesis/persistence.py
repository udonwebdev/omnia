"""
OMNIA Module 36: Autonomous Knowledge Synthesis & Intelligence Briefing Persistence
Provides durable SQLite storage for intelligence products, briefing versions,
synthesized claims, tracked contradictions, developments, and delivery audits.
"""

import sqlite3
import json
import time
import logging
from typing import Dict, Any, List, Optional
from synthesis.models import (
    IntelligenceProductRecord,
    ProductType,
    AudienceLevel,
    ProductLifecycleState,
    SynthesizedClaim,
    EpistemicClaimType,
    ContradictionRecord,
    ContradictionStatus,
    DevelopmentRecord,
    ChangeType,
    SignificanceAssessment,
    BriefingVersion,
    DeliveryRecord,
    DeliveryStatus,
)

logger = logging.getLogger("Omnia.Synthesis.Persistence")


class SynthesisRepository:
    """Manages relational SQLite persistence for intelligence products and briefings."""

    def __init__(self, db_path: str = "omnia.db"):
        self.db_path = db_path
        self._ensure_schema()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            CREATE TABLE IF NOT EXISTS intelligence_products (
                product_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                purpose TEXT NOT NULL,
                product_type TEXT NOT NULL,
                domain TEXT NOT NULL,
                intended_audience TEXT NOT NULL,
                authorized_scope TEXT NOT NULL,
                required_sources TEXT NOT NULL,
                update_cadence TEXT NOT NULL,
                max_length_words INTEGER DEFAULT 1500,
                freshness_window_sec REAL DEFAULT 86400.0,
                retention_days INTEGER DEFAULT 90,
                approval_required INTEGER DEFAULT 0,
                version INTEGER DEFAULT 1,
                state TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS intelligence_briefing_versions (
                version_id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL,
                version_number INTEGER NOT NULL,
                title TEXT NOT NULL,
                audience_level TEXT NOT NULL,
                executive_summary TEXT NOT NULL,
                rendered_content_markdown TEXT NOT NULL,
                content_digest_sha256 TEXT NOT NULL,
                evidence_sources_count INTEGER NOT NULL,
                claims_count INTEGER NOT NULL,
                quality_score TEXT NOT NULL,
                approval_token TEXT,
                is_stale INTEGER DEFAULT 0,
                generated_at REAL NOT NULL,
                FOREIGN KEY (product_id) REFERENCES intelligence_products(product_id)
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS intelligence_claims (
                claim_id TEXT PRIMARY KEY,
                briefing_version_id TEXT NOT NULL,
                claim_text TEXT NOT NULL,
                claim_type TEXT NOT NULL,
                supporting_evidence_refs TEXT NOT NULL,
                contradictory_evidence_refs TEXT NOT NULL,
                confidence_assessment TEXT NOT NULL,
                confidence_score REAL NOT NULL,
                temporal_scope TEXT NOT NULL,
                known_assumptions TEXT NOT NULL,
                limitations TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (briefing_version_id) REFERENCES intelligence_briefing_versions(version_id)
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS intelligence_contradictions (
                contradiction_id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL,
                claim_a TEXT NOT NULL,
                claim_b TEXT NOT NULL,
                source_a_ref TEXT NOT NULL,
                source_b_ref TEXT NOT NULL,
                divergence_reason TEXT NOT NULL,
                status TEXT NOT NULL,
                resolution_evidence_needed TEXT,
                created_at REAL NOT NULL,
                FOREIGN KEY (product_id) REFERENCES intelligence_products(product_id)
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS intelligence_developments (
                development_id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL,
                change_type TEXT NOT NULL,
                summary TEXT NOT NULL,
                previous_state TEXT,
                new_state TEXT,
                source_refs TEXT NOT NULL,
                significance_score REAL NOT NULL,
                detected_at REAL NOT NULL,
                FOREIGN KEY (product_id) REFERENCES intelligence_products(product_id)
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS intelligence_deliveries (
                delivery_id TEXT PRIMARY KEY,
                briefing_version_id TEXT NOT NULL,
                recipient_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                status TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                error_message TEXT,
                delivered_at REAL,
                created_at REAL NOT NULL,
                FOREIGN KEY (briefing_version_id) REFERENCES intelligence_briefing_versions(version_id)
            );
            """)
            conn.commit()

    # Product Operations
    def save_product(self, product: IntelligenceProductRecord) -> None:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT OR REPLACE INTO intelligence_products (
                product_id, name, purpose, product_type, domain, intended_audience,
                authorized_scope, required_sources, update_cadence, max_length_words,
                freshness_window_sec, retention_days, approval_required, version,
                state, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                product.product_id, product.name, product.purpose, product.product_type.value,
                product.domain, product.intended_audience.value, product.authorized_scope,
                json.dumps(product.required_sources), product.update_cadence, product.max_length_words,
                product.freshness_window_sec, product.retention_days, 1 if product.approval_required else 0,
                product.version, product.state.value, product.created_at, product.updated_at
            ))
            conn.commit()

    def get_product(self, product_id: str) -> Optional[IntelligenceProductRecord]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM intelligence_products WHERE product_id = ?", (product_id,))
            row = cur.fetchone()
            if not row:
                return None
            return IntelligenceProductRecord(
                product_id=row["product_id"],
                name=row["name"],
                purpose=row["purpose"],
                product_type=ProductType(row["product_type"]),
                domain=row["domain"],
                intended_audience=AudienceLevel(row["intended_audience"]),
                authorized_scope=row["authorized_scope"],
                required_sources=json.loads(row["required_sources"]),
                update_cadence=row["update_cadence"],
                max_length_words=row["max_length_words"],
                freshness_window_sec=row["freshness_window_sec"],
                retention_days=row["retention_days"],
                approval_required=bool(row["approval_required"]),
                version=row["version"],
                state=ProductLifecycleState(row["state"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def list_products(self, state: Optional[ProductLifecycleState] = None) -> List[IntelligenceProductRecord]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            if state:
                cur.execute("SELECT * FROM intelligence_products WHERE state = ?", (state.value,))
            else:
                cur.execute("SELECT * FROM intelligence_products")
            results = []
            for row in cur.fetchall():
                results.append(IntelligenceProductRecord(
                    product_id=row["product_id"],
                    name=row["name"],
                    purpose=row["purpose"],
                    product_type=ProductType(row["product_type"]),
                    domain=row["domain"],
                    intended_audience=AudienceLevel(row["intended_audience"]),
                    authorized_scope=row["authorized_scope"],
                    required_sources=json.loads(row["required_sources"]),
                    update_cadence=row["update_cadence"],
                    max_length_words=row["max_length_words"],
                    freshness_window_sec=row["freshness_window_sec"],
                    retention_days=row["retention_days"],
                    approval_required=bool(row["approval_required"]),
                    version=row["version"],
                    state=ProductLifecycleState(row["state"]),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                ))
            return results

    # Briefing Versions
    def save_briefing_version(self, version: BriefingVersion) -> None:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT OR REPLACE INTO intelligence_briefing_versions (
                version_id, product_id, version_number, title, audience_level,
                executive_summary, rendered_content_markdown, content_digest_sha256,
                evidence_sources_count, claims_count, quality_score, approval_token,
                is_stale, generated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                version.version_id, version.product_id, version.version_number,
                version.title, version.audience_level.value, version.executive_summary,
                version.rendered_content_markdown, version.content_digest_sha256,
                version.evidence_sources_count, version.claims_count,
                json.dumps(version.quality_score), version.approval_token,
                1 if version.is_stale else 0, version.generated_at
            ))
            conn.commit()

    def get_briefing_version(self, version_id: str) -> Optional[BriefingVersion]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM intelligence_briefing_versions WHERE version_id = ?", (version_id,))
            row = cur.fetchone()
            if not row:
                return None
            return BriefingVersion(
                version_id=row["version_id"],
                product_id=row["product_id"],
                version_number=row["version_number"],
                title=row["title"],
                audience_level=AudienceLevel(row["audience_level"]),
                executive_summary=row["executive_summary"],
                rendered_content_markdown=row["rendered_content_markdown"],
                content_digest_sha256=row["content_digest_sha256"],
                evidence_sources_count=row["evidence_sources_count"],
                claims_count=row["claims_count"],
                quality_score=json.loads(row["quality_score"]),
                approval_token=row["approval_token"],
                is_stale=bool(row["is_stale"]),
                generated_at=row["generated_at"],
            )

    def get_latest_briefing_version(self, product_id: str) -> Optional[BriefingVersion]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT * FROM intelligence_briefing_versions 
            WHERE product_id = ? ORDER BY version_number DESC LIMIT 1
            """, (product_id,))
            row = cur.fetchone()
            if not row:
                return None
            return BriefingVersion(
                version_id=row["version_id"],
                product_id=row["product_id"],
                version_number=row["version_number"],
                title=row["title"],
                audience_level=AudienceLevel(row["audience_level"]),
                executive_summary=row["executive_summary"],
                rendered_content_markdown=row["rendered_content_markdown"],
                content_digest_sha256=row["content_digest_sha256"],
                evidence_sources_count=row["evidence_sources_count"],
                claims_count=row["claims_count"],
                quality_score=json.loads(row["quality_score"]),
                approval_token=row["approval_token"],
                is_stale=bool(row["is_stale"]),
                generated_at=row["generated_at"],
            )

    # Claims Operations
    def save_claim(self, claim: SynthesizedClaim) -> None:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT OR REPLACE INTO intelligence_claims (
                claim_id, briefing_version_id, claim_text, claim_type,
                supporting_evidence_refs, contradictory_evidence_refs,
                confidence_assessment, confidence_score, temporal_scope,
                known_assumptions, limitations, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                claim.claim_id, claim.briefing_version_id, claim.claim_text, claim.claim_type.value,
                json.dumps(claim.supporting_evidence_refs), json.dumps(claim.contradictory_evidence_refs),
                claim.confidence_assessment, claim.confidence_score, claim.temporal_scope,
                json.dumps(claim.known_assumptions), json.dumps(claim.limitations), claim.created_at
            ))
            conn.commit()

    def list_claims_for_version(self, version_id: str) -> List[SynthesizedClaim]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM intelligence_claims WHERE briefing_version_id = ?", (version_id,))
            results = []
            for row in cur.fetchall():
                results.append(SynthesizedClaim(
                    claim_id=row["claim_id"],
                    briefing_version_id=row["briefing_version_id"],
                    claim_text=row["claim_text"],
                    claim_type=EpistemicClaimType(row["claim_type"]),
                    supporting_evidence_refs=json.loads(row["supporting_evidence_refs"]),
                    contradictory_evidence_refs=json.loads(row["contradictory_evidence_refs"]),
                    confidence_assessment=row["confidence_assessment"],
                    confidence_score=row["confidence_score"],
                    temporal_scope=row["temporal_scope"],
                    known_assumptions=json.loads(row["known_assumptions"]),
                    limitations=json.loads(row["limitations"]),
                    created_at=row["created_at"],
                ))
            return results

    # Contradiction Operations
    def save_contradiction(self, contra: ContradictionRecord) -> None:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT OR REPLACE INTO intelligence_contradictions (
                contradiction_id, product_id, claim_a, claim_b, source_a_ref,
                source_b_ref, divergence_reason, status, resolution_evidence_needed, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                contra.contradiction_id, contra.product_id, contra.claim_a, contra.claim_b,
                contra.source_a_ref, contra.source_b_ref, contra.divergence_reason,
                contra.status.value, contra.resolution_evidence_needed, contra.created_at
            ))
            conn.commit()

    def list_contradictions(self, product_id: str) -> List[ContradictionRecord]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM intelligence_contradictions WHERE product_id = ?", (product_id,))
            results = []
            for row in cur.fetchall():
                results.append(ContradictionRecord(
                    contradiction_id=row["contradiction_id"],
                    product_id=row["product_id"],
                    claim_a=row["claim_a"],
                    claim_b=row["claim_b"],
                    source_a_ref=row["source_a_ref"],
                    source_b_ref=row["source_b_ref"],
                    divergence_reason=row["divergence_reason"],
                    status=ContradictionStatus(row["status"]),
                    resolution_evidence_needed=row["resolution_evidence_needed"],
                    created_at=row["created_at"],
                ))
            return results

    # Development Operations
    def save_development(self, dev: DevelopmentRecord) -> None:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT OR REPLACE INTO intelligence_developments (
                development_id, product_id, change_type, summary, previous_state,
                new_state, source_refs, significance_score, detected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                dev.development_id, dev.product_id, dev.change_type.value, dev.summary,
                dev.previous_state, dev.new_state, json.dumps(dev.source_refs),
                dev.significance_score, dev.detected_at
            ))
            conn.commit()

    def list_developments(self, product_id: str) -> List[DevelopmentRecord]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM intelligence_developments WHERE product_id = ? ORDER BY detected_at DESC", (product_id,))
            results = []
            for row in cur.fetchall():
                results.append(DevelopmentRecord(
                    development_id=row["development_id"],
                    product_id=row["product_id"],
                    change_type=ChangeType(row["change_type"]),
                    summary=row["summary"],
                    previous_state=row["previous_state"],
                    new_state=row["new_state"],
                    source_refs=json.loads(row["source_refs"]),
                    significance_score=row["significance_score"],
                    detected_at=row["detected_at"],
                ))
            return results

    # Delivery Operations
    def save_delivery(self, delivery: DeliveryRecord) -> None:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT OR REPLACE INTO intelligence_deliveries (
                delivery_id, briefing_version_id, recipient_id, channel,
                status, idempotency_key, error_message, delivered_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                delivery.delivery_id, delivery.briefing_version_id, delivery.recipient_id,
                delivery.channel, delivery.status.value, delivery.idempotency_key,
                delivery.error_message, delivery.delivered_at, delivery.created_at
            ))
            conn.commit()

    def get_delivery_by_idempotency(self, idempotency_key: str) -> Optional[DeliveryRecord]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM intelligence_deliveries WHERE idempotency_key = ?", (idempotency_key,))
            row = cur.fetchone()
            if not row:
                return None
            return DeliveryRecord(
                delivery_id=row["delivery_id"],
                briefing_version_id=row["briefing_version_id"],
                recipient_id=row["recipient_id"],
                channel=row["channel"],
                status=DeliveryStatus(row["status"]),
                idempotency_key=row["idempotency_key"],
                error_message=row["error_message"],
                delivered_at=row["delivered_at"],
                created_at=row["created_at"],
            )
