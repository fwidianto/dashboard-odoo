"""Production-grade sync health reporting and diagnostics module.

This module provides comprehensive reporting capabilities:
- Error classification (SCHEMA_ERROR, DATA_TOO_LONG, NUMERIC_OVERFLOW, etc.)
- Error aggregation by category and column
- Data profiling for observed values
- CSV and JSON export
- Sample record storage (up to 10 per error type)
- Schema recommendations with SQL migrations
- Final run reports with top issues
"""

from src.reporting.error_enums import ErrorCategory
from src.reporting.error_reporter import (
    ErrorRecord, 
    BatchErrorSummary, 
    SyncErrorReport, 
    ErrorReporter,
    DataProfile,
)
from src.reporting.schema_recommender import SchemaRecommender

__all__ = [
    "ErrorCategory",
    "ErrorRecord", 
    "BatchErrorSummary",
    "SyncErrorReport",
    "ErrorReporter",
    "DataProfile",
    "SchemaRecommender",
]
