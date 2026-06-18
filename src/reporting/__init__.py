"""Production-grade sync health reporting and diagnostics module.

This module provides comprehensive reporting capabilities:
- Root cause detection (only first real error is logged)
- Cascade failure tracking (TRANSACTION_ABORTED counted separately)
- Per-record transaction isolation
- JSON and CSV export
"""

from src.reporting.error_enums import ErrorCategory
from src.reporting.error_reporter import (
    RootCauseError,
    ModelErrorStats,
    ErrorReporter,
)

__all__ = [
    "ErrorCategory",
    "RootCauseError",
    "ModelErrorStats",
    "ErrorReporter",
]
