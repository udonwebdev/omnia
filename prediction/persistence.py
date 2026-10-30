"""
Omnia Module 32: Predictive Intelligence Persistence Layer
Provides SQLite persistence for forecast requests, forecast records,
observed outcomes, evaluations, calibration records, and drift assessments.
"""

import sqlite3
import json
import os
import time
import logging
from typing import List, Dict, Any, Optional

from persistence.migrations import apply_migrations
from prediction.models import (
    Forecast,
    ForecastRequest,
    ForecastTarget,
    ForecastHorizon,
    ForecastInterval,
    ForecastAssumption,
    PredictionExplanation,
    RiskAssessment,
    RiskLevel,
    RiskFactor,
    ForecastOutcome,
    ForecastEvaluation,
    CalibrationRecord,
    DriftAssessment,
    ForecastType,
    ForecastStatus,
)

logger = logging.getLogger("Omnia.Prediction.Persistence")


class PredictionPersistence:
    """Authoritative SQLite repository for predictive state and evaluations."""

    def __init__(self, db_path: str = "omnia_prediction.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        # Ensure Schema V14 tables exist
        apply_migrations(self.db_path)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    # --- FORECAST REQUESTS ---

    def save_request(self, req: ForecastRequest) -> None:
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO forecast_requests (
                        request_id, target_id, target_description, target_type,
                        horizon_start, horizon_end, horizon_duration_sec,
                        parameters_json, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(request_id) DO UPDATE SET
                        status = excluded.status
                    """,
                    (
                        req.request_id,
                        req.target.target_id,
                        req.target.target_description,
                        req.target.target_type.value if isinstance(req.target.target_type, ForecastType) else str(req.target.target_type),
                        req.horizon.start_time,
                        req.horizon.end_time,
                        req.horizon.duration_sec,
                        json.dumps(req.parameters),
                        req.status.value if isinstance(req.status, ForecastStatus) else str(req.status),
                        req.created_at,
                    ),
                )
        finally:
            conn.close()

    def get_request(self, request_id: str) -> Optional[ForecastRequest]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM forecast_requests WHERE request_id = ?", (request_id,))
            row = cur.fetchone()
            if not row:
                return None
            target = ForecastTarget(
                target_id=row["target_id"],
                target_description=row["target_description"],
                target_type=ForecastType(row["target_type"]),
                observation_unit="units",
                outcome_definition="Independently observed state",
            )
            horizon = ForecastHorizon(
                start_time=float(row["horizon_start"]),
                end_time=float(row["horizon_end"]),
                duration_sec=float(row["horizon_duration_sec"]),
            )
            return ForecastRequest(
                request_id=row["request_id"],
                target=target,
                horizon=horizon,
                parameters=json.loads(row["parameters_json"]) if row["parameters_json"] else {},
                status=ForecastStatus(row["status"]),
                created_at=float(row["created_at"]),
            )
        finally:
            conn.close()

    # --- FORECAST RECORDS ---

    def save_forecast(self, fc: Forecast) -> None:
        # First ensure request exists in DB
        self.save_request(ForecastRequest(
            request_id=fc.request_id,
            target=fc.target,
            horizon=fc.horizon,
            as_of_time=fc.created_at,
        ))

        conn = self._get_connection()
        try:
            with conn:
                interval_lower = fc.interval.lower_bound if fc.interval else None
                interval_upper = fc.interval.upper_bound if fc.interval else None
                interval_conf = fc.interval.confidence_level if fc.interval else None
                is_calib_int = 1 if (fc.interval and fc.interval.is_calibrated) else 0
                cov_guar = fc.interval.coverage_guarantee if fc.interval else None

                conn.execute(
                    """
                    INSERT INTO forecast_records (
                        forecast_id, request_id, target_id, forecast_type,
                        predicted_value, predicted_class, probability, is_calibrated_probability,
                        interval_lower, interval_upper, interval_confidence, is_calibrated_interval,
                        coverage_guarantee, method_name, model_version, inputs_hash,
                        sample_count, assumptions_json, limitations_json, explanation_json,
                        risk_assessment_json, status, superseded_by, created_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(forecast_id) DO UPDATE SET
                        status = excluded.status,
                        superseded_by = excluded.superseded_by
                    """,
                    (
                        fc.forecast_id,
                        fc.request_id,
                        fc.target.target_id,
                        fc.forecast_type.value if isinstance(fc.forecast_type, ForecastType) else str(fc.forecast_type),
                        fc.predicted_value,
                        fc.predicted_class,
                        fc.probability,
                        1 if fc.is_calibrated_probability else 0,
                        interval_lower,
                        interval_upper,
                        interval_conf,
                        is_calib_int,
                        cov_guar,
                        fc.method_name,
                        fc.model_version,
                        fc.inputs_hash,
                        fc.sample_count,
                        json.dumps([a.to_dict() for a in fc.assumptions]),
                        json.dumps(fc.limitations),
                        json.dumps(fc.explanation.to_dict()) if fc.explanation else "{}",
                        json.dumps(fc.risk_assessment.to_dict()) if fc.risk_assessment else "{}",
                        fc.status.value if isinstance(fc.status, ForecastStatus) else str(fc.status),
                        fc.superseded_by,
                        fc.created_at,
                        fc.expires_at,
                    ),
                )
        finally:
            conn.close()

    def get_forecast(self, forecast_id: str) -> Optional[Forecast]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM forecast_records WHERE forecast_id = ?", (forecast_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_forecast(row)
        finally:
            conn.close()

    def get_forecasts_for_target(self, target_id: str) -> List[Forecast]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM forecast_records WHERE target_id = ? ORDER BY created_at DESC", (target_id,))
            return [self._row_to_forecast(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def _row_to_forecast(self, r: sqlite3.Row) -> Forecast:
        target = ForecastTarget(
            target_id=r["target_id"],
            target_description="",
            target_type=ForecastType(r["forecast_type"]),
            observation_unit="units",
            outcome_definition="",
        )
        horizon = ForecastHorizon(
            start_time=float(r["created_at"]),
            end_time=float(r["expires_at"]),
            duration_sec=float(r["expires_at"]) - float(r["created_at"]),
        )
        interval = None
        if r["interval_lower"] is not None and r["interval_upper"] is not None:
            interval = ForecastInterval(
                lower_bound=float(r["interval_lower"]),
                upper_bound=float(r["interval_upper"]),
                confidence_level=float(r["interval_confidence"]) if r["interval_confidence"] is not None else 0.95,
                is_calibrated=bool(r["is_calibrated_interval"]),
                coverage_guarantee=r["coverage_guarantee"] or "HEURISTIC",
            )

        explanation = None
        if r["explanation_json"]:
            exp_data = json.loads(r["explanation_json"])
            if exp_data:
                explanation = PredictionExplanation(
                    summary=exp_data.get("summary", ""),
                    key_factors=exp_data.get("key_factors", []),
                    baseline_comparison=exp_data.get("baseline_comparison"),
                    data_uncertainty=exp_data.get("data_uncertainty", "LOW"),
                    model_uncertainty=exp_data.get("model_uncertainty", "LOW"),
                    horizon_uncertainty=exp_data.get("horizon_uncertainty", "LOW"),
                    known_assumptions=exp_data.get("known_assumptions", []),
                    limitations=exp_data.get("limitations", []),
                )

        risk_assessment = None
        if r["risk_assessment_json"]:
            ra_data = json.loads(r["risk_assessment_json"])
            if ra_data:
                risk_assessment = RiskAssessment(
                    risk_id=ra_data.get("risk_id", "risk_unknown"),
                    target_id=r["target_id"],
                    risk_level=RiskLevel(ra_data.get("risk_level", "LOW")),
                    likelihood_score=float(ra_data.get("likelihood_score", 0.0)),
                    is_calibrated_likelihood=bool(ra_data.get("is_calibrated_likelihood", False)),
                    impact_score=float(ra_data.get("impact_score", 1.0)),
                    mitigations=ra_data.get("mitigations", []),
                    evaluated_at=float(ra_data.get("evaluated_at", r["created_at"])),
                    expires_at=float(ra_data.get("expires_at", r["expires_at"])),
                )

        return Forecast(
            forecast_id=r["forecast_id"],
            request_id=r["request_id"],
            target=target,
            horizon=horizon,
            forecast_type=ForecastType(r["forecast_type"]),
            predicted_value=float(r["predicted_value"]) if r["predicted_value"] is not None else None,
            predicted_class=r["predicted_class"],
            probability=float(r["probability"]) if r["probability"] is not None else None,
            is_calibrated_probability=bool(r["is_calibrated_probability"]),
            interval=interval,
            method_name=r["method_name"],
            model_version=r["model_version"],
            inputs_hash=r["inputs_hash"],
            sample_count=int(r["sample_count"]),
            limitations=json.loads(r["limitations_json"]) if r["limitations_json"] else [],
            explanation=explanation,
            risk_assessment=risk_assessment,
            status=ForecastStatus(r["status"]),
            superseded_by=r["superseded_by"],
            created_at=float(r["created_at"]),
            expires_at=float(r["expires_at"]),
        )

    # --- FORECAST OUTCOMES ---

    def save_outcome(self, outcome: ForecastOutcome) -> None:
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO forecast_outcomes (
                        outcome_id, forecast_id, target_id, observed_value,
                        observed_class, observed_at, source, is_verified, notes, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(outcome_id) DO UPDATE SET
                        observed_value = excluded.observed_value,
                        observed_class = excluded.observed_class,
                        notes = excluded.notes
                    """,
                    (
                        outcome.outcome_id,
                        outcome.forecast_id,
                        outcome.target_id,
                        outcome.observed_value,
                        outcome.observed_class,
                        outcome.observed_at,
                        outcome.source,
                        1 if outcome.is_verified else 0,
                        outcome.notes,
                        outcome.created_at,
                    ),
                )
        finally:
            conn.close()

    def get_outcome(self, outcome_id: str) -> Optional[ForecastOutcome]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM forecast_outcomes WHERE outcome_id = ?", (outcome_id,))
            r = cur.fetchone()
            if not r:
                return None
            return ForecastOutcome(
                outcome_id=r["outcome_id"],
                forecast_id=r["forecast_id"],
                target_id=r["target_id"],
                observed_value=float(r["observed_value"]) if r["observed_value"] is not None else None,
                observed_class=r["observed_class"],
                observed_at=float(r["observed_at"]),
                source=r["source"],
                is_verified=bool(r["is_verified"]),
                notes=r["notes"],
                created_at=float(r["created_at"]),
            )
        finally:
            conn.close()

    # --- FORECAST EVALUATIONS ---

    def save_evaluation(self, ev: ForecastEvaluation) -> None:
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO forecast_evaluations (
                        evaluation_id, forecast_id, outcome_id, metric_name,
                        error_value, is_accurate, evaluation_notes, evaluated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(evaluation_id) DO NOTHING
                    """,
                    (
                        ev.evaluation_id,
                        ev.forecast_id,
                        ev.outcome_id,
                        ev.metric_name,
                        ev.error_value,
                        1 if ev.is_accurate else 0,
                        ev.evaluation_notes,
                        ev.evaluated_at,
                    ),
                )
        finally:
            conn.close()

    def get_evaluations_for_model(self, model_name: str) -> List[ForecastEvaluation]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT fe.* FROM forecast_evaluations fe
                JOIN forecast_records fr ON fe.forecast_id = fr.forecast_id
                WHERE fr.method_name = ?
                ORDER BY fe.evaluated_at ASC
                """,
                (model_name,),
            )
            return [
                ForecastEvaluation(
                    evaluation_id=r["evaluation_id"],
                    forecast_id=r["forecast_id"],
                    outcome_id=r["outcome_id"],
                    metric_name=r["metric_name"],
                    error_value=float(r["error_value"]),
                    is_accurate=bool(r["is_accurate"]),
                    evaluated_at=float(r["evaluated_at"]),
                    evaluation_notes=r["evaluation_notes"],
                )
                for r in cur.fetchall()
            ]
        finally:
            conn.close()

    # --- CALIBRATION & DRIFT ---

    def save_calibration_record(self, calib: CalibrationRecord) -> None:
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO forecast_calibration_records (
                        calibration_id, model_name, target_type, sample_count,
                        brier_score, ece, mae, rmse, coverage_rate,
                        time_window_start, time_window_end, is_valid, notes, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(calibration_id) DO UPDATE SET
                        sample_count = excluded.sample_count,
                        updated_at = excluded.updated_at
                    """,
                    (
                        calib.calibration_id,
                        calib.model_name,
                        calib.target_type,
                        calib.sample_count,
                        calib.brier_score,
                        calib.ece,
                        calib.mae,
                        calib.rmse,
                        calib.coverage_rate,
                        calib.time_window_start,
                        calib.time_window_end,
                        1 if calib.is_valid else 0,
                        calib.notes,
                        calib.updated_at,
                    ),
                )
        finally:
            conn.close()

    def get_latest_calibration(self, model_name: str, target_type: str) -> Optional[CalibrationRecord]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT * FROM forecast_calibration_records
                WHERE model_name = ? AND target_type = ?
                ORDER BY updated_at DESC LIMIT 1
                """,
                (model_name, target_type),
            )
            r = cur.fetchone()
            if not r:
                return None
            return CalibrationRecord(
                calibration_id=r["calibration_id"],
                model_name=r["model_name"],
                target_type=r["target_type"],
                sample_count=int(r["sample_count"]),
                brier_score=float(r["brier_score"]) if r["brier_score"] is not None else None,
                ece=float(r["ece"]) if r["ece"] is not None else None,
                mae=float(r["mae"]) if r["mae"] is not None else None,
                rmse=float(r["rmse"]) if r["rmse"] is not None else None,
                coverage_rate=float(r["coverage_rate"]) if r["coverage_rate"] is not None else None,
                time_window_start=float(r["time_window_start"]),
                time_window_end=float(r["time_window_end"]),
                is_valid=bool(r["is_valid"]),
                notes=r["notes"],
                updated_at=float(r["updated_at"]),
            )
        finally:
            conn.close()

    def save_drift_assessment(self, drift: DriftAssessment) -> None:
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO forecast_drift_assessments (
                        drift_id, model_name, target_id, detected, drift_type,
                        p_value, metric_shift, sample_count, recommendation, detected_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(drift_id) DO NOTHING
                    """,
                    (
                        drift.drift_id,
                        drift.model_name,
                        drift.target_id,
                        1 if drift.detected else 0,
                        drift.drift_type,
                        drift.p_value,
                        drift.metric_shift,
                        drift.sample_count,
                        drift.recommendation,
                        drift.detected_at,
                    ),
                )
        finally:
            conn.close()
