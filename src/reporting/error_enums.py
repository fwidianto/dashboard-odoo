"""Error category classification for sync failures.

Each error category represents a distinct failure mode that can occur
during Odoo to PostgreSQL synchronization.
"""

from enum import Enum


class ErrorCategory(str, Enum):
    """
    Error categories for sync failures.
    
    These categories help identify the root cause of synchronization errors
    and guide remediation efforts.
    """
    
    # Schema-related errors
    SCHEMA_ERROR = "SCHEMA_ERROR"
    """Missing column, invalid type, or migration issue."""
    
    # Data length/size errors
    DATA_TOO_LONG = "DATA_TOO_LONG"
    """VARCHAR or text overflow - value exceeds column size."""
    
    # Numeric precision errors
    NUMERIC_OVERFLOW = "NUMERIC_OVERFLOW"
    """Precision exceeded or decimal overflow for numeric types."""
    
    # Constraint violations
    NULL_CONSTRAINT = "NULL_CONSTRAINT"
    """Attempt to insert NULL into a NOT NULL column."""
    
    FOREIGN_KEY = "FOREIGN_KEY"
    """Referenced foreign key does not exist."""
    
    UNIQUE_CONSTRAINT = "UNIQUE_CONSTRAINT"
    """Duplicate value violates unique constraint."""
    
    # Data validation errors specific to Odoo
    ODOO_DATA_ERROR = "ODOO_DATA_ERROR"
    """Invalid data format or business rule violation from Odoo."""
    
    # Catch-all for unclassified errors
    UNKNOWN = "UNKNOWN"
    """Error could not be classified."""
    
    @classmethod
    def classify_from_message(cls, error_message: str) -> "ErrorCategory":
        """
        Classify an error message into an ErrorCategory.
        
        Args:
            error_message: The raw error message from the database.
            
        Returns:
            The appropriate ErrorCategory for the error.
        """
        msg_lower = error_message.lower()
        
        # VARCHAR/text overflow
        if any(pattern in msg_lower for pattern in [
            "varchar",
            "character varying",
            "too long",
            "string length",
            "would be truncated",
            "value too long",
            "single-byte character possible",
            "right truncation",
            "string data right truncation",
        ]):
            return cls.DATA_TOO_LONG
        
        # Numeric precision errors
        if any(pattern in msg_lower for pattern in [
            "numeric",
            "precision",
            "scale",
            "overflow",
            "out of range",
            "decimal",
            "amount",
            "value out of range",
        ]):
            return cls.NUMERIC_OVERFLOW
        
        # NULL constraint violations
        if any(pattern in msg_lower for pattern in [
            "null",
            "not null",
            "cannot be null",
            "violates not-null",
        ]):
            return cls.NULL_CONSTRAINT
        
        # Foreign key violations
        if any(pattern in msg_lower for pattern in [
            "foreign key",
            "violates foreign key",
            "referenced key",
            "referential integrity",
        ]):
            return cls.FOREIGN_KEY
        
        # Unique constraint violations
        if any(pattern in msg_lower for pattern in [
            "unique",
            "duplicate",
            "violates unique",
            "already exists",
        ]):
            return cls.UNIQUE_CONSTRAINT
        
        # Schema errors
        if any(pattern in msg_lower for pattern in [
            "column",
            "does not exist",
            "relation",
            "table",
            "type",
            "invalid",
            "migration",
        ]):
            return cls.SCHEMA_ERROR
        
        # Odoo-specific data errors
        if any(pattern in msg_lower for pattern in [
            "odoo",
            "invalid",
            "malformed",
        ]):
            return cls.ODOO_DATA_ERROR
        
        return cls.UNKNOWN
    
    @classmethod
    def classify_from_exception(cls, exception: Exception) -> "ErrorCategory":
        """
        Classify an exception into an ErrorCategory.
        
        Args:
            exception: The exception to classify.
            
        Returns:
            The appropriate ErrorCategory for the exception.
        """
        return cls.classify_from_message(str(exception))
