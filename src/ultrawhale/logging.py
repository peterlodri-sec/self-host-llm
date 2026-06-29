# SPDX-License-Identifier: MIT
"""Shared structured logging for the Ultrawhale pipeline.

Provides JSON-structured and human-readable log output with consistent
timestamp, level, and component tagging across all modules.
"""

import json
import logging
import sys
from datetime import UTC, datetime


class _StructuredFormatter(logging.Formatter):
    """JSON-structured log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "component": getattr(record, "component", "ultrawhale"),
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            payload["exc"] = str(record.exc_info[1])
        return json.dumps(payload, default=str)


class _HumanFormatter(logging.Formatter):
    """Human-readable log formatter with color.

    Format: [HH:MM:SS] LEVEL component message
    """

    COLORS = {
        "DEBUG": "\033[2;37m",  # dim white
        "INFO": "\033[0m",  # default
        "WARNING": "\033[1;33m",  # yellow
        "ERROR": "\033[1;31m",  # red
        "CRITICAL": "\033[1;35m",  # magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now().strftime("%H:%M:%S")
        level = record.levelname
        component = getattr(record, "component", "ultrawhale")
        color = self.COLORS.get(level, "")
        msg = record.getMessage()
        return f"[{ts}] {color}{level:<7}{self.RESET} [{component}] {msg}"


def setup_logging(
    level: int = logging.INFO,
    json_mode: bool = False,
    component: str | None = None,
) -> logging.Logger:
    """Configure and return the root Ultrawhale logger.

    Args:
        level: Logging level (default INFO).
        json_mode: If True, emit JSON-structured logs (for log aggregation).
                   If False, emit human-readable colorized logs.
        component: Optional component tag for this logger instance.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger("ultrawhale")
    logger.setLevel(level)
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)

    if json_mode:
        handler.setFormatter(_StructuredFormatter())
    else:
        handler.setFormatter(_HumanFormatter())

    logger.addHandler(handler)

    if component:
        child = logging.getLogger(f"ultrawhale.{component}")
        child.setLevel(level)
        child.handlers.clear()
        child.addHandler(handler)
        child.propagate = False  # Don't bubble to root (avoids double logging)

        # Use a filter rather than LogRecordFactory for component tagging
        component_filter = _ComponentFilter(component)
        child.filters = [f for f in child.filters if not isinstance(f, _ComponentFilter)]
        child.addFilter(component_filter)

    return logger


def get_logger(component: str) -> logging.Logger:
    """Get a logger for a specific pipeline component.

    Args:
        component: Component name (e.g., 'generate', 'orchestrator', 'upload').

    Returns:
        Logger with the component tag pre-set.
    """
    logger = logging.getLogger(f"ultrawhale.{component}")
    # If component was explicitly set up (propagate=False), keep its own handler.
    # Otherwise, rely on root propagation for output.
    if not logger.handlers and not logger.propagate:
        # logger was set up but handlers got cleared — re-attach to root
        root = logging.getLogger("ultrawhale")
        if root.handlers:
            logger.handlers = root.handlers
            logger.setLevel(root.level)

    # Attach component via log record filter
    component_filter = _ComponentFilter(component)
    logger.filters = [f for f in logger.filters if not isinstance(f, _ComponentFilter)]
    logger.addFilter(component_filter)
    return logger


class _ComponentFilter(logging.Filter):
    """Inject component name into log records."""

    def __init__(self, component: str):
        super().__init__()
        self.component = component

    def filter(self, record: logging.LogRecord) -> bool:
        record.component = self.component
        return True
