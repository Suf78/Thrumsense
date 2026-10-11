import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.db import get_readings_col, get_alerts_col
from app.cache import cached, get_redis, get_cache_stats
from app.aggregate import get_aggregated_stats
from app.health import get_fleet_health
from app.replay import replay_engine
from app.detect import get_thresholds_for_sensor

logger = logging.getLogger(__name__)

# List of all 13 standard sensor variable identifiers
ALL_SENSORS: List[str] = [
    "CO(GT)",
    "PT08.S1(CO)",
    "NMHC(GT)",
    "C6H6(GT)",
    "PT08.S2(NMHC)",
    "NOx(GT)",
    "PT08.S3(NOx)",
    "NO2(GT)",
    "PT08.S4(NO2)",
    "PT08.S5(O3)",
    "T",
    "RH",
    "AH",
]

def get_sim_state() -> Dict[str, Any]:
    """Retrieve current simulation state and clock bounded time."""
    clock = replay_engine.get_clock()
    return {
        "clock": clock.isoformat(),
        "clock_dt": clock,
        "running": replay_engine.is_running(),
        "speed": replay_engine.get_speed(),
    }

def get_latest(sensor_id: str) -> Optional[Dict[str, Any]]:
    """Get latest sensor reading bounded by sim clock with cache-aside."""
    clock = replay_engine.get_clock()
    clock_str = clock.strftime("%Y%m%d%H%M%S")
    key = f"latest:{sensor_id}:{clock_str}"

    def loader() -> Optional[Dict[str, Any]]:
        doc = get_readings_col().find_one(
            {"sensor_id": sensor_id, "timestamp": {"$lte": clock}},
            sort=[("timestamp", -1)]
        )
        if not doc:
            return None
        return {
            "sensor_id": doc["sensor_id"],
            "timestamp": doc["timestamp"].isoformat(),
            "value": doc.get("value"),
            "kind": doc.get("kind"),
            "unit": doc.get("unit"),
        }

    return cached(key, ttl=30, loader=loader)

def get_series(sensor_id: str, start: datetime, end: datetime) -> List[Dict[str, Any]]:
    """
    Get raw time-series bounded by sim clock for charts.
    Not cached as chart zoom/filters vary frequently.
    """
    clock = replay_engine.get_clock()
    bounded_end = min(end, clock)

    cursor = get_readings_col().find(
        {"sensor_id": sensor_id, "timestamp": {"$gte": start, "$lte": bounded_end}},
        sort=[("timestamp", 1)]
    )
    results = []
    for doc in cursor:
        results.append({
            "timestamp": doc["timestamp"].isoformat(),
            "value": doc.get("value"),
            "kind": doc.get("kind"),
            "unit": doc.get("unit"),
        })
    return results

def get_stats(sensor_id: str, gran: str, start: datetime, end: datetime) -> List[Dict[str, Any]]:
    """Get min/max/avg aggregation buckets bounded by sim clock."""
    clock = replay_engine.get_clock()
    bounded_end = min(end, clock)
    return get_aggregated_stats(sensor_id=sensor_id, gran=gran, start=start, end=bounded_end)

def get_alerts(sensor_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve latest alerts bounded by sim clock."""
    clock = replay_engine.get_clock()
    alerts_col = get_alerts_col()

    query: Dict[str, Any] = {"timestamp": {"$lte": clock}}
    if sensor_id:
        query["sensor_id"] = sensor_id

    cursor = alerts_col.find(query).sort("timestamp", -1).limit(limit)
    alerts = []
    for doc in cursor:
        alerts.append({
            "sensor_id": doc["sensor_id"],
            "timestamp": doc["timestamp"].isoformat() if isinstance(doc["timestamp"], datetime) else str(doc["timestamp"]),
            "type": doc.get("type"),
            "severity": doc.get("severity"),
            "value": doc.get("value"),
            "expected_low": doc.get("expected_low"),
            "expected_high": doc.get("expected_high"),
            "rule": doc.get("rule"),
            "explanation": doc.get("explanation"),
        })
    return alerts

def get_health() -> Dict[str, Any]:
    """Return fleet health and sensor scores bounded by current sim clock."""
    clock = replay_engine.get_clock()
    return get_fleet_health(ALL_SENSORS, clock)

def get_kpis() -> Dict[str, Any]:
    """Retrieve high-level KPI strip data."""
    clock = replay_engine.get_clock()
    health_data = get_health()
    cache_stats = get_cache_stats()

    t24 = clock - timedelta(hours=24)
    active_alerts_count = get_alerts_col().count_documents({
        "timestamp": {"$gt": t24, "$lte": clock}
    })

    sensors_ok_count = sum(
        1 for h in health_data.get("sensors", {}).values() if h.get("band") == "ok"
    )

    total_readings = get_readings_col().count_documents({
        "timestamp": {"$gt": t24, "$lte": clock}
    })
    valid_readings = get_readings_col().count_documents({
        "timestamp": {"$gt": t24, "$lte": clock},
        "value": {"$ne": None}
    })
    data_quality_pct = (valid_readings / total_readings * 100.0) if total_readings > 0 else 100.0

    return {
        "sensors_ok": sensors_ok_count,
        "total_sensors": len(ALL_SENSORS),
        "active_alerts": active_alerts_count,
        "data_quality_pct": round(data_quality_pct, 1),
        "fleet_score": health_data.get("fleet_score", 100.0),
        "fleet_band": health_data.get("fleet_band", "ok"),
        "cache_stats": cache_stats,
    }
