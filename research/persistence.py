"""
OMNIA Module 35: SQLite Persistence Repository for Autonomous Research & Discovery
Stores research requests, plans, knowledge gaps, hypotheses, experiments, tests,
conclusions, reproducibility manifests, and reports.
"""

import sqlite3
import json
import logging
from typing import Dict, Any, List, Optional
from research.models import (
    ResearchRequest,
    ResearchState,
    KnowledgeGapRecord,
    HypothesisRecord,
    HypothesisType,
    HypothesisState,
    ExperimentDefinition,
    ExperimentType,
    ExperimentExecutionResult,
    HypothesisTestResult,
    ResearchConclusion,
    ConclusionState,
    ReproducibilityManifest,
)

logger = logging.getLogger("Omnia.Research.Persistence")


class ResearchRepository:
    """Manages persistent SQLite operations for the autonomous scientific discovery engine."""

    def __init__(self, db_path: str = "omnia.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Ensures Schema Version 20 tables are initialized."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS research_requests (
                research_id TEXT PRIMARY KEY,
                original_question TEXT NOT NULL,
                normalized_objective TEXT NOT NULL,
                domain TEXT NOT NULL,
                scope TEXT NOT NULL,
                state TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                requires_approval INTEGER NOT NULL,
                created_by TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS research_knowledge_gaps (
                gap_id TEXT PRIMARY KEY,
                research_id TEXT NOT NULL,
                description TEXT NOT NULL,
                why_it_matters TEXT NOT NULL,
                evidence_required TEXT NOT NULL,
                possible_acquisition_method TEXT NOT NULL,
                priority TEXT NOT NULL,
                resolution_status TEXT NOT NULL
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS research_hypotheses (
                hypothesis_id TEXT PRIMARY KEY,
                research_id TEXT NOT NULL,
                statement TEXT NOT NULL,
                hypothesis_type TEXT NOT NULL,
                scope TEXT NOT NULL,
                assumptions TEXT NOT NULL,
                supporting_evidence TEXT NOT NULL,
                contradictory_evidence TEXT NOT NULL,
                expected_observations TEXT NOT NULL,
                falsification_conditions TEXT NOT NULL,
                state TEXT NOT NULL,
                confidence_score REAL NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS research_experiments (
                experiment_id TEXT PRIMARY KEY,
                research_id TEXT NOT NULL,
                hypothesis_id TEXT NOT NULL,
                title TEXT NOT NULL,
                objective TEXT NOT NULL,
                experiment_type TEXT NOT NULL,
                independent_variables TEXT NOT NULL,
                dependent_variables TEXT NOT NULL,
                controlled_variables TEXT NOT NULL,
                sampling_strategy TEXT NOT NULL,
                sample_size INTEGER NOT NULL,
                baseline_condition TEXT NOT NULL,
                treatment_condition TEXT NOT NULL,
                measurement_protocol TEXT NOT NULL,
                stopping_conditions TEXT NOT NULL,
                success_criteria TEXT NOT NULL,
                failure_criteria TEXT NOT NULL,
                requires_approval INTEGER NOT NULL,
                approval_token TEXT,
                isolation_environment TEXT NOT NULL,
                status TEXT NOT NULL
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS research_hypothesis_tests (
                test_id TEXT PRIMARY KEY,
                hypothesis_id TEXT NOT NULL,
                method TEXT NOT NULL,
                sample_size INTEGER NOT NULL,
                test_statistic REAL,
                p_value REAL,
                effect_size REAL NOT NULL,
                confidence_interval TEXT,
                evaluated_state TEXT NOT NULL,
                reasoning TEXT NOT NULL,
                limitations TEXT NOT NULL,
                tested_at REAL NOT NULL
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS research_conclusions (
                conclusion_id TEXT PRIMARY KEY,
                research_id TEXT NOT NULL,
                state TEXT NOT NULL,
                summary TEXT NOT NULL,
                direct_observations TEXT NOT NULL,
                supported_claims TEXT NOT NULL,
                rejected_hypotheses TEXT NOT NULL,
                unresolved_uncertainties TEXT NOT NULL,
                scope_limitations TEXT NOT NULL,
                evidence_trail TEXT NOT NULL,
                concluded_at REAL NOT NULL
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS research_reproducibility (
                manifest_id TEXT PRIMARY KEY,
                research_id TEXT NOT NULL,
                dataset_digest_sha256 TEXT NOT NULL,
                methodology_version TEXT NOT NULL,
                code_digest_sha256 TEXT NOT NULL,
                random_seed INTEGER,
                environment_metadata TEXT NOT NULL,
                replay_instructions TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            """)
            conn.commit()

    # --- Requests ---
    def save_request(self, req: ResearchRequest) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO research_requests (
                research_id, original_question, normalized_objective, domain, scope,
                state, risk_level, requires_approval, created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                req.research_id,
                req.original_question,
                req.normalized_objective,
                req.domain,
                req.scope,
                req.state.value if isinstance(req.state, ResearchState) else str(req.state),
                req.risk_level,
                1 if req.requires_approval else 0,
                req.created_by,
                req.created_at,
                req.updated_at,
            ))
            conn.commit()

    def get_request(self, research_id: str) -> Optional[ResearchRequest]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM research_requests WHERE research_id = ?", (research_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return ResearchRequest(
                research_id=row["research_id"],
                original_question=row["original_question"],
                normalized_objective=row["normalized_objective"],
                domain=row["domain"],
                scope=row["scope"],
                state=ResearchState(row["state"]),
                risk_level=row["risk_level"],
                requires_approval=bool(row["requires_approval"]),
                created_by=row["created_by"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    # --- Knowledge Gaps ---
    def save_knowledge_gap(self, gap: KnowledgeGapRecord) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO research_knowledge_gaps (
                gap_id, research_id, description, why_it_matters, evidence_required,
                possible_acquisition_method, priority, resolution_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                gap.gap_id,
                gap.research_id,
                gap.description,
                gap.why_it_matters,
                gap.evidence_required,
                gap.possible_acquisition_method,
                gap.priority,
                gap.resolution_status,
            ))
            conn.commit()

    def list_knowledge_gaps(self, research_id: str) -> List[KnowledgeGapRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM research_knowledge_gaps WHERE research_id = ?", (research_id,))
            rows = cursor.fetchall()
            return [
                KnowledgeGapRecord(
                    gap_id=r["gap_id"],
                    research_id=r["research_id"],
                    description=r["description"],
                    why_it_matters=r["why_it_matters"],
                    evidence_required=r["evidence_required"],
                    possible_acquisition_method=r["possible_acquisition_method"],
                    priority=r["priority"],
                    resolution_status=r["resolution_status"],
                ) for r in rows
            ]

    # --- Hypotheses ---
    def save_hypothesis(self, hyp: HypothesisRecord) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO research_hypotheses (
                hypothesis_id, research_id, statement, hypothesis_type, scope,
                assumptions, supporting_evidence, contradictory_evidence,
                expected_observations, falsification_conditions, state,
                confidence_score, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                hyp.hypothesis_id,
                hyp.research_id,
                hyp.statement,
                hyp.hypothesis_type.value if isinstance(hyp.hypothesis_type, HypothesisType) else str(hyp.hypothesis_type),
                hyp.scope,
                json.dumps(hyp.assumptions),
                json.dumps(hyp.supporting_evidence),
                json.dumps(hyp.contradictory_evidence),
                json.dumps(hyp.expected_observations),
                json.dumps(hyp.falsification_conditions),
                hyp.state.value if isinstance(hyp.state, HypothesisState) else str(hyp.state),
                hyp.confidence_score,
                hyp.created_at,
                hyp.updated_at,
            ))
            conn.commit()

    def get_hypothesis(self, hypothesis_id: str) -> Optional[HypothesisRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM research_hypotheses WHERE hypothesis_id = ?", (hypothesis_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return HypothesisRecord(
                hypothesis_id=row["hypothesis_id"],
                research_id=row["research_id"],
                statement=row["statement"],
                hypothesis_type=HypothesisType(row["hypothesis_type"]),
                scope=row["scope"],
                assumptions=json.loads(row["assumptions"]),
                supporting_evidence=json.loads(row["supporting_evidence"]),
                contradictory_evidence=json.loads(row["contradictory_evidence"]),
                expected_observations=json.loads(row["expected_observations"]),
                falsification_conditions=json.loads(row["falsification_conditions"]),
                state=HypothesisState(row["state"]),
                confidence_score=row["confidence_score"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def list_hypotheses(self, research_id: str) -> List[HypothesisRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM research_hypotheses WHERE research_id = ?", (research_id,))
            rows = cursor.fetchall()
            return [
                HypothesisRecord(
                    hypothesis_id=r["hypothesis_id"],
                    research_id=r["research_id"],
                    statement=r["statement"],
                    hypothesis_type=HypothesisType(r["hypothesis_type"]),
                    scope=r["scope"],
                    assumptions=json.loads(r["assumptions"]),
                    supporting_evidence=json.loads(r["supporting_evidence"]),
                    contradictory_evidence=json.loads(r["contradictory_evidence"]),
                    expected_observations=json.loads(r["expected_observations"]),
                    falsification_conditions=json.loads(r["falsification_conditions"]),
                    state=HypothesisState(r["state"]),
                    confidence_score=r["confidence_score"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                ) for r in rows
            ]

    # --- Experiments ---
    def save_experiment(self, exp: ExperimentDefinition) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO research_experiments (
                experiment_id, research_id, hypothesis_id, title, objective,
                experiment_type, independent_variables, dependent_variables,
                controlled_variables, sampling_strategy, sample_size,
                baseline_condition, treatment_condition, measurement_protocol,
                stopping_conditions, success_criteria, failure_criteria,
                requires_approval, approval_token, isolation_environment, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                exp.experiment_id,
                exp.research_id,
                exp.hypothesis_id,
                exp.title,
                exp.objective,
                exp.experiment_type.value if isinstance(exp.experiment_type, ExperimentType) else str(exp.experiment_type),
                json.dumps(exp.independent_variables),
                json.dumps(exp.dependent_variables),
                json.dumps(exp.controlled_variables),
                exp.sampling_strategy,
                exp.sample_size,
                exp.baseline_condition,
                exp.treatment_condition,
                exp.measurement_protocol,
                exp.stopping_conditions,
                exp.success_criteria,
                exp.failure_criteria,
                1 if exp.requires_approval else 0,
                exp.approval_token,
                exp.isolation_environment,
                exp.status,
            ))
            conn.commit()

    def get_experiment(self, experiment_id: str) -> Optional[ExperimentDefinition]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM research_experiments WHERE experiment_id = ?", (experiment_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return ExperimentDefinition(
                experiment_id=row["experiment_id"],
                research_id=row["research_id"],
                hypothesis_id=row["hypothesis_id"],
                title=row["title"],
                objective=row["objective"],
                experiment_type=ExperimentType(row["experiment_type"]),
                independent_variables=json.loads(row["independent_variables"]),
                dependent_variables=json.loads(row["dependent_variables"]),
                controlled_variables=json.loads(row["controlled_variables"]),
                sampling_strategy=row["sampling_strategy"],
                sample_size=row["sample_size"],
                baseline_condition=row["baseline_condition"],
                treatment_condition=row["treatment_condition"],
                measurement_protocol=row["measurement_protocol"],
                stopping_conditions=row["stopping_conditions"],
                success_criteria=row["success_criteria"],
                failure_criteria=row["failure_criteria"],
                requires_approval=bool(row["requires_approval"]),
                approval_token=row["approval_token"],
                isolation_environment=row["isolation_environment"],
                status=row["status"],
            )

    # --- Hypothesis Tests ---
    def save_hypothesis_test(self, test: HypothesisTestResult) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO research_hypothesis_tests (
                test_id, hypothesis_id, method, sample_size, test_statistic,
                p_value, effect_size, confidence_interval, evaluated_state,
                reasoning, limitations, tested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                test.test_id,
                test.hypothesis_id,
                test.method,
                test.sample_size,
                test.test_statistic,
                test.p_value,
                test.effect_size,
                json.dumps(test.confidence_interval) if test.confidence_interval else None,
                test.evaluated_state.value if isinstance(test.evaluated_state, HypothesisState) else str(test.evaluated_state),
                test.reasoning,
                json.dumps(test.limitations),
                test.tested_at,
            ))
            conn.commit()

    # --- Conclusions ---
    def save_conclusion(self, concl: ResearchConclusion) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO research_conclusions (
                conclusion_id, research_id, state, summary, direct_observations,
                supported_claims, rejected_hypotheses, unresolved_uncertainties,
                scope_limitations, evidence_trail, concluded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                concl.conclusion_id,
                concl.research_id,
                concl.state.value if isinstance(concl.state, ConclusionState) else str(concl.state),
                concl.summary,
                json.dumps(concl.direct_observations),
                json.dumps(concl.supported_claims),
                json.dumps(concl.rejected_hypotheses),
                json.dumps(concl.unresolved_uncertainties),
                json.dumps(concl.scope_limitations),
                json.dumps(concl.evidence_trail),
                concl.concluded_at,
            ))
            conn.commit()

    def get_conclusion(self, research_id: str) -> Optional[ResearchConclusion]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM research_conclusions WHERE research_id = ? ORDER BY concluded_at DESC LIMIT 1", (research_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return ResearchConclusion(
                conclusion_id=row["conclusion_id"],
                research_id=row["research_id"],
                state=ConclusionState(row["state"]),
                summary=row["summary"],
                direct_observations=json.loads(row["direct_observations"]),
                supported_claims=json.loads(row["supported_claims"]),
                rejected_hypotheses=json.loads(row["rejected_hypotheses"]),
                unresolved_uncertainties=json.loads(row["unresolved_uncertainties"]),
                scope_limitations=json.loads(row["scope_limitations"]),
                evidence_trail=json.loads(row["evidence_trail"]),
                concluded_at=row["concluded_at"],
            )

    # --- Reproducibility Manifests ---
    def save_reproducibility(self, rep: ReproducibilityManifest) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO research_reproducibility (
                manifest_id, research_id, dataset_digest_sha256, methodology_version,
                code_digest_sha256, random_seed, environment_metadata,
                replay_instructions, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rep.manifest_id,
                rep.research_id,
                rep.dataset_digest_sha256,
                rep.methodology_version,
                rep.code_digest_sha256,
                rep.random_seed,
                json.dumps(rep.environment_metadata),
                rep.replay_instructions,
                rep.created_at,
            ))
            conn.commit()

    def get_reproducibility(self, research_id: str) -> Optional[ReproducibilityManifest]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM research_reproducibility WHERE research_id = ?", (research_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return ReproducibilityManifest(
                manifest_id=row["manifest_id"],
                research_id=row["research_id"],
                dataset_digest_sha256=row["dataset_digest_sha256"],
                methodology_version=row["methodology_version"],
                code_digest_sha256=row["code_digest_sha256"],
                random_seed=row["random_seed"],
                environment_metadata=json.loads(row["environment_metadata"]),
                replay_instructions=row["replay_instructions"],
                created_at=row["created_at"],
            )
