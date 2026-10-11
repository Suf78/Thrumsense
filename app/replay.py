import json
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.config import REPLAY_SPEED, REPLAY_IN_PROCESS
from app.db import get_readings_col, get_alerts_col
from app.cache import get_redis
from app.detect import evaluate_reading

logger = logging.getLogger(__name__)

class ReplayEngine:
    """
    Simulation Clock and Stream Replay Engine per TECHNICAL.md section 5.7:
    - Maintains sim:clock and sim:state (running, speed) in Redis
    - Ticks forward 1 hour at a time
    - Triggers detection on arriving readings
    - Invalidates latest:{sensor} cache
    """
    def __init__(self):
        self._running: bool = False
        self._speed: int = REPLAY_SPEED
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        # In-memory rolling detector state: sensor_id -> {"window": [...], "recent_values": [...], "consecutive_nulls": int}
        self._state: Dict[str, Dict[str, Any]] = {}
        self._init_clock()

    def _init_clock(self) -> None:
        """Initialize or fetch sim:clock from Redis / Mongo."""
        r = get_redis()
        if r is not None:
            try:
                clock_str = r.get("sim:clock")
                if not clock_str:
                    first_doc = get_readings_col().find_one({}, sort=[("timestamp", 1)])
                    if first_doc:
                        t = first_doc["timestamp"]
                        r.set("sim:clock", t.isoformat())
                state = r.hgetall("sim:state")
                if not state:
                    r.hset("sim:state", mapping={"running": "false", "speed": str(self._speed)})
                return
            except Exception as e:
                logger.warning("Could not sync clock with Redis: %s", e)

    def get_clock(self) -> datetime:
        """Get current simulated clock datetime."""
        r = get_redis()
        if r is not None:
            try:
                val = r.get("sim:clock")
                if val:
                    return datetime.fromisoformat(val)
            except Exception:
                pass
        # Fallback to earliest timestamp in DB
        first_doc = get_readings_col().find_one({}, sort=[("timestamp", 1)])
        return first_doc["timestamp"] if first_doc else datetime(2004, 3, 10, 18, 0, 0)

    def set_clock(self, target_dt: datetime) -> None:
        """Set simulation clock to specific timestamp and rebuild rolling detector state."""
        r = get_redis()
        if r is not None:
            try:
                r.set("sim:clock", target_dt.isoformat())
            except Exception:
                pass
        self._rebuild_rolling_state(target_dt)

    def is_running(self) -> bool:
        r = get_redis()
        if r is not None:
            try:
                return r.hget("sim:state", "running") == "true"
            except Exception:
                pass
        return self._running

    def get_speed(self) -> int:
        r = get_redis()
        if r is not None:
            try:
                val = r.hget("sim:state", "speed")
                if val:
                    return int(val)
            except Exception:
                pass
        return self._speed

    def play(self) -> None:
        self._running = True
        r = get_redis()
        if r is not None:
            try:
                r.hset("sim:state", "running", "true")
            except Exception:
                pass

    def pause(self) -> None:
        self._running = False
        r = get_redis()
        if r is not None:
            try:
                r.hset("sim:state", "running", "false")
            except Exception:
                pass

    def set_speed(self, speed: int) -> None:
        self._speed = max(1, speed)
        r = get_redis()
        if r is not None:
            try:
                r.hset("sim:state", "speed", str(self._speed))
            except Exception:
                pass

    def reset(self) -> None:
        """Reset clock back to beginning."""
        self.pause()
        first_doc = get_readings_col().find_one({}, sort=[("timestamp", 1)])
        start_t = first_doc["timestamp"] if first_doc else datetime(2004, 3, 10, 18, 0, 0)
        self.set_clock(start_t)

    def _rebuild_rolling_state(self, clock: datetime) -> None:
        """Reconstruct in-memory rolling 24-hour windows for all sensors up to clock."""
        with self._lock:
            self._state.clear()
            t0 = clock - timedelta(hours=24)
            readings = list(get_readings_col().find(
                {"timestamp": {"$gt": t0, "$lte": clock}},
                {"sensor_id": 1, "value": 1, "timestamp": 1}
            ).sort("timestamp", 1))

            for doc in readings:
                s_id = doc["sensor_id"]
                val = doc.get("value")
                if s_id not in self._state:
                    self._state[s_id] = {
                        "window": [],
                        "recent_values": [],
                        "consecutive_nulls": 0,
                    }
                st = self._state[s_id]
                if val is None:
                    st["consecutive_nulls"] += 1
                else:
                    st["consecutive_nulls"] = 0
                    st["window"].append(val)
                    if len(st["window"]) > 24:
                        st["window"].pop(0)

                st["recent_values"].append(val)
                if len(st["recent_values"]) > 10:
                    st["recent_values"].pop(0)

    def step(self) -> None:
        """Advance sim clock by 1 hour and process arriving readings."""
        current_clock = self.get_clock()
        next_clock = current_clock + timedelta(hours=1)

        readings_col = get_readings_col()
        alerts_col = get_alerts_col()
        r = get_redis()

        docs = list(readings_col.find({"timestamp": next_clock}))
        if not docs:
            # Reached end of dataset, loop back or pause
            self.pause()
            return

        with self._lock:
            new_alerts = []
            for doc in docs:
                s_id = doc["sensor_id"]
                val = doc.get("value")
                if s_id not in self._state:
                    self._state[s_id] = {
                        "window": [],
                        "recent_values": [],
                        "consecutive_nulls": 0,
                    }
                st = self._state[s_id]
                if val is None:
                    st["consecutive_nulls"] += 1
                else:
                    st["consecutive_nulls"] = 0
                    st["window"].append(val)
                    if len(st["window"]) > 24:
                        st["window"].pop(0)

                st["recent_values"].append(val)
                if len(st["recent_values"]) > 10:
                    st["recent_values"].pop(0)

                alerts = evaluate_reading(
                    reading=doc,
                    rolling_window=st["window"],
                    consecutive_nulls=st["consecutive_nulls"],
                    recent_values=st["recent_values"],
                )
                if alerts:
                    new_alerts.extend(alerts)

            if new_alerts:
                alerts_col.insert_many(new_alerts, ordered=False)
                if r is not None:
                    try:
                        for al in new_alerts:
                            r.incr(f"alerts:count:{al['sensor_id']}")
                            # Push to recent alert feed (cap 50)
                            summary = {
                                "sensor_id": al["sensor_id"],
                                "timestamp": al["timestamp"].isoformat(),
                                "severity": al["severity"],
                                "type": al["type"],
                                "explanation": al["explanation"],
                            }
                            r.lpush("alerts:recent", json.dumps(summary))
                        r.ltrim("alerts:recent", 0, 49)
                    except Exception as e:
                        logger.debug("Redis error updating alerts counters: %s", e)

            # Invalidate cached latest values
            if r is not None:
                try:
                    for doc in docs:
                        r.delete(f"latest:{doc['sensor_id']}")
                except Exception:
                    pass

        self.set_clock(next_clock)

    def run_loop(self) -> None:
        """Main worker loop."""
        while True:
            if self.is_running():
                speed = self.get_speed()
                delay = 1.0 / max(1, speed)
                time.sleep(delay)
                try:
                    self.step()
                except Exception as e:
                    logger.error("Error in replay step: %s", e)
            else:
                time.sleep(0.2)

    def start_background(self) -> None:
        """Start replay loop in background thread."""
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self.run_loop, daemon=True)
            self._thread.start()

replay_engine = ReplayEngine()
