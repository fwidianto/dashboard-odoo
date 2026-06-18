"""Error category classification for sync failures."""

from enum import Enum


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

        # NULL constraint
        if any(p in msg_lower for p in ["violates not-null constraint", "cannot be null", "null value in column"]):
            return cls.NULL_CONSTRAINT

        # VARCHAR/text overflow
        if any(p in msg_lower for p in ["varchar", "character varying", "too long for type", 
                                          "string length", "would be truncated", "value too long",
                                          "right truncation", "string data right truncation"]):
            return cls.DATA_TOO_LONG

        # Numeric precision/overflow
        if any(p in msg_lower for p in ["numeric", "precision overflow", "decimal overflow", 
                                         "value out of range", "interval overflow"]):
            return cls.NUMERIC_OVERFLOW

        # Foreign key
        if any(p in msg_lower for p in ["foreign key constraint", "violates foreign key constraint",
                                         "referenced key", "referential integrity"]):
            return cls.FOREIGN_KEY

        # Unique constraint
        if any(p in msg_lower for p in ["violates unique constraint", "duplicate key",
                                         "already exists", "unique constraint"]):
            return cls.UNIQUE_CONSTRAINT

        # Schema errors - table/column doesn't exist
        if any(p in msg_lower for p in ["does not exist"]):
            return cls.SCHEMA_ERROR

        # Odoo-specific data errors (special characters, encoding, etc.)
        if any(p in msg_lower for p in ["malformed", "invalid encoding", "character", "bytea"]):
            return cls.ODOO_DATA_ERROR

        return cls.UNKNOWN

    @classmethod
    def classify_from_exception(cls, exception: Exception) -> "ErrorCategory":
        return cls.classify_from_message(str(exception))
