import os
from pathlib import Path
from typing import Any, Dict
from dotenv import load_dotenv
import yaml

# Base project path
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file
load_dotenv(dotenv_path=BASE_DIR / ".env")

# Database & Cache settings
MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB: str = os.getenv("MONGO_DB", "thrumsense")
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "60"))

# Replay settings
REPLAY_IN_PROCESS: bool = os.getenv("REPLAY_IN_PROCESS", "true").lower() == "true"
REPLAY_SPEED: int = int(os.getenv("REPLAY_SPEED", "1"))

# Dataset settings
DATA_PATH: Path = BASE_DIR / os.getenv("DATA_PATH", "data/AirQualityUCI.csv")

# Benchmark settings
BENCHMARK_N: int = int(os.getenv("BENCHMARK_N", "50"))
BENCHMARK_SCALED: bool = os.getenv("BENCHMARK_SCALED", "false").lower() == "true"

# App & Logging settings
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
DASH_HOST: str = os.getenv("DASH_HOST", "127.0.0.1")
DASH_PORT: int = int(os.getenv("DASH_PORT", "8050"))
DASH_DEBUG: bool = os.getenv("DASH_DEBUG", "false").lower() == "true"

# Load thresholds config
THRESHOLDS_FILE = BASE_DIR / "config" / "thresholds.yaml"

def load_thresholds() -> Dict[str, Any]:
    """Load configuration from config/thresholds.yaml."""
    if THRESHOLDS_FILE.exists():
        with open(THRESHOLDS_FILE, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {
        "defaults": {"method": "percentile", "low_pct": 1.0, "high_pct": 99.0},
        "adaptive": {"window_hours": 24, "z_limit": 3.5},
        "fault": {"dropout_hours": 3, "flatline_hours": 4},
        "health": {
            "missing_weight": 40.0,
            "alert_weight": 40.0,
            "flatline_penalty": 20.0,
            "alert_ratio_k": 10.0,
        },
        "overrides": {},
    }

THRESHOLDS: Dict[str, Any] = load_thresholds()
