import uuid
"""
End-to-End integration tests for Module 32: Predictive Intelligence & Risk Forecasting Engine via Omnia Tools.
"""

import unittest
import json
import time

from omnia_tools import (
    request_forecast,
    assess_target_risk,
    compare_forecast_scenarios,
    record_forecast_outcome,
    evaluate_forecast_accuracy,
    check_model_drift,
)


class TestPredictionModule32E2E(unittest.TestCase):
    def test_e2e_prediction_lifecycle_flow(self):
        """Exercises Module 32 end-to-end through the Omnia Tools interface."""
        now = time.time()
        target_id = f"e2e_db_qps_{uuid.uuid4().hex[:6]}"
        inputs = [
            {"input_id": "inp_1", "timestamp": now - 300, "value": 50.0, "source": "cluster_metrics"},
            {"input_id": "inp_2", "timestamp": now - 200, "value": 55.0, "source": "cluster_metrics"},
            {"input_id": "inp_3", "timestamp": now - 100, "value": 60.0, "source": "cluster_metrics"},
            {"input_id": "inp_4", "timestamp": now, "value": 65.0, "source": "cluster_metrics"},
        ]

        # 1. Request forecast
        fc_raw = request_forecast(
            target_id=target_id,
            target_type="TIME_SERIES",
            target_description="Database query rate projection",
            duration_sec=300.0,
            method_name="TrendForecaster",
            inputs_json=json.dumps(inputs),
        )
        fc = json.loads(fc_raw)
        self.assertIn("forecast_id", fc)
        self.assertEqual(fc["status"], "COMPLETED")
        self.assertGreaterEqual(fc["predicted_value"], 65.0)
        self.assertIsNotNone(fc["interval"])
        self.assertFalse(fc["is_calibrated_probability"])
        forecast_id = fc["forecast_id"]

        # 2. Assess emerging risk
        risk_raw = assess_target_risk(
            target_id=target_id,
            critical_threshold=60.0,  # 65 > 60 triggers risk factor
            impact_score=4.0,
            horizon_sec=600.0,
            inputs_json=json.dumps(inputs),
        )
        risk = json.loads(risk_raw)
        self.assertIn("risk_id", risk)
        self.assertEqual(risk["impact_score"], 4.0)
        self.assertFalse(risk["is_calibrated_likelihood"])
        self.assertIn(risk["risk_level"], ["HIGH", "CRITICAL", "MODERATE"])

        # 3. Compare hypothetical scenarios
        scenarios = [
            {
                "scenario_id": "scn_throttle",
                "name": "Throttle Ingestion",
                "modified_variables": {"simulated_last_value": 40.0},
                "assumptions": [{"description": "Limits batch writers"}]
            }
        ]
        scn_raw = compare_forecast_scenarios(
            target_id=target_id,
            target_type="TIME_SERIES",
            scenarios_json=json.dumps(scenarios),
            duration_sec=300.0,
            method_name="LastObservationBaseline",
            inputs_json=json.dumps(inputs),
        )
        scn_res = json.loads(scn_raw)
        self.assertTrue(scn_res["is_hypothetical"])
        self.assertIn("scn_throttle", scn_res["differences"])
        self.assertEqual(scn_res["differences"]["scn_throttle"]["value_delta"], -25.0)

        # 4. Record actual ground-truth outcome
        outcome_raw = record_forecast_outcome(
            forecast_id=forecast_id,
            observed_value=72.5,
            notes="Actual observed query rate at horizon close",
        )
        outcome = json.loads(outcome_raw)
        self.assertIn("outcome_id", outcome)
        self.assertEqual(outcome["observed_value"], 72.5)
        outcome_id = outcome["outcome_id"]

        # 5. Evaluate forecast accuracy against ground-truth
        eval_raw = evaluate_forecast_accuracy(
            forecast_id=forecast_id,
            outcome_id=outcome_id,
        )
        evaluation = json.loads(eval_raw)
        self.assertIn("evaluation_id", evaluation)
        self.assertIn("error_value", evaluation)
        self.assertGreaterEqual(evaluation["error_value"], 0.0)

        # 6. Check drift
        drift_raw = check_model_drift(
            model_name="TrendForecaster",
            target_id=target_id,
            baseline_error=2.0,
        )
        drift = json.loads(drift_raw)
        self.assertIn("drift_id", drift)
        self.assertIn("recommendation", drift)

        # 7. Test supersession by issuing replacement forecast
        fc2_raw = request_forecast(
            target_id=target_id,
            target_type="TIME_SERIES",
            duration_sec=300.0,
            inputs_json=json.dumps(inputs),
        )
        fc2 = json.loads(fc2_raw)
        self.assertNotEqual(fc2["forecast_id"], forecast_id)

        # Verify initial forecast was marked SUPERSEDED in persistence
        from prediction.service import predictive_service
        fc1_updated = predictive_service.get_forecast(forecast_id)
        self.assertIsNotNone(fc1_updated)
        self.assertEqual(fc1_updated.status.value, "SUPERSEDED")
        self.assertEqual(fc1_updated.superseded_by, fc2["forecast_id"])


if __name__ == "__main__":
    unittest.main()
