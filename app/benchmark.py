import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List
import numpy as np

from app.db import (
    get_readings_col,
    get_benchmarks_col,
    create_indexes,
    drop_indexes,
    get_db,
)
from app.cache import get_redis, cached
from app.aggregate import get_aggregated_stats

def run_query_q1(sensor_id: str, clock: datetime) -> Any:
    """Q1: Latest reading for a sensor <= clock."""
    return get_readings_col().find_one(
        {"sensor_id": sensor_id, "timestamp": {"$lte": clock}},
        sort=[("timestamp", -1)]
    )

def run_query_q2(sensor_id: str, clock: datetime) -> List[Any]:
    """Q2: Sensor readings in a 7-day window."""
    t0 = clock - timedelta(days=7)
    return list(get_readings_col().find(
        {"sensor_id": sensor_id, "timestamp": {"$gte": t0, "$lte": clock}}
    ))

def run_query_q3(sensor_id: str, clock: datetime) -> List[Any]:
    """Q3: Daily summary for 30 days via aggregation pipeline."""
    t0 = clock - timedelta(days=30)
    pipeline = [
        {"$match": {"sensor_id": sensor_id, "timestamp": {"$gte": t0, "$lte": clock}, "value": {"$ne": None}}},
        {"$group": {
            "_id": {"$dateTrunc": {"date": "$timestamp", "unit": "day"}},
            "min": {"$min": "$value"},
            "max": {"$max": "$value"},
            "avg": {"$avg": "$value"}
        }},
        {"$sort": {"_id": 1}}
    ]
    return list(get_readings_col().aggregate(pipeline))

def run_benchmark_suite(iterations: int = 50, sensor_id: str = "PT08.S1(CO)") -> List[Dict[str, Any]]:
    """
    Run Benchmark Lab comparing Q1, Q2, Q3 across 4 conditions (TECHNICAL §5.10):
    - C1: No indexes
    - C2: Indexes, no cache
    - C3: Indexes + cache miss
    - C4: Indexes + cache hit
    5 warm-up iterations discarded, followed by N measured runs.
    """
    first_doc = get_readings_col().find_one({}, sort=[("timestamp", -1)])
    clock = first_doc["timestamp"] if first_doc else datetime(2004, 3, 17, 18, 0, 0)
    dataset_rows = get_readings_col().count_documents({})

    run_id = str(uuid.uuid4())[:8]
    ran_at = datetime.utcnow().isoformat()
    results: List[Dict[str, Any]] = []

    queries = {
        "Q1_latest": lambda: run_query_q1(sensor_id, clock),
        "Q2_7day_window": lambda: run_query_q2(sensor_id, clock),
        "Q3_daily_summary": lambda: run_query_q3(sensor_id, clock),
    }

    conditions = ["C1_no_index", "C2_index_no_cache", "C3_index_cache_miss", "C4_index_cache_hit"]

    r = get_redis()

    for cond in conditions:
        # Condition setup
        if cond == "C1_no_index":
            drop_indexes()
        else:
            create_indexes()

        for q_name, q_func in queries.items():
            # Warm-up (5 runs discarded)
            for _ in range(5):
                q_func()

            timings: List[float] = []

            for i in range(iterations):
                if cond == "C3_index_cache_miss":
                    # Flush cache key before query to force miss
                    if r is not None:
                        try:
                            r.delete(f"bench:{q_name}:{i}")
                        except Exception:
                            pass

                t0 = time.perf_counter()

                if cond in ["C3_index_cache_miss", "C4_index_cache_hit"]:
                    cache_key = f"bench:{q_name}:{0 if cond == 'C4_index_cache_hit' else i}"
                    cached(cache_key, ttl=300, loader=q_func)
                else:
                    q_func()

                t1 = time.perf_counter()
                timings.append((t1 - t0) * 1000.0)  # Convert to milliseconds

            mean_ms = float(np.mean(timings))
            median_ms = float(np.median(timings))
            p95_ms = float(np.percentile(timings, 95))

            row = {
                "run_id": run_id,
                "ran_at": ran_at,
                "dataset_rows": dataset_rows,
                "query": q_name,
                "condition": cond,
                "iterations": iterations,
                "mean_ms": round(mean_ms, 3),
                "median_ms": round(median_ms, 3),
                "p95_ms": round(p95_ms, 3),
            }
            results.append(row)

    # Ensure indexes restored after benchmark
    create_indexes()

    # Save results to MongoDB
    if results:
        try:
            get_benchmarks_col().insert_many(results, ordered=False)
        except Exception:
            pass

    return results
