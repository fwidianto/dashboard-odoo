"""Error reporting module for Odoo-PostgreSQL sync diagnostics.

This module provides production-grade error reporting and diagnostics including:
- Error classification (SCHEMA_ERROR, DATA_TOO_LONG, NUMERIC_OVERFLOW, etc.)
- Error aggregation by category
- CSV and JSON export
- Sample record storage
- Final run reports
"""

from src.reporting.error_enums import ErrorCategory
from src.reporting.error_reporter import ErrorRecord, BatchErrorSummary, SyncErrorReport, ErrorReporter

__all__ = [
    "ErrorCategory",
    "ErrorRecord", 
    "BatchErrorSummary",
    "SyncErrorReport",
    "ErrorReporter",
]
