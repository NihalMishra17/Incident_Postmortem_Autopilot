"""Redis client initialization for postmortem caching."""
import os
import redis


def get_redis_client():
    """Returns a Redis client with connection pooling configured from env (REDIS_HOST, REDIS_PORT, REDIS_PASSWORD)."""
    host = os.environ.get("REDIS_HOST", "localhost")
    port = int(os.environ.get("REDIS_PORT", "6379"))
    password = os.environ.get("REDIS_PASSWORD")
    password = password if password else None

    return redis.Redis(
        host=host,
        port=port,
        password=password,
        decode_responses=True,
        max_connections=10,
        socket_timeout=5.0,
        socket_connect_timeout=5.0,
    )
