import json
import logging
import sys
import pytest
import structlog
from io import StringIO
from unittest.mock import patch


def test_configure_logging_sets_structlog():
    """configure_logging should configure structlog with JSON processors."""
    # Import the module (which auto-calls configure_logging)
    import logging_config

    # Verify structlog is configured
    assert structlog.is_configured()


def test_logging_produces_json_output():
    """Logging after importing logging_config should produce JSON-parseable output."""
    # Import logging_config (configures structlog)
    import logging_config

    # Capture stdout
    captured_output = StringIO()

    # Create a logger and add a handler that writes to our captured output
    logger = logging.getLogger("test_json_logger")
    logger.handlers = []  # Clear existing handlers
    handler = logging.StreamHandler(captured_output)
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    # Use structlog to wrap the logger
    struct_logger = structlog.wrap_logger(logger)

    # Log a message
    struct_logger.info("test message", key1="value1", key2=42)

    # Get the output
    output = captured_output.getvalue()

    # Verify it's valid JSON
    assert output.strip(), "Output should not be empty"
    try:
        log_entry = json.loads(output.strip())
        assert "event" in log_entry
        assert log_entry["event"] == "test message"
        assert "key1" in log_entry
        assert log_entry["key1"] == "value1"
        assert "key2" in log_entry
        assert log_entry["key2"] == 42
    except json.JSONDecodeError as e:
        pytest.fail(f"Output is not valid JSON: {output}\nError: {e}")


def test_configure_logging_idempotent():
    """Calling configure_logging multiple times should not raise an error."""
    import logging_config

    # Call configure_logging again (it was already called on import)
    try:
        logging_config.configure_logging()
        logging_config.configure_logging()
    except Exception as e:
        pytest.fail(f"configure_logging should be idempotent but raised: {e}")


def test_logging_includes_timestamp():
    """Logged output should include an ISO timestamp."""
    import logging_config

    captured_output = StringIO()
    logger = logging.getLogger("test_timestamp_logger")
    logger.handlers = []
    handler = logging.StreamHandler(captured_output)
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    struct_logger = structlog.wrap_logger(logger)
    struct_logger.info("timestamp test")

    output = captured_output.getvalue().strip()
    log_entry = json.loads(output)

    assert "timestamp" in log_entry, "Log entry should include a timestamp field"


def test_logging_includes_log_level():
    """Logged output should include the log level."""
    import logging_config

    captured_output = StringIO()
    logger = logging.getLogger("test_level_logger")
    logger.handlers = []
    handler = logging.StreamHandler(captured_output)
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    struct_logger = structlog.wrap_logger(logger)
    struct_logger.info("level test")

    output = captured_output.getvalue().strip()
    log_entry = json.loads(output)

    assert "level" in log_entry, "Log entry should include a level field"
    assert log_entry["level"] == "info"


def test_logging_includes_logger_name():
    """Logged output should include the logger name."""
    import logging_config

    captured_output = StringIO()
    logger_name = "test_name_logger"
    logger = logging.getLogger(logger_name)
    logger.handlers = []
    handler = logging.StreamHandler(captured_output)
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    struct_logger = structlog.wrap_logger(logger)
    struct_logger.info("logger name test")

    output = captured_output.getvalue().strip()
    log_entry = json.loads(output)

    assert "logger" in log_entry, "Log entry should include a logger field"
    assert log_entry["logger"] == logger_name
