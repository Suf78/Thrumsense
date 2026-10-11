from datetime import datetime
from typing import Any, Dict, List
from app.db import get_readings_col
from app.cache import cached

def build_stats_pipeline(sensor_id: str, start: datetime, end: datetime, gran: str) -> List[Dict[str, Any]]:
    """Build Mongo aggregation pipeline for hourly or daily min, max, avg (TECHNICAL §5.9)."""
    date_trunc_unit = "hour" if gran == "hour" else "day"
    return [
        {
            "$match": {
                "sensor_id": sensor_id,
                "timestamp": {"$gte": start, "$lte": end},
                "value": {"$ne": None},
            }
        },
        {
            "$group": {
                "_id": {
                    "$dateTrunc": {
                        "date": "$timestamp",
                        "unit": date_trunc_unit
                    }
                },
                "min": {"$min": "$value"},
                "max": {"$max": "$value"},
                "avg": {"$avg": "$value"},
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
    ]

def get_aggregated_stats(
    sensor_id: str,
    gran: str,
    start: datetime,
    end: datetime,
    ttl: int = 60
) -> List[Dict[str, Any]]:
    """Retrieve min/max/avg buckets using MongoDB aggregation pipeline with cache-aside."""
    start_str = start.strftime("%Y%m%d%H")
    end_str = end.strftime("%Y%m%d%H")
    cache_key = f"stats:{sensor_id}:{gran}:{start_str}:{end_str}"

    def loader() -> List[Dict[str, Any]]:
        readings = get_readings_col()
        pipeline = build_stats_pipeline(sensor_id, start, end, gran)
        cursor = readings.aggregate(pipeline)
        results: List[Dict[str, Any]] = []
        for doc in cursor:
            results.append({
                "timestamp": doc["_id"].isoformat() if isinstance(doc["_id"], datetime) else str(doc["_id"]),
                "min": round(float(doc["min"]), 2) if doc["min"] is not None else None,
                "max": round(float(doc["max"]), 2) if doc["max"] is not None else None,
                "avg": round(float(doc["avg"]), 2) if doc["avg"] is not None else None,
                "count": doc["count"],
            })
        return results

    return cached(cache_key, ttl=ttl, loader=loader)
