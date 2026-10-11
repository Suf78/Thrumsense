from datetime import datetime, timedelta
from typing import Any, Dict, List
from app.config import THRESHOLDS
from app.db import get_readings_col, get_alerts_col
from app.cache import cached

def compute_sensor_health(sensor_id: str, clock: datetime) -> Dict[str, Any]:
    """
    Compute sensor health score (0-100) over trailing 24 sim-hours (TECHNICAL §5.6):
    score = 100 - 40 * missing_ratio - 40 * min(1, alert_ratio * k) - 20 * flatline_flag
    clamped to [0, 100]
    Bands: >= 80 OK (green), 50-79 Watch (amber), < 50 Faulty (red).
    """
    health_cfg = THRESHOLDS.get("health", {})
    missing_weight = float(health_cfg.get("missing_weight", 40.0))
    alert_weight = float(health_cfg.get("alert_weight", 40.0))
    flatline_penalty = float(health_cfg.get("flatline_penalty", 20.0))
    k = float(health_cfg.get("alert_ratio_k", 10.0))

    t0 = clock - timedelta(hours=24)
    readings_col = get_readings_col()
    alerts_col = get_alerts_col()

    docs = list(readings_col.find(
        {"sensor_id": sensor_id, "timestamp": {"$gt": t0, "$lte": clock}},
        {"value": 1, "timestamp": 1}
    ).sort("timestamp", 1))

    total_expected = 24
    if not docs:
        return {
            "sensor_id": sensor_id,
            "score": 0.0,
            "band": "faulty",
            "missing_ratio": 1.0,
            "alert_ratio": 0.0,
            "flatline": False,
        }

    null_count = sum(1 for d in docs if d.get("value") is None)
    # Count missing hours if fewer docs than expected
    if len(docs) < total_expected:
        null_count += (total_expected - len(docs))
    missing_ratio = min(1.0, null_count / float(total_expected))

    # Alert count in trailing 24 hours
    alert_count = alerts_col.count_documents({
        "sensor_id": sensor_id,
        "timestamp": {"$gt": t0, "$lte": clock}
    })
    alert_ratio = min(1.0, (alert_count / float(total_expected)) * k)

    # Flatline detection in the window
    flatline_flag = 0.0
    valid_values = [d["value"] for d in docs if d.get("value") is not None]
    if len(valid_values) >= 4:
        for i in range(len(valid_values) - 3):
            window = valid_values[i:i+4]
            if all(abs(v - window[0]) < 1e-6 for v in window):
                flatline_flag = 1.0
                break

    score = 100.0 - (missing_weight * missing_ratio) - (alert_weight * alert_ratio) - (flatline_penalty * flatline_flag)
    clamped_score = max(0.0, min(100.0, score))

    if clamped_score >= 80.0:
        band = "ok"
    elif clamped_score >= 50.0:
        band = "watch"
    else:
        band = "faulty"

    return {
        "sensor_id": sensor_id,
        "score": round(clamped_score, 1),
        "band": band,
        "missing_ratio": round(missing_ratio, 2),
        "alert_ratio": round(alert_ratio, 2),
        "flatline": bool(flatline_flag > 0),
    }

def get_fleet_health(sensor_ids: List[str], clock: datetime, ttl: int = 15) -> Dict[str, Any]:
    """Calculate per-sensor health and fleet mean score with caching."""
    clock_str = clock.strftime("%Y%m%d%H%M%S")
    cache_key = f"health:fleet:{clock_str}"

    def loader() -> Dict[str, Any]:
        sensors_health = {}
        scores = []
        for s_id in sensor_ids:
            h = compute_sensor_health(s_id, clock)
            sensors_health[s_id] = h
            scores.append(h["score"])

        fleet_score = round(sum(scores) / len(scores), 1) if scores else 100.0
        if fleet_score >= 80.0:
            fleet_band = "ok"
        elif fleet_score >= 50.0:
            fleet_band = "watch"
        else:
            fleet_band = "faulty"

        return {
            "fleet_score": fleet_score,
            "fleet_band": fleet_band,
            "sensors": sensors_health,
        }

    return cached(cache_key, ttl=ttl, loader=loader)
