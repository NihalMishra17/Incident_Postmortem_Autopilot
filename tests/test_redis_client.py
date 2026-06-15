import os
import pytest
from unittest.mock import patch, MagicMock
import redis
from redis.exceptions import ConnectionError as RedisConnectionError

from infra.redis_client import get_redis_client


def test_get_redis_client_returns_redis_instance():
    """get_redis_client should return a Redis instance."""
    with patch("infra.redis_client.redis.Redis") as mock_redis:
        mock_redis.return_value = MagicMock()
        client = get_redis_client()

        mock_redis.assert_called_once()
        assert client is not None


def test_get_redis_client_uses_env_vars():
    """get_redis_client should use REDIS_HOST, REDIS_PORT, REDIS_PASSWORD from env."""
    with patch.dict(os.environ, {
        "REDIS_HOST": "redis.example.com",
        "REDIS_PORT": "6380",
        "REDIS_PASSWORD": "secret123"
    }):
        with patch("infra.redis_client.redis.Redis") as mock_redis:
            get_redis_client()

            mock_redis.assert_called_once_with(
                host="redis.example.com",
                port=6380,
                password="secret123",
                decode_responses=True,
                max_connections=10,
                socket_timeout=5.0,
                socket_connect_timeout=5.0,
            )


def test_get_redis_client_connection_error():
    """get_redis_client should propagate ConnectionError from Redis constructor."""
    with patch("infra.redis_client.redis.Redis") as mock_redis:
        mock_redis.side_effect = RedisConnectionError("Connection refused")

        with pytest.raises(RedisConnectionError, match="Connection refused"):
            get_redis_client()


def test_get_redis_client_no_password():
    """get_redis_client should pass password=None when REDIS_PASSWORD not set."""
    with patch.dict(os.environ, {
        "REDIS_HOST": "localhost",
        "REDIS_PORT": "6379",
    }, clear=True):
        # Remove REDIS_PASSWORD from env if it exists
        os.environ.pop("REDIS_PASSWORD", None)

        with patch("infra.redis_client.redis.Redis") as mock_redis:
            get_redis_client()

            call_kwargs = mock_redis.call_args[1]
            assert call_kwargs["password"] is None
