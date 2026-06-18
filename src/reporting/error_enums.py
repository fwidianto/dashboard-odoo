"""Error category classification for sync failures."""

from enum import Enum
import re


class ErrorCategory(str, Enum):
    SCHEMA_ERROR = "SCHEMA_ERROR"
    DATA_TOO_LONG = "DATA_TOO_LONG"
    NUMERIC_OVERFLOW = "NUMERIC_OVERFLOW"
    NULL_CONSTRAINT = "NULL_CONSTRAINT"
    FOREIGN_KEY = "FOREIGN_KEY"
    UNIQUE_CONSTRAINT = "UNIQUE_CONSTRAINT"
    ODOO_DATA_ERROR = "ODOO_DATA_ERROR"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def classify_from_message(cls, error_message: str) -> "ErrorCategory":
        msg_lower = error_message.lower()

        # NULL constraint violations (PostgreSQL error codes: 23502)
        if any(p in msg_lower for p in ["23502", "null value", "not-null", "cannot be null"]):
            return cls.NULL_CONSTRAINT

        # VARCHAR/text overflow (PostgreSQL error codes: 22001, 22003)
        if any(p in msg_lower for p in ["22001", "22003", "varchar", "character varying",
                                          "too long for type", "string length", "would be truncated",
                                          "value too long", "right truncation", "integer out of range",
                                          "numeric field overflow"]):
            if "numeric" in msg_lower or "22003" in msg_lower:
                return cls.NUMERIC_OVERFLOW
            return cls.DATA_TOO_LONG

        # Numeric precision/overflow (PostgreSQL error codes: 22003, 22008)
        if any(p in msg_lower for p in ["22003", "22008", "numeric", "precision overflow",
                                         "decimal overflow", "interval overflow"]):
            return cls.NUMERIC_OVERFLOW

        # Foreign key violations (PostgreSQL error codes: 23503)
        if any(p in msg_lower for p in ["23503", "foreign key", "referenced key", "referential integrity"]):
            return cls.FOREIGN_KEY

        # Unique constraint violations (PostgreSQL error codes: 23505)
        if any(p in msg_lower for p in ["23505", "unique constraint", "duplicate key", "already exists"]):
            return cls.UNIQUE_CONSTRAINT

        # Schema errors - table/column doesn't exist (PostgreSQL error codes: 42P01, 42703)
        if any(p in msg_lower for p in ["42p01", "42703", "does not exist", "undefined column"]):
            return cls.SCHEMA_ERROR

        # Data errors from Odoo or encoding issues
        if any(p in msg_lower for p in ["malformed", "invalid encoding", "bytea", "encoding"]):
            return cls.ODOO_DATA_ERROR

        # Check for any PostgreSQL error code in format (12345)
        error_code_match = re.search(r'\(([0-9A-Z]{5})\)', error_message)
        if error_code_match:
            code = error_code_match.group(1)
            # Class 22: Data Exception
            if code.startswith("22"):
                if code in ["22001"]:
                    return cls.DATA_TOO_LONG
                if code in ["22003", "22008"]:
                    return cls.NUMERIC_OVERFLOW
            # Class 23: Integrity Constraint Violation
            if code.startswith("23"):
                if code == "23502":
                    return cls.NULL_CONSTRAINT
                if code == "23503":
                    return cls.FOREIGN_KEY
                if code == "23505":
                    return cls.UNIQUE_CONSTRAINT
            # Class 42: Syntax Error or Access Rule Violation
            if code.startswith("42"):
                return cls.SCHEMA_ERROR

        return cls.UNKNOWN

    @classmethod
    def classify_from_exception(cls, exception: Exception) -> "ErrorCategory":
        return cls.classify_from_message(str(exception))
