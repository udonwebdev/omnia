"""
OMNIA Module 37: Strategic Decision Support Persistence Repository
Provides durable SQLite persistence for decision cases, strategic options,
evaluation criteria, multi-criteria assessments, risk matrices, recommendations,
and post-decision outcome monitoring.
"""

import sqlite3
import json
import time
import logging
from typing import Dict, Any, List, Optional
from strategy.models import (
    DecisionCaseRecord,
    DecisionLifecycleState,
    StrategicOptionRecord,
    DecisionCriterion,
    CriterionDirection,
    OptionAssessment,
    RiskTradeoffAssessment,
    StrategicRecommendation,
    RecommendationOutcome,
    DecisionOutcomeMonitoring,
)

logger = logging.getLogger("Omnia.Strategy.Persistence")


class StrategyRepository:
    """Manages relational SQLite persistence for strategic decision cases and options analysis."""

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
            CREATE TABLE IF NOT EXISTS strategy_cases (
                case_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                category TEXT NOT NULL,
                deadline_ts REAL,
                context_json TEXT NOT NULL,
                desired_outcomes_json TEXT NOT NULL,
                constraints_json TEXT NOT NULL,
                available_resources_json TEXT NOT NULL,
                stakeholders_json TEXT NOT NULL,
                risk_tolerance TEXT NOT NULL,
                version INTEGER DEFAULT 1,
                state TEXT NOT NULL,
                selected_option_id TEXT,
                decided_by TEXT,
                approval_token TEXT,
                review_date_ts REAL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS strategy_options (
                option_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                is_baseline INTEGER NOT NULL,
                expected_outcome TEXT NOT NULL,
                estimated_cost REAL NOT NULL,
                implementation_complexity TEXT NOT NULL,
                reversibility_score REAL NOT NULL,
                time_horizon_days INTEGER NOT NULL,
                dependencies_json TEXT NOT NULL,
                benefits_json TEXT NOT NULL,
                disadvantages_json TEXT NOT NULL,
                critical_assumptions_json TEXT NOT NULL,
                known_limitations_json TEXT NOT NULL,
                origin TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (case_id) REFERENCES strategy_cases(case_id)
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS strategy_criteria (
                criterion_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                name TEXT NOT NULL,
                weight REAL NOT NULL,
                direction TEXT NOT NULL,
                is_mandatory INTEGER NOT NULL DEFAULT 0,
                minimum_threshold REAL,
                acceptable_range_json TEXT,
                description TEXT,
                FOREIGN KEY (case_id) REFERENCES strategy_cases(case_id)
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS strategy_assessments (
                assessment_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                option_id TEXT NOT NULL,
                criterion_scores_json TEXT NOT NULL,
                normalized_score REAL NOT NULL,
                is_pareto_dominated INTEGER NOT NULL DEFAULT 0,
                violates_mandatory_constraint INTEGER NOT NULL DEFAULT 0,
                constraint_violations_json TEXT NOT NULL,
                FOREIGN KEY (case_id) REFERENCES strategy_cases(case_id),
                FOREIGN KEY (option_id) REFERENCES strategy_options(option_id)
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS strategy_risk_assessments (
                assessment_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                option_id TEXT NOT NULL,
                probability_of_failure REAL NOT NULL,
                severity_of_failure REAL NOT NULL,
                financial_exposure REAL NOT NULL,
                operational_disruption TEXT NOT NULL,
                security_risk TEXT NOT NULL,
                opportunity_cost_notes TEXT NOT NULL,
                mitigation_strategy TEXT NOT NULL,
                residual_risk_score REAL NOT NULL,
                is_acceptable INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (case_id) REFERENCES strategy_cases(case_id),
                FOREIGN KEY (option_id) REFERENCES strategy_options(option_id)
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS strategy_recommendations (
                recommendation_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                outcome TEXT NOT NULL,
                recommended_option_id TEXT,
                primary_justification TEXT NOT NULL,
                key_tradeoffs_json TEXT NOT NULL,
                major_risks_json TEXT NOT NULL,
                critical_assumptions_json TEXT NOT NULL,
                conditions_for_invalidation_json TEXT NOT NULL,
                confidence_level TEXT NOT NULL,
                suggested_review_date_ts REAL NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (case_id) REFERENCES strategy_cases(case_id)
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS strategy_outcomes (
                monitoring_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                selected_option_id TEXT NOT NULL,
                actual_cost REAL,
                expected_vs_actual_variance_pct REAL NOT NULL DEFAULT 0.0,
                assumptions_still_valid INTEGER NOT NULL DEFAULT 1,
                invalidated_assumptions_json TEXT NOT NULL,
                reassessment_triggered INTEGER NOT NULL DEFAULT 0,
                reassessment_reason TEXT,
                observed_at REAL NOT NULL,
                FOREIGN KEY (case_id) REFERENCES strategy_cases(case_id)
            );
            """)
            conn.commit()

    # Case Operations
    def save_case(self, case: DecisionCaseRecord) -> None:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT OR REPLACE INTO strategy_cases (
                case_id, title, description, owner_id, category, deadline_ts,
                context_json, desired_outcomes_json, constraints_json,
                available_resources_json, stakeholders_json, risk_tolerance,
                version, state, selected_option_id, decided_by, approval_token,
                review_date_ts, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                case.case_id, case.title, case.description, case.owner_id, case.category,
                case.deadline_ts, json.dumps(case.context), json.dumps(case.desired_outcomes),
                json.dumps(case.constraints), json.dumps(case.available_resources),
                json.dumps(case.stakeholders), case.risk_tolerance, case.version,
                case.state.value, case.selected_option_id, case.decided_by,
                case.approval_token, case.review_date_ts, case.created_at, case.updated_at
            ))
            conn.commit()

    def get_case(self, case_id: str) -> Optional[DecisionCaseRecord]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM strategy_cases WHERE case_id = ?", (case_id,))
            row = cur.fetchone()
            if not row:
                return None
            return DecisionCaseRecord(
                case_id=row["case_id"],
                title=row["title"],
                description=row["description"],
                owner_id=row["owner_id"],
                category=row["category"],
                deadline_ts=row["deadline_ts"],
                context=json.loads(row["context_json"]),
                desired_outcomes=json.loads(row["desired_outcomes_json"]),
                constraints=json.loads(row["constraints_json"]),
                available_resources=json.loads(row["available_resources_json"]),
                stakeholders=json.loads(row["stakeholders_json"]),
                risk_tolerance=row["risk_tolerance"],
                version=row["version"],
                state=DecisionLifecycleState(row["state"]),
                selected_option_id=row["selected_option_id"],
                decided_by=row["decided_by"],
                approval_token=row["approval_token"],
                review_date_ts=row["review_date_ts"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def list_cases(self, state: Optional[DecisionLifecycleState] = None) -> List[DecisionCaseRecord]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            if state:
                cur.execute("SELECT * FROM strategy_cases WHERE state = ?", (state.value,))
            else:
                cur.execute("SELECT * FROM strategy_cases")
            results = []
            for row in cur.fetchall():
                results.append(DecisionCaseRecord(
                    case_id=row["case_id"],
                    title=row["title"],
                    description=row["description"],
                    owner_id=row["owner_id"],
                    category=row["category"],
                    deadline_ts=row["deadline_ts"],
                    context=json.loads(row["context_json"]),
                    desired_outcomes=json.loads(row["desired_outcomes_json"]),
                    constraints=json.loads(row["constraints_json"]),
                    available_resources=json.loads(row["available_resources_json"]),
                    stakeholders=json.loads(row["stakeholders_json"]),
                    risk_tolerance=row["risk_tolerance"],
                    version=row["version"],
                    state=DecisionLifecycleState(row["state"]),
                    selected_option_id=row["selected_option_id"],
                    decided_by=row["decided_by"],
                    approval_token=row["approval_token"],
                    review_date_ts=row["review_date_ts"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                ))
            return results

    # Options Operations
    def save_option(self, option: StrategicOptionRecord) -> None:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT OR REPLACE INTO strategy_options (
                option_id, case_id, title, description, is_baseline, expected_outcome,
                estimated_cost, implementation_complexity, reversibility_score,
                time_horizon_days, dependencies_json, benefits_json, disadvantages_json,
                critical_assumptions_json, known_limitations_json, origin, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                option.option_id, option.case_id, option.title, option.description,
                1 if option.is_baseline else 0, option.expected_outcome, option.estimated_cost,
                option.implementation_complexity, option.reversibility_score,
                option.time_horizon_days, json.dumps(option.dependencies), json.dumps(option.benefits),
                json.dumps(option.disadvantages), json.dumps(option.critical_assumptions),
                json.dumps(option.known_limitations), option.origin, option.created_at
            ))
            conn.commit()

    def list_options_for_case(self, case_id: str) -> List[StrategicOptionRecord]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM strategy_options WHERE case_id = ?", (case_id,))
            results = []
            for row in cur.fetchall():
                results.append(StrategicOptionRecord(
                    option_id=row["option_id"],
                    case_id=row["case_id"],
                    title=row["title"],
                    description=row["description"],
                    is_baseline=bool(row["is_baseline"]),
                    expected_outcome=row["expected_outcome"],
                    estimated_cost=row["estimated_cost"],
                    implementation_complexity=row["implementation_complexity"],
                    reversibility_score=row["reversibility_score"],
                    time_horizon_days=row["time_horizon_days"],
                    dependencies=json.loads(row["dependencies_json"]),
                    benefits=json.loads(row["benefits_json"]),
                    disadvantages=json.loads(row["disadvantages_json"]),
                    critical_assumptions=json.loads(row["critical_assumptions_json"]),
                    known_limitations=json.loads(row["known_limitations_json"]),
                    origin=row["origin"],
                    created_at=row["created_at"],
                ))
            return results

    # Criteria Operations
    def save_criterion(self, crit: DecisionCriterion) -> None:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT OR REPLACE INTO strategy_criteria (
                criterion_id, case_id, name, weight, direction, is_mandatory,
                minimum_threshold, acceptable_range_json, description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                crit.criterion_id, crit.case_id, crit.name, crit.weight, crit.direction.value,
                1 if crit.is_mandatory else 0, crit.minimum_threshold,
                json.dumps(crit.acceptable_range) if crit.acceptable_range else None, crit.description
            ))
            conn.commit()

    def list_criteria_for_case(self, case_id: str) -> List[DecisionCriterion]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM strategy_criteria WHERE case_id = ?", (case_id,))
            results = []
            for row in cur.fetchall():
                results.append(DecisionCriterion(
                    criterion_id=row["criterion_id"],
                    case_id=row["case_id"],
                    name=row["name"],
                    weight=row["weight"],
                    direction=CriterionDirection(row["direction"]),
                    is_mandatory=bool(row["is_mandatory"]),
                    minimum_threshold=row["minimum_threshold"],
                    acceptable_range=json.loads(row["acceptable_range_json"]) if row["acceptable_range_json"] else None,
                    description=row["description"] or "",
                ))
            return results

    # Assessments & Risks
    def save_assessment(self, ass: OptionAssessment) -> None:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT OR REPLACE INTO strategy_assessments (
                assessment_id, case_id, option_id, criterion_scores_json,
                normalized_score, is_pareto_dominated, violates_mandatory_constraint,
                constraint_violations_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ass.assessment_id, ass.case_id, ass.option_id, json.dumps(ass.criterion_scores),
                ass.normalized_score, 1 if ass.is_pareto_dominated else 0,
                1 if ass.violates_mandatory_constraint else 0, json.dumps(ass.constraint_violations)
            ))
            conn.commit()

    def save_risk_assessment(self, risk: RiskTradeoffAssessment) -> None:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT OR REPLACE INTO strategy_risk_assessments (
                assessment_id, case_id, option_id, probability_of_failure,
                severity_of_failure, financial_exposure, operational_disruption,
                security_risk, opportunity_cost_notes, mitigation_strategy,
                residual_risk_score, is_acceptable
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                risk.assessment_id, risk.case_id, risk.option_id, risk.probability_of_failure,
                risk.severity_of_failure, risk.financial_exposure, risk.operational_disruption,
                risk.security_risk, risk.opportunity_cost_notes, risk.mitigation_strategy,
                risk.residual_risk_score, 1 if risk.is_acceptable else 0
            ))
            conn.commit()

    # Recommendations & Outcomes
    def save_recommendation(self, rec: StrategicRecommendation) -> None:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT OR REPLACE INTO strategy_recommendations (
                recommendation_id, case_id, outcome, recommended_option_id,
                primary_justification, key_tradeoffs_json, major_risks_json,
                critical_assumptions_json, conditions_for_invalidation_json,
                confidence_level, suggested_review_date_ts, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rec.recommendation_id, rec.case_id, rec.outcome.value, rec.recommended_option_id,
                rec.primary_justification, json.dumps(rec.key_tradeoffs), json.dumps(rec.major_risks),
                json.dumps(rec.critical_assumptions), json.dumps(rec.conditions_for_invalidation),
                rec.confidence_level, rec.suggested_review_date_ts, rec.created_at
            ))
            conn.commit()

    def get_latest_recommendation(self, case_id: str) -> Optional[StrategicRecommendation]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT * FROM strategy_recommendations WHERE case_id = ?
            ORDER BY created_at DESC LIMIT 1
            """, (case_id,))
            row = cur.fetchone()
            if not row:
                return None
            return StrategicRecommendation(
                recommendation_id=row["recommendation_id"],
                case_id=row["case_id"],
                outcome=RecommendationOutcome(row["outcome"]),
                recommended_option_id=row["recommended_option_id"],
                primary_justification=row["primary_justification"],
                key_tradeoffs=json.loads(row["key_tradeoffs_json"]),
                major_risks=json.loads(row["major_risks_json"]),
                critical_assumptions=json.loads(row["critical_assumptions_json"]),
                conditions_for_invalidation=json.loads(row["conditions_for_invalidation_json"]),
                confidence_level=row["confidence_level"],
                suggested_review_date_ts=row["suggested_review_date_ts"],
                created_at=row["created_at"],
            )

    def save_outcome_monitoring(self, mon: DecisionOutcomeMonitoring) -> None:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT OR REPLACE INTO strategy_outcomes (
                monitoring_id, case_id, selected_option_id, actual_cost,
                expected_vs_actual_variance_pct, assumptions_still_valid,
                invalidated_assumptions_json, reassessment_triggered,
                reassessment_reason, observed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                mon.monitoring_id, mon.case_id, mon.selected_option_id, mon.actual_cost,
                mon.expected_vs_actual_variance_pct, 1 if mon.assumptions_still_valid else 0,
                json.dumps(mon.invalidated_assumptions), 1 if mon.reassessment_triggered else 0,
                mon.reassessment_reason, mon.observed_at
            ))
            conn.commit()
