from datetime import datetime
import math
from typing import Any, Dict, List, Optional
from app.config import THRESHOLDS

# In-memory derived static thresholds: sensor_id -> {"low": float, "high": float}
_DERIVED_THRESHOLDS: Dict[str, Dict[str, float]] = {}

def set_derived_thresholds(thresholds: Dict[str, Dict[str, float]]) -> None:
    """Store computed percentile thresholds in memory."""
    global _DERIVED_THRESHOLDS
    _DERIVED_THRESHOLDS = thresholds

def get_thresholds_for_sensor(sensor_id: str) -> Dict[str, float]:
    """Retrieve threshold boundaries for a sensor (overrides win)."""
    overrides = THRESHOLDS.get("overrides", {}).get(sensor_id, {})
    if "low" in overrides and "high" in overrides:
        return {"low": float(overrides["low"]), "high": float(overrides["high"])}
    return _DERIVED_THRESHOLDS.get(sensor_id, {"low": float("-inf"), "high": float("inf")})

def check_static_threshold(sensor_id: str, value: float) -> Optional[Dict[str, Any]]:
    """Check if reading value violates static percentile thresholds (TECHNICAL §5.2)."""
    limits = get_thresholds_for_sensor(sensor_id)
    low, high = limits["low"], limits["high"]
    if value < low:
        return {
            "type": "THRESHOLD_LOW",
            "rule": f"Lower bound violation (< {low:.2f})",
            "value": value,
            "expected_low": low,
            "expected_high": high,
            "explanation": f"{sensor_id} was {value:.2f}, below lower limit {low:.2f}",
        }
    elif value > high:
        return {
            "type": "THRESHOLD_HIGH",
            "rule": f"Upper bound violation (> {high:.2f})",
            "value": value,
            "expected_low": low,
            "expected_high": high,
            "explanation": f"{sensor_id} was {value:.2f}, above upper limit {high:.2f}",
        }
    return None

def check_adaptive_spike(
    sensor_id: str,
    value: float,
    window: List[float],
    z_limit: float = 3.5
) -> Optional[Dict[str, Any]]:
    """
    Rolling robust z-score using median and MAD (TECHNICAL §5.3):
    med = median(w)
    mad = median(|w - med|)
    z = 0.6745 * (x - med) / mad
    Flag if |z| > z_limit.
    """
    valid_window = [v for v in window if v is not None and not math.isnan(v)]
    if len(valid_window) < 5:
        return None

    sorted_w = sorted(valid_window)
    n = len(sorted_w)
    mid = n // 2
    median = (sorted_w[mid] if n % 2 != 0 else (sorted_w[mid - 1] + sorted_w[mid]) / 2.0)

    abs_deviations = sorted([abs(v - median) for v in valid_window])
    mad = (abs_deviations[mid] if n % 2 != 0 else (abs_deviations[mid - 1] + abs_deviations[mid]) / 2.0)

    if mad == 0.0:
        return None

    z_score = 0.6745 * (value - median) / mad
    if abs(z_score) > z_limit:
        expected_range_low = median - (z_limit * mad / 0.6745)
        expected_range_high = median + (z_limit * mad / 0.6745)
        return {
            "type": "ADAPTIVE_SPIKE",
            "rule": f"Adaptive robust z-score (|z| = {abs(z_score):.2f} > {z_limit})",
            "value": value,
            "expected_low": round(expected_range_low, 2),
            "expected_high": round(expected_range_high, 2),
            "explanation": f"{sensor_id} anomaly detected via rolling median/MAD (z={z_score:+.2f})",
        }
    return None

