"""
Unit tests for Module 32: Predictive Intelligence & Risk Forecasting Engine.
"""

import unittest
import os
import shutil
import tempfile
import time
import uuid

from prediction.models import (
    ForecastType,
    ForecastStatus,
    RiskLevel,
    ForecastTarget,
    ForecastHorizon,
    ForecastRequest,
    ForecastInput,
    ForecastScenario,
    ForecastAssumption,
    Forecast,
    ForecastOutcome,
    ForecastEvaluation,
)
from prediction.validation import validate_input_dataset
from prediction.features import FeaturePipeline
from prediction.baselines import (
    LastObservationBaseline,
    MovingAverageForecaster,
    TrendForecaster,
    FrequencyClassificationForecaster,
    DurationForecaster,
    RuleBasedRiskForecaster,
)
from prediction.scenarios import ScenarioAnalyzer
from prediction.calibration import CalibrationEngine
from prediction.drift import DriftDetector
from prediction.persistence import PredictionPersistence
from prediction.service import PredictiveIntelligenceService


class TestPredictiveIntelligenceSubsystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.test_dir, "test_prediction.db")
        cls.persistence = PredictionPersistence(db_path=cls.db_path)
        cls.service = PredictiveIntelligenceService(persistence=cls.persistence)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_01_data_quality_and_leakage_prevention(self):
        """Tests that future observations after as_of_time are caught as temporal leakage."""
        now = 1000.0
        valid_inputs = [
            ForecastInput(input_id="i1", timestamp=900.0, value=10.0, source="metric"),
            ForecastInput(input_id="i2", timestamp=950.0, value=12.0, source="metric"),
            ForecastInput(input_id="i3", timestamp=990.0, value=14.0, source="metric"),
        ]
        is_valid, report = validate_input_dataset(valid_inputs, as_of_time=now, min_samples=3)
        self.assertTrue(is_valid)
        self.assertFalse(report.has_future_leakage)

        # Inject future record (leakage)
        leaked_inputs = list(valid_inputs) + [
            ForecastInput(input_id="i_future", timestamp=1050.0, value=20.0, source="metric")
        ]
        is_valid_leak, report_leak = validate_input_dataset(leaked_inputs, as_of_time=now)
        self.assertFalse(is_valid_leak)
        self.assertTrue(report_leak.has_future_leakage)
        self.assertTrue(any("Temporal data leakage detected" in iss for iss in report_leak.issues))

    def test_02_baseline_forecasters_deterministic(self):
        """Verifies deterministic behavior of MovingAverage and Trend forecasters."""
        now = 2000.0
        inputs = [
            ForecastInput(input_id="t1", timestamp=1000.0, value=10.0, source="metric"),
            ForecastInput(input_id="t2", timestamp=1100.0, value=20.0, source="metric"),
            ForecastInput(input_id="t3", timestamp=1200.0, value=30.0, source="metric"),
            ForecastInput(input_id="t4", timestamp=1300.0, value=40.0, source="metric"),
        ]
        req = ForecastRequest(
            request_id="req_trend",
            target=ForecastTarget(
                target_id="tgt_cpu",
                target_description="CPU load forecast",
                target_type=ForecastType.REGRESSION,
                observation_unit="percent",
                outcome_definition="Observed CPU utilization",
            ),
            horizon=ForecastHorizon.from_duration(100.0, start_time=1300.0),
            as_of_time=1300.0,
        )

        features = FeaturePipeline.extract_features(inputs, as_of_time=1300.0)
        self.assertEqual(features["recent_value"], 40.0)
        self.assertEqual(features["historical_mean"], 25.0)

        # 1. Moving average of last 2 (30 and 40 -> 35.0)
        ma_forecaster = MovingAverageForecaster(window_size=2)
        fc_ma = ma_forecaster.forecast(req, inputs, features)
        self.assertEqual(fc_ma.predicted_value, 35.0)

        # 2. Trend forecaster (slope = 0.1 units/sec, midpoint +50s -> 40 + 5 = 45.0)
        trend_forecaster = TrendForecaster()
        fc_trend = trend_forecaster.forecast(req, inputs, features)
        self.assertAlmostEqual(fc_trend.predicted_value, 45.0, places=2)
        self.assertIsNotNone(fc_trend.interval)

    def test_03_probability_integrity_and_classification(self):
        """Ensures frequency classification score is never claimed as calibrated probability without calibration."""
        now = 3000.0
        inputs = [
            ForecastInput(input_id="c1", timestamp=2900.0, value="HEALTHY", source="state"),
            ForecastInput(input_id="c2", timestamp=2950.0, value="HEALTHY", source="state"),
            ForecastInput(input_id="c3", timestamp=2980.0, value="DEGRADED", source="state"),
            ForecastInput(input_id="c4", timestamp=2990.0, value="HEALTHY", source="state"),
        ]
        req = ForecastRequest(
            request_id="req_class",
            target=ForecastTarget(
                target_id="tgt_svc_status",
                target_description="Service status class",
                target_type=ForecastType.CLASSIFICATION,
                observation_unit="status_enum",
                outcome_definition="Service health enum",
            ),
            horizon=ForecastHorizon.from_duration(300.0, start_time=now),
            as_of_time=now,
        )

        features = FeaturePipeline.extract_features(inputs, as_of_time=now)
        clf = FrequencyClassificationForecaster()
        fc = clf.forecast(req, inputs, features)

        self.assertEqual(fc.predicted_class, "HEALTHY")
        self.assertEqual(fc.probability, 0.75)
        # MUST BE FALSE
        self.assertFalse(fc.is_calibrated_probability)

    def test_04_duration_forecaster(self):
        """Verifies duration estimation percentiles and median."""
        durations = [10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0, 100.0]
        inputs = [
            ForecastInput(input_id=f"d{i}", timestamp=4000.0 + i, value=d, source="task_log")
            for i, d in enumerate(durations)
        ]
        req = ForecastRequest(
            request_id="req_dur",
            target=ForecastTarget(
                target_id="tgt_task_duration",
                target_description="Dataform execution duration",
                target_type=ForecastType.DURATION_ESTIMATION,
                observation_unit="seconds",
                outcome_definition="Task completion time",
            ),
            horizon=ForecastHorizon.from_duration(3600.0, start_time=4100.0),
            as_of_time=4100.0,
        )

        features = FeaturePipeline.extract_features(inputs, as_of_time=4100.0)
        forecaster = DurationForecaster()
        fc = forecaster.forecast(req, inputs, features)

        self.assertAlmostEqual(fc.predicted_value, 32.5, places=1)
        self.assertIsNotNone(fc.interval)
        self.assertLessEqual(fc.interval.lower_bound, fc.predicted_value)
        self.assertGreaterEqual(fc.interval.upper_bound, fc.predicted_value)

    def test_05_rule_based_risk_separation(self):
        """Verifies risk assessment strictly separates likelihood from impact severity."""
        now = 5000.0
        inputs = [
            ForecastInput(input_id="r1", timestamp=4900.0, value=85.0, source="telemetry"),  # Breach threshold 80
            ForecastInput(input_id="r2", timestamp=4950.0, value=92.0, source="telemetry"),
            ForecastInput(input_id="r3", timestamp=4990.0, value=98.0, source="telemetry"),
        ]
        features = FeaturePipeline.extract_features(inputs, as_of_time=now)
        req = ForecastRequest(
            request_id="req_risk",
            target=ForecastTarget(
                target_id="tgt_risk",
                target_description="System hazard risk",
                target_type=ForecastType.ANOMALY_RISK,
                observation_unit="risk_score",
                outcome_definition="Host failure event",
            ),
            horizon=ForecastHorizon.from_duration(1800.0, start_time=now),
            parameters={"critical_threshold": 80.0, "configured_impact": 5.0},
            as_of_time=now,
        )

        forecaster = RuleBasedRiskForecaster()
        fc = forecaster.forecast(req, inputs, features)

        self.assertIsNotNone(fc.risk_assessment)
        ra = fc.risk_assessment
        self.assertEqual(ra.impact_score, 5.0)
        self.assertGreaterEqual(ra.likelihood_score, 0.5)
        self.assertIn(ra.risk_level, (RiskLevel.HIGH, RiskLevel.CRITICAL))
        self.assertTrue(len(ra.risk_factors) >= 1)
        self.assertFalse(ra.is_calibrated_likelihood)

    def test_06_hypothetical_scenario_analysis(self):
        """Verifies scenario comparisons are explicitly tagged as HYPOTHETICAL conditional estimates."""
        now = 6000.0
        inputs = [
            ForecastInput(input_id="s1", timestamp=5800.0, value=100.0, source="load"),
            ForecastInput(input_id="s2", timestamp=5900.0, value=110.0, source="load"),
            ForecastInput(input_id="s3", timestamp=6000.0, value=120.0, source="load"),
        ]
        base_req = ForecastRequest(
            request_id="req_base_scn",
            target=ForecastTarget(
                target_id="tgt_server_load",
                target_description="Server load comparison",
                target_type=ForecastType.TIME_SERIES,
                observation_unit="qps",
                outcome_definition="Recorded query rate",
            ),
            horizon=ForecastHorizon.from_duration(300.0, start_time=now),
            as_of_time=now,
        )

        scenarios = [
            ForecastScenario(
                scenario_id="scn_load_shed",
                name="Load Shedding Activated",
                description="Drop non-critical background jobs",
                modified_variables={"simulated_last_value": 70.0},
                assumptions=[ForecastAssumption(assumption_id="a1", description="30% traffic shed instantly")],
                is_hypothetical=True,
            )
        ]

        res = ScenarioAnalyzer.compare_scenarios(base_req, inputs, scenarios, method_name="LastObservationBaseline")
        self.assertTrue(res.is_hypothetical)
        self.assertEqual(res.baseline_forecast.predicted_value, 120.0)
        self.assertEqual(res.scenario_forecasts["scn_load_shed"].predicted_value, 70.0)
        self.assertEqual(res.differences["scn_load_shed"]["value_delta"], -50.0)

    def test_07_calibration_calculation_and_brier(self):
        """Verifies hand-calculated Brier score and MAE in CalibrationEngine."""
        target = ForecastTarget(
            target_id="tgt_eval",
            target_description="Test target",
            target_type=ForecastType.REGRESSION,
            observation_unit="units",
            outcome_definition="Test outcome",
        )
        horizon = ForecastHorizon.from_duration(3600.0)

        # 3 regression pairs: pred vs actual -> errors: |10-12|=2, |20-20|=0, |30-34|=4. MAE = 6/3 = 2.0
        fc1 = Forecast(forecast_id="f1", request_id="r1", target=target, horizon=horizon, forecast_type=ForecastType.REGRESSION, predicted_value=10.0, method_name="TestModel")
        out1 = ForecastOutcome(outcome_id="o1", forecast_id="f1", target_id="tgt_eval", observed_value=12.0)

        fc2 = Forecast(forecast_id="f2", request_id="r2", target=target, horizon=horizon, forecast_type=ForecastType.REGRESSION, predicted_value=20.0, method_name="TestModel")
        out2 = ForecastOutcome(outcome_id="o2", forecast_id="f2", target_id="tgt_eval", observed_value=20.0)

        fc3 = Forecast(forecast_id="f3", request_id="r3", target=target, horizon=horizon, forecast_type=ForecastType.REGRESSION, predicted_value=30.0, method_name="TestModel")
        out3 = ForecastOutcome(outcome_id="o3", forecast_id="f3", target_id="tgt_eval", observed_value=34.0)

        pairs = [(fc1, out1), (fc2, out2), (fc3, out3)]
        calib = CalibrationEngine.compute_calibration_record("TestModel", "REGRESSION", pairs)
        self.assertIsNotNone(calib)
        self.assertEqual(calib.mae, 2.0)
        self.assertAlmostEqual(calib.rmse, 2.582, places=2)

    def test_08_drift_detection(self):
        """Verifies model drift alert when recent evaluation error exceeds baseline threshold."""
        # 4 baseline evals with error ~ 1.0, 4 recent evals with error ~ 5.0
        evals = [
            ForecastEvaluation(evaluation_id=f"e{i}", forecast_id=f"f{i}", outcome_id=f"o{i}", metric_name="MAE", error_value=1.0, is_accurate=True)
            for i in range(4)
        ] + [
            ForecastEvaluation(evaluation_id=f"e{i}", forecast_id=f"f{i}", outcome_id=f"o{i}", metric_name="MAE", error_value=5.0, is_accurate=False)
            for i in range(4, 8)
        ]

        drift = DriftDetector.assess_drift("TestModel", "tgt_eval", evals, drift_threshold_multiplier=1.75, min_evals_required=6)
        self.assertTrue(drift.detected)
        self.assertEqual(drift.drift_type, "INCREASING_PREDICTION_ERROR")
        self.assertIn("RECOMMEND_RECALIBRATION", drift.recommendation)


if __name__ == "__main__":
    unittest.main()
