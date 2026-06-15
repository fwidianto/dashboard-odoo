"""Logging configuration using structlog for structured logging."""

import logging
import sys
from pathlib import Path
from typing import Optional, Any

import structlog


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
) -> structlog.BoundLogger:
    """
    Configure structured logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Optional path to log file.

    Returns:
        Configured structlog logger.
    """
    # Convert string level to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Console renderer with colors
    def console_render(logger: Any, method_name: str, event_dict: dict) -> str:
        """Simple console renderer."""
        timestamp = event_dict.pop("timestamp", "")
        level = event_dict.pop("level", method_name.upper())
        msg = event_dict.pop("event", "")
        
        parts = []
        if timestamp:
            parts.append(timestamp[:19])
        parts.append(f"[{level:8}]")
        parts.append(msg)
        
        # Add remaining fields
        for key, value in event_dict.items():
            if key not in ("logger", "exception"):
                parts.append(f"{key}={value}")
        
        # Handle exception
        exc = event_dict.get("exception")
        if exc:
            parts.append(f"\n{exc}")
        
        return " ".join(parts)

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            console_render,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard logging
    handlers: list[logging.Handler] = []

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    handlers.append(console_handler)

    # File handler if specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(numeric_level)
        handlers.append(file_handler)

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add new handlers
    for handler in handlers:
        formatter = logging.Formatter("%(message)s")
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    logger = structlog.get_logger("odoo_sync")
    return logger


def get_logger(name: Optional[str] = None) -> structlog.stdlib.BoundLogger:
    """
    Get a logger instance.

    Args:
        name: Optional logger name suffix.

    Returns:
        Configured structlog logger.
    """
    if name:
        return structlog.get_logger(f"odoo_sync.{name}")
    return structlog.get_logger("odoo_sync")