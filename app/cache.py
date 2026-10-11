import json
import logging
from typing import Any, Callable, Dict, Optional
import redis
from redis.exceptions import RedisError
from app.config import REDIS_URL, CACHE_TTL_SECONDS

logger = logging.getLogger(__name__)

_redis_client: Optional[redis.Redis] = None

def get_redis() -> Optional[redis.Redis]:
    """Get or initialize Redis client connection."""
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_timeout=1.0,
                socket_connect_timeout=1.0
            )
            # Ping to verify
            _redis_client.ping()
        except Exception as e:
            logger.warning("Redis not available (%s). Caching disabled, falling back to DB.", e)
            _redis_client = None
    return _redis_client

def is_redis_available() -> bool:
    """Check if Redis connection is active."""
    try:
        r = get_redis()
        return r is not None and r.ping()
    except Exception:
        return False

def cached(key: str, ttl: int = CACHE_TTL_SECONDS, loader: Optional[Callable[[], Any]] = None) -> Any:
    """
    Cache-aside wrapper per TECHNICAL.md section 5.8:
    - Attempt to fetch key from Redis.
    - If hit: increment cache:hits and return deserialized JSON.
    - If miss / Redis down: increment cache:misses, execute loader(), setex, return result.
    """
    r = get_redis()
    if r is not None:
        try:
            val = r.get(key)
            if val is not None:
                r.incr("cache:hits")
                return json.loads(val)
        except RedisError as e:
            logger.debug("Redis error on GET: %s. Falling back to loader.", e)

    # Cache miss or Redis unavailable
    if r is not None:
        try:
            r.incr("cache:misses")
        except RedisError:
            pass

    if loader is None:
        return None

    result = loader()

    # Save to Redis if available
    if r is not None and result is not None:
        try:
            r.setex(key, ttl, json.dumps(result, default=str))
        except RedisError as e:
            logger.debug("Redis error on SETEX: %s", e)

    return result

def get_cache_stats() -> Dict[str, Any]:
    """Return cache hit and miss counters and status for the UI KPI."""
    r = get_redis()
    if r is None:
        return {"online": False, "hits": 0, "misses": 0, "ratio": 0.0}
    try:
        hits = int(r.get("cache:hits") or 0)
        misses = int(r.get("cache:misses") or 0)
        total = hits + misses
        ratio = (hits / total * 100.0) if total > 0 else 0.0
        return {"online": True, "hits": hits, "misses": misses, "ratio": round(ratio, 1)}
    except RedisError:
        return {"online": False, "hits": 0, "misses": 0, "ratio": 0.0}

def invalidate_cache(pattern: str) -> None:
    """Invalidate cache keys matching a pattern."""
    r = get_redis()
    if r is None:
        return
    try:
        keys = r.keys(pattern)
        if keys:
            r.delete(*keys)
    except RedisError as e:
        logger.debug("Error invalidating cache pattern %s: %s", pattern, e)
