from typing import Optional
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.database import Database
from pymongo.collection import Collection
from app.config import MONGO_URI, MONGO_DB

_client: Optional[MongoClient] = None

def get_client() -> MongoClient:
    """Get or create singleton MongoClient."""
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
    return _client

def get_db() -> Database:
    """Return the application database handle."""
    return get_client()[MONGO_DB]

def get_readings_col() -> Collection:
    """Return handle to 'readings' collection."""
    return get_db()["readings"]

def get_alerts_col() -> Collection:
    """Return handle to 'alerts' collection."""
    return get_db()["alerts"]

def get_benchmarks_col() -> Collection:
    """Return handle to 'benchmarks' collection."""
    return get_db()["benchmarks"]

def create_indexes() -> None:
    """Create indexes for performance as specified in TECHNICAL.md section 4."""
    readings = get_readings_col()
    # Compound index for sensor + time window queries
    readings.create_index([("sensor_id", ASCENDING), ("timestamp", ASCENDING)], name="idx_sensor_ts")
    # Time-only scan index
    readings.create_index([("timestamp", ASCENDING)], name="idx_ts")

    alerts = get_alerts_col()
    alerts.create_index([("timestamp", DESCENDING)], name="idx_alert_ts")
    alerts.create_index([("sensor_id", ASCENDING), ("timestamp", DESCENDING)], name="idx_alert_sensor_ts")

def drop_indexes() -> None:
    """Drop non-default indexes (used for benchmark comparisons)."""
    readings = get_readings_col()
    # Drop all except _id_
    for idx_name in ["idx_sensor_ts", "idx_ts"]:
        try:
            readings.drop_index(idx_name)
        except Exception:
            pass

def check_connection() -> bool:
    """Check if MongoDB is reachable."""
    try:
        get_client().admin.command("ping")
        return True
    except Exception:
        return False
