"""Initialize structured JSON logging via structlog.

This module must be imported first in api/main.py and agents/pipeline.py
to configure the logging pipeline before any loggers are instantiated.
All logs are emitted as JSON to stdout for container aggregation.
"""
import logging
import sys
import structlog


def configure_logging() -> None:
    """Configure structlog with JSON renderer and stdlib integration.

    Sets up structured logging with ISO timestamps, exception formatting,
    and stdlib logger factory. All output flows through LoggerFactory to
    enable both structlog and standard logging.getLogger() calls to emit JSON.
    """
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        stream=sys.stdout,
    )


configure_logging()
