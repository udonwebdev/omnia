"""
Omnia Module 32: Feature Engineering Pipeline
Extracts verifiable statistical and temporal features from input observations
strictly bounded by as_of_time to prevent future data leakage.
"""

from typing import List, Dict, Any, Optional
import math
import statistics

from prediction.models import ForecastInput


class FeaturePipeline:
    """Computes time-series and statistical summary features for forecasting."""

    @staticmethod
    def extract_features(
        inputs: List[ForecastInput],
        as_of_time: float,
    ) -> Dict[str, Any]:
        """
        Calculates time-series summary features from observations strictly <= as_of_time.
        """
        # Strict filtration against leakage
        valid_inputs = [inp for inp in inputs if inp.timestamp <= as_of_time and inp.value is not None]
        if not valid_inputs:
            return {
                "sample_count": 0,
                "recent_value": None,
                "historical_mean": None,
                "historical_variance": None,
                "historical_std": None,
                "trend_slope": 0.0,
                "rate_of_change": 0.0,
                "time_since_last_observation": 0.0,
            }

        # Chronological sort
        sorted_inputs = sorted(valid_inputs, key=lambda x: x.timestamp)
        n = len(sorted_inputs)

        # Separate numeric vs categorical
        numeric_values = []
        for inp in sorted_inputs:
            if isinstance(inp.value, (int, float)):
                numeric_values.append(float(inp.value))

        recent_input = sorted_inputs[-1]
        time_since_last = max(0.0, as_of_time - recent_input.timestamp)

        features: Dict[str, Any] = {
            "sample_count": n,
            "recent_value": recent_input.value,
            "time_since_last_observation": time_since_last,
            "is_numeric": len(numeric_values) == n,
        }

        if numeric_values:
            mean_val = statistics.mean(numeric_values)
            median_val = statistics.median(numeric_values)
            variance_val = statistics.variance(numeric_values) if len(numeric_values) > 1 else 0.0
            std_val = math.sqrt(variance_val)

            features["historical_mean"] = round(mean_val, 4)
            features["historical_median"] = round(median_val, 4)
            features["historical_variance"] = round(variance_val, 4)
            features["historical_std"] = round(std_val, 4)
            features["min_value"] = min(numeric_values)
            features["max_value"] = max(numeric_values)

            # Trend estimation via simple linear regression (slope)
            if len(numeric_values) >= 2:
                ts = [inp.timestamp for inp in sorted_inputs if isinstance(inp.value, (int, float))]
                t_mean = statistics.mean(ts)
                denom = sum((t - t_mean) ** 2 for t in ts)
                if denom > 0:
                    slope = sum((ts[i] - t_mean) * (numeric_values[i] - mean_val) for i in range(len(ts))) / denom
                    features["trend_slope"] = round(slope, 6)
                else:
                    features["trend_slope"] = 0.0

                # Rate of change between last two observations
                t_delta = sorted_inputs[-1].timestamp - sorted_inputs[-2].timestamp
                if t_delta > 0:
                    v_delta = float(sorted_inputs[-1].value) - float(sorted_inputs[-2].value)
                    features["rate_of_change"] = round(v_delta / t_delta, 6)
                else:
                    features["rate_of_change"] = 0.0
            else:
                features["trend_slope"] = 0.0
                features["rate_of_change"] = 0.0
        else:
            # Categorical frequency distribution
            counts: Dict[str, int] = {}
            for inp in sorted_inputs:
                k = str(inp.value)
                counts[k] = counts.get(k, 0) + 1
            features["category_frequencies"] = {k: v / n for k, v in counts.items()}
            features["mode_value"] = max(counts.keys(), key=lambda k: counts[k])

        return features
