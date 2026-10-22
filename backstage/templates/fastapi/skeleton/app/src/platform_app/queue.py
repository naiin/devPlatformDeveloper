from functools import lru_cache

from redis import Redis

from platform_app.config import settings


@lru_cache
def redis_client() -> Redis:
    return Redis.from_url(
        settings().redis_url,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=5,
        health_check_interval=15,
    )