def check_faults(
    sensor_id: str,
    consecutive_nulls: int,
    recent_values: List[Optional[float]],
    dropout_hours: int = 3,
    flatline_hours: int = 4
) -> Optional[Dict[str, Any]]:
    """
    Check sensor hardware fault rules (TECHNICAL §5.4):
    - SENSOR_DROPOUT: consecutive nulls >= dropout_hours
    - FLATLINE: consecutive identical non-null values >= flatline_hours
    """
    if consecutive_nulls >= dropout_hours:
        return {
            "type": "SENSOR_DROPOUT",
            "rule": f"Dropout >= {dropout_hours} hours",
            "value": None,
            "expected_low": None,
            "expected_high": None,
            "explanation": f"{sensor_id} has been missing for {consecutive_nulls} consecutive hours",
        }

    valid_recent = [v for v in recent_values if v is not None and not math.isnan(v)]
    if len(valid_recent) >= flatline_hours:
        slice_check = valid_recent[-flatline_hours:]
        first_val = slice_check[0]
        if all(abs(v - first_val) < 1e-6 for v in slice_check):
            return {
                "type": "FLATLINE",
                "rule": f"Flatline >= {flatline_hours} hours",
                "value": first_val,
                "expected_low": None,
                "expected_high": None,
                "explanation": f"{sensor_id} held constant value {first_val} for {flatline_hours} hours",
            }

    return None

def determine_severity(
    has_threshold: bool,
    has_adaptive: bool,
    has_fault: bool,
    value: Optional[float],
    threshold_limits: Dict[str, float],
    consecutive_nulls: int = 0,
    dropout_limit: int = 3
) -> str:
    """
    Determine alert severity level (TECHNICAL §5.5):
    - info: 1 rule (threshold or adaptive)
    - warning: 2 rules agree, or any fault rule
    - critical: both fire and value > 1.5x limit, or dropout >= 2x limit
    """
    if consecutive_nulls >= 2 * dropout_limit:
        return "critical"

    if has_threshold and has_adaptive and value is not None:
        low, high = threshold_limits.get("low", float("-inf")), threshold_limits.get("high", float("inf"))
        if (high > 0 and value > 1.5 * high) or (low != float("-inf") and value < 0.5 * low):
            return "critical"
        return "warning"

    if has_fault:
        return "warning"

    if has_threshold or has_adaptive:
        return "info"

    return "info"

def evaluate_reading(
    reading: Dict[str, Any],
    rolling_window: List[float],
    consecutive_nulls: int,
    recent_values: List[Optional[float]]
) -> List[Dict[str, Any]]:
    """
    Full detector evaluation pipeline for an incoming reading document.
    Returns list of alert dictionaries to insert into DB.
    """
    sensor_id = reading["sensor_id"]
    timestamp = reading["timestamp"]
    value = reading.get("value")

    adaptive_cfg = THRESHOLDS.get("adaptive", {})
    fault_cfg = THRESHOLDS.get("fault", {})

    dropout_hours = int(fault_cfg.get("dropout_hours", 3))
    flatline_hours = int(fault_cfg.get("flatline_hours", 4))
    z_limit = float(adaptive_cfg.get("z_limit", 3.5))

    alerts: List[Dict[str, Any]] = []

    # 1. Fault check
    fault_alert = check_faults(
        sensor_id,
        consecutive_nulls=consecutive_nulls,
        recent_values=recent_values,
        dropout_hours=dropout_hours,
        flatline_hours=flatline_hours,
    )

    if value is None:
        if fault_alert:
            severity = determine_severity(
                has_threshold=False,
                has_adaptive=False,
                has_fault=True,
                value=None,
                threshold_limits={},
                consecutive_nulls=consecutive_nulls,
                dropout_limit=dropout_hours,
            )
            fault_alert.update({
                "sensor_id": sensor_id,
                "timestamp": timestamp,
                "severity": severity,
                "created_at": datetime.utcnow(),
            })
            alerts.append(fault_alert)
        return alerts

    # Value is present -> check static & adaptive
    thresh_alert = check_static_threshold(sensor_id, value)
    adapt_alert = check_adaptive_spike(sensor_id, value, rolling_window, z_limit=z_limit)

    has_thresh = thresh_alert is not None
    has_adapt = adapt_alert is not None
    has_fault = fault_alert is not None

    limits = get_thresholds_for_sensor(sensor_id)
    severity = determine_severity(
        has_threshold=has_thresh,
        has_adaptive=has_adapt,
        has_fault=has_fault,
        value=value,
        threshold_limits=limits,
        consecutive_nulls=consecutive_nulls,
        dropout_limit=dropout_hours,
    )

    for item in [thresh_alert, adapt_alert, fault_alert]:
        if item is not None:
            item.update({
                "sensor_id": sensor_id,
                "timestamp": timestamp,
                "severity": severity,
                "created_at": datetime.utcnow(),
            })
            alerts.append(item)

    return alerts
