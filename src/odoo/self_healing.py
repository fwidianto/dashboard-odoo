"""Self-Healing Sync Engine Module.

This module provides automatic error detection, classification, isolation, and recovery
for the Odoo to PostgreSQL sync process.

Key Features:
- Root Cause Detection: Extract original PostgreSQL errors from cascading exceptions
- Savepoint-Based Isolation: Each record is isolated; one failure doesn't stop batch
- Automatic Schema Repair: Auto-add missing columns, migrate types, fix constraints
- Adaptive Learning: Learn from past errors and apply fixes proactively
- Production Safety: Only safe operations (CREATE, ADD, ALTER TYPE, DROP NOT NULL)

Safety Rules:
ALLOWED (auto):
  ✅ CREATE TABLE
  ✅ ADD COLUMN
  ✅ ALTER COLUMN TYPE
  ✅ DROP NOT NULL
  ✅ CREATE INDEX

FORBIDDEN (never auto):
  ❌ DROP TABLE
  ❌ DROP COLUMN
  ❌ DELETE DATA
  ❌ TRUNCATE TABLE
"""

import re
import traceback
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any, Callable, TYPE_CHECKING
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.utils.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection
    from src.clients.postgres_client import PostgresClient


class RootCauseType(Enum):
    """PostgreSQL error root cause types."""
    
    # Schema errors
    UNDEFINED_COLUMN = "UndefinedColumn"           # Column doesn't exist
    UNDEFINED_TABLE = "UndefinedTable"             # Table doesn't exist
    UNDEFINED_FUNCTION = "UndefinedFunction"        # Function doesn't exist
    
    # Type mismatch errors
    DATATYPE_MISMATCH = "DatatypeMismatch"         # Wrong type for column
    STRING_DATA_RIGHT_TRUNCATION = "StringDataRightTruncation"  # VARCHAR overflow
    NUMERIC_VALUE_OUT_OF_RANGE = "NumericValueOutOfRange"      # NUMERIC overflow
    INVALID_TEXT_REPRESENTATION = "InvalidTextRepresentation"  # Can't parse text as type
    
    # Constraint errors
    NOT_NULL_VIOLATION = "NotNullViolation"         # NULL in NOT NULL column
    FOREIGN_KEY_VIOLATION = "ForeignKeyViolation"  # FK constraint failed
    UNIQUE_VIOLATION = "UniqueViolation"           # Duplicate key
    CHECK_VIOLATION = "CheckViolation"             # CHECK constraint failed
    
    # Transaction errors
    DEADLOCK_DETECTED = "DeadlockDetected"
    LOCK_NOT_AVAILABLE = "LockNotAvailable"
    
    # Connection errors
    CONNECTION_ERROR = "ConnectionError"
    
    # Unknown
    UNKNOWN = "Unknown"


# Maximum auto-fix attempts per record
MAX_AUTO_FIX_ATTEMPTS = 3


@dataclass
class RootCause:
    """Represents the root cause of an error."""
    
    type: RootCauseType
    message: str
    column_name: Optional[str] = None
    table_name: Optional[str] = None
    constraint_name: Optional[str] = None
    original_exception: Optional[Exception] = None
    
    def __str__(self) -> str:
        parts = [self.type.value]
        if self.column_name:
            parts.append(f"column={self.column_name}")
        if self.table_name:
            parts.append(f"table={self.table_name}")
        return f"RootCause({' '.join(parts)})"


@dataclass
class ErrorPattern:
    """Represents a learned error pattern and its fix."""
    
    model: str
    table: str
    field: str
    error_type: RootCauseType
    fix_applied: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    occurrences: int = 1
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "model": self.model,
            "table": self.table,
            "field": self.field,
            "error_type": self.error_type.value,
            "fix_applied": self.fix_applied,
            "timestamp": self.timestamp.isoformat(),
            "occurrences": self.occurrences,
        }


@dataclass
class ErrorSample:
    """Sample error for debugging."""
    
    model: str
    table: str
    record_id: Any
    field: Optional[str]
    error_type: RootCauseType
    error_message: str
    value_preview: Optional[str]
    sql: Optional[str] = None
    stack_trace: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "model": self.model,
            "table": self.table,
            "record_id": str(self.record_id),
            "field": self.field,
            "error_type": self.error_type.value,
            "error_message": self.error_message[:500],
            "value_preview": self.value_preview[:200] if self.value_preview else None,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class RepairResult:
    """Result of a repair attempt."""
    
    success: bool
    repair_type: str
    details: dict = field(default_factory=dict)
    record_retried: bool = False
    record_success: bool = False


class SelfHealingEngine:
    """
    Self-healing engine for sync operations.
    
    This engine:
    1. Detects root causes of PostgreSQL errors
    2. Isolates record failures using savepoints
    3. Automatically repairs schema issues
    4. Learns from past errors
    5. Retries records after repairs
    
    Usage:
        engine = SelfHealingEngine(pg_client, odoo_client)
        result = engine.upsert_with_healing(
            table_name="product_template",
            records=[...],
            primary_key_column="id",
            model="product.template",
        )
    """
    
    def __init__(
        self,
        postgres_client: "PostgresClient",
        odoo_client: Optional[Any] = None,
    ):
        """
        Initialize self-healing engine.
        
        Args:
            postgres_client: Connected PostgresClient.
            odoo_client: Optional OdooClient for metadata.
        """
        self._pg = postgres_client
        self._odoo = odoo_client
        self._logger = get_logger("self_healing")
        
        # Error patterns learned from past fixes
        self._error_patterns: dict[str, ErrorPattern] = {}
        
        # Error samples (max 100 per type)
        self._error_samples: dict[RootCauseType, list[ErrorSample]] = {
            rt: [] for rt in RootCauseType
        }
        self._max_samples = 100
        
        # Track repairs for reporting
        self._repairs_made: list[dict] = []
        
        # Initialize error patterns table
        self._init_error_patterns_table()
    
    def _init_error_patterns_table(self) -> None:
        """Create sync_error_patterns table if not exists."""
        sql = text("""
            CREATE TABLE IF NOT EXISTS sync_error_patterns (
                id SERIAL PRIMARY KEY,
                model VARCHAR(128) NOT NULL,
                table_name VARCHAR(128) NOT NULL,
                field VARCHAR(128) NOT NULL,
                error_type VARCHAR(64) NOT NULL,
                fix_applied VARCHAR(256) NOT NULL,
                occurrences INTEGER DEFAULT 1,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(model, field, error_type)
            )
        """)
        
        try:
            with self._pg.engine.connect() as conn:
                conn.execute(sql)
                conn.commit()
        except Exception as e:
            self._logger.warning("Could not create sync_error_patterns table", error=str(e))
    
    # =========================================================================
    # PHASE 1: ROOT CAUSE DETECTION
    # =========================================================================
    
    def find_root_cause(self, exception: Exception) -> RootCause:
        """
        Extract the root cause from a possibly cascaded exception.
        
        PostgreSQL errors often come wrapped in SQLAlchemy/SQL exceptions.
        This method unwraps them to find the actual PostgreSQL error.
        
        Args:
            exception: The exception to analyze.
            
        Returns:
            RootCause with the underlying error type and details.
        """
        # Extract original PostgreSQL error
        original_msg = self._extract_original_message(exception)
        
        # Classify the error
        return self._classify_error(original_msg, exception)
    
    def _extract_original_message(self, exception: Exception) -> str:
        """Extract the original PostgreSQL error message."""
        msg = str(exception)
        
        # Check for psycopg2 errors (common in PostgreSQL)
        if hasattr(exception, 'pgcode'):
            # psycopg2 error
            return f"{exception.pgcode}: {exception.diag.message_primary or msg}"
        
        # Check for SQLAlchemy errors with orig
        if hasattr(exception, 'orig') and exception.orig:
            orig = exception.orig
            if hasattr(orig, 'pgcode'):
                return f"{orig.pgcode}: {orig.diag.message_primary if hasattr(orig, 'diag') else str(orig)}"
            return str(orig)
        
        # Check exception chain
        current = exception.__cause__
        while current:
            if hasattr(current, 'pgcode'):
                return f"{current.pgcode}: {str(current)}"
            current = current.__cause__
        
        # Check __context__
        current = exception.__context__
        while current:
            if hasattr(current, 'pgcode'):
                return f"{current.pgcode}: {str(current)}"
            current = current.__context__
        
        return msg
    
    def _classify_error(self, message: str, original: Exception) -> RootCause:
        """Classify error message into RootCauseType."""
        msg_lower = message.lower()
        
        # NULL constraint violation - check BEFORE general "null" checks
        if any(p in msg_lower for p in ['null value', 'not-null constraint', 'violates not-null']):
            col_match = re.search(r'column\s+"(\w+)"', message, re.IGNORECASE)
            return RootCause(
                type=RootCauseType.NOT_NULL_VIOLATION,
                message=message,
                column_name=col_match.group(1) if col_match else None,
                original_exception=original,
            )
        
        # String truncation - check BEFORE general checks
        if any(p in msg_lower for p in [
            'string data right truncation', 'value too long', 'varchar',
            'character varying', 'would be truncated', 'right truncation'
        ]):
            col_match = re.search(r'column\s+"(\w+)"', message, re.IGNORECASE)
            return RootCause(
                type=RootCauseType.STRING_DATA_RIGHT_TRUNCATION,
                message=message,
                column_name=col_match.group(1) if col_match else None,
                original_exception=original,
            )
        
        # Numeric overflow - check BEFORE general overflow
        if any(p in msg_lower for p in [
            'numeric value out of range', 'numeric field overflow', 'precision'
        ]):
            col_match = re.search(r'column\s+"(\w+)"', message, re.IGNORECASE)
            return RootCause(
                type=RootCauseType.NUMERIC_VALUE_OUT_OF_RANGE,
                message=message,
                column_name=col_match.group(1) if col_match else None,
                original_exception=original,
            )
        
        # Schema errors - Column doesn't exist - check AFTER specific checks
        if 'column "' in msg_lower and 'does not exist' in msg_lower:
            col_match = re.search(r'column\s+"(\w+)"', message, re.IGNORECASE)
            return RootCause(
                type=RootCauseType.UNDEFINED_COLUMN,
                message=message,
                column_name=col_match.group(1) if col_match else None,
                original_exception=original,
            )
        
        # Table doesn't exist
        if 'relation "' in msg_lower or 'table "' in msg_lower:
            return RootCause(
                type=RootCauseType.UNDEFINED_TABLE,
                message=message,
                original_exception=original,
            )
        
        # Type mismatch
        if any(p in msg_lower for p in [
            'datatype mismatch', 'cannot be cast', 'cannot cast', 'invalid input syntax'
        ]):
            col_match = re.search(r'column\s+"(\w+)"', message, re.IGNORECASE)
            return RootCause(
                type=RootCauseType.DATATYPE_MISMATCH,
                message=message,
                column_name=col_match.group(1) if col_match else None,
                original_exception=original,
            )
        
        # String truncation
        if any(p in msg_lower for p in [
            'string data right truncation', 'value too long', 'varchar',
            'character varying', 'would be truncated', 'right truncation'
        ]):
            col_match = re.search(r'column\s+"(\w+)"', message, re.IGNORECASE)
            return RootCause(
                type=RootCauseType.STRING_DATA_RIGHT_TRUNCATION,
                message=message,
                column_name=col_match.group(1) if col_match else None,
                original_exception=original,
            )
        
        # Numeric overflow
        if any(p in msg_lower for p in [
            'numeric value out of range', 'numeric field overflow',
            'precision', 'out of range'
        ]):
            col_match = re.search(r'column\s+"(\w+)"', message, re.IGNORECASE)
            return RootCause(
                type=RootCauseType.NUMERIC_VALUE_OUT_OF_RANGE,
                message=message,
                column_name=col_match.group(1) if col_match else None,
                original_exception=original,
            )
        
        # NULL constraint violation
        if any(p in msg_lower for p in [
            'null value', 'not-null constraint', 'violates not-null'
        ]):
            col_match = re.search(r'column\s+"(\w+)"', message, re.IGNORECASE)
            return RootCause(
                type=RootCauseType.NOT_NULL_VIOLATION,
                message=message,
                column_name=col_match.group(1) if col_match else None,
                original_exception=original,
            )
        
        # Foreign key violation
        if any(p in msg_lower for p in [
            'foreign key', 'violates foreign key', 'referenced key'
        ]):
            return RootCause(
                type=RootCauseType.FOREIGN_KEY_VIOLATION,
                message=message,
                original_exception=original,
            )
        
        # Unique violation
        if any(p in msg_lower for p in [
            'unique constraint', 'duplicate key', 'violates unique'
        ]):
            return RootCause(
                type=RootCauseType.UNIQUE_VIOLATION,
                message=message,
                original_exception=original,
            )
        
        # Deadlock
        if 'deadlock' in msg_lower:
            return RootCause(
                type=RootCauseType.DEADLOCK_DETECTED,
                message=message,
                original_exception=original,
            )
        
        # Connection error
        if any(p in msg_lower for p in [
            'connection refused', 'could not connect', 'timeout'
        ]):
            return RootCause(
                type=RootCauseType.CONNECTION_ERROR,
                message=message,
                original_exception=original,
            )
        
        # Unknown
        return RootCause(
            type=RootCauseType.UNKNOWN,
            message=message,
            original_exception=original,
        )
    
    # =========================================================================
    # PHASE 2: SAVEPOINT-BASED ISOLATION
    # =========================================================================
    
    def upsert_with_healing(
        self,
        table_name: str,
        records: list[dict],
        primary_key_column: str,
        model: Optional[str] = None,
        odoo_fields: Optional[dict] = None,
    ) -> dict:
        """
        Upsert records with self-healing capabilities.
        
        Each record is processed in its own savepoint. Failures are isolated
        and repairs are attempted automatically.
        
        Args:
            table_name: Target PostgreSQL table.
            records: List of records to upsert.
            primary_key_column: Primary key column name.
            model: Odoo model name (for metadata lookup).
            odoo_fields: Odoo field definitions (if known).
            
        Returns:
            Dict with upsert results and statistics.
        """
        results = {
            "inserted": 0,
            "updated": 0,
            "errors": 0,
            "auto_fixed": 0,
            "record_failures": [],
        }
        
        with self._pg.engine.connect() as conn:
            for record in records:
                savepoint_name = f"sp_{hashlib.md5(str(record).encode()).hexdigest()[:8]}"
                
                try:
                    # Create savepoint
                    conn.execute(text(f"SAVEPOINT {savepoint_name}"))
                    
                    # Try to upsert
                    inserted, updated = self._upsert_single(conn, table_name, record, primary_key_column)
                    
                    # Success
                    results["inserted"] += inserted
                    results["updated"] += updated
                    
                except SQLAlchemyError as e:
                    # Record failed - rollback to savepoint
                    conn.execute(text(f"ROLLBACK TO SAVEPOINT {savepoint_name}"))
                    
                    # Find root cause
                    root_cause = self.find_root_cause(e)
                    
                    # Try to repair
                    repair_result = self._attempt_repair(
                        conn=conn,
                        table_name=table_name,
                        record=record,
                        primary_key_column=primary_key_column,
                        root_cause=root_cause,
                        model=model,
                        odoo_fields=odoo_fields,
                        savepoint_name=savepoint_name,
                    )
                    
                    if repair_result.success:
                        if repair_result.record_retried:
                            if repair_result.record_success:
                                results["inserted"] += 1
                                results["auto_fixed"] += 1
                            else:
                                results["errors"] += 1
                                results["record_failures"].append({
                                    "record_id": record.get(primary_key_column),
                                    "root_cause": root_cause.type.value,
                                    "message": root_cause.message,
                                })
                        else:
                            # Schema repair didn't require retry
                            results["auto_fixed"] += 1
                    else:
                        results["errors"] += 1
                        results["record_failures"].append({
                            "record_id": record.get(primary_key_column),
                            "root_cause": root_cause.type.value,
                            "message": root_cause.message,
                        })
                        
                        # Store error sample
                        self._store_error_sample(
                            model=model or table_name,
                            table=table_name,
                            record_id=record.get(primary_key_column),
                            field=root_cause.column_name,
                            error=root_cause,
                            value=record.get(root_cause.column_name) if root_cause.column_name else None,
                        )
                finally:
                    # Release savepoint (always happens)
                    try:
                        conn.execute(text(f"RELEASE SAVEPOINT {savepoint_name}"))
                    except Exception:
                        pass
        
        return results
    
    def _upsert_single(
        self,
        conn: "Connection",
        table_name: str,
        record: dict,
        primary_key_column: str,
    ) -> tuple[int, int]:
        """Execute single record upsert."""
        columns = list(record.keys())
        insert_cols = ", ".join(f'"{c}"' for c in columns)
        placeholders = ", ".join(f":{c}" for c in columns)
        update_cols = ", ".join(
            f'"{c}" = EXCLUDED."{c}"' for c in columns if c != primary_key_column
        )
        
        sql = text(f"""
            INSERT INTO "{table_name}" ({insert_cols})
            VALUES ({placeholders})
            ON CONFLICT ("{primary_key_column}") DO UPDATE SET {update_cols}
            RETURNING "{primary_key_column}", xmax
        """)
        
        result = conn.execute(sql, record)
        row = result.fetchone()
        
        if row and row[1] == 0:
            return 1, 0
        return 0, 1
    
    # =========================================================================
    # PHASE 3-5: AUTOMATIC REPAIR
    # =========================================================================
    
    def _attempt_repair(
        self,
        conn: "Connection",
        table_name: str,
        record: dict,
        primary_key_column: str,
        root_cause: RootCause,
        model: Optional[str],
        odoo_fields: Optional[dict],
        savepoint_name: str,
        attempt: int = 0,
    ) -> RepairResult:
        """
        Attempt to repair a failure.
        
        Args:
            conn: Database connection.
            table_name: Target table.
            record: Record that failed.
            primary_key_column: PK column name.
            root_cause: Identified error type.
            model: Odoo model name.
            odoo_fields: Odoo field definitions.
            savepoint_name: Savepoint to retry at.
            attempt: Current repair attempt number.
            
        Returns:
            RepairResult with success status.
        """
        if attempt >= MAX_AUTO_FIX_ATTEMPTS:
            self._logger.warning(
                "Max repair attempts reached",
                table=table_name,
                root_cause=root_cause.type.value,
            )
            return RepairResult(success=False, repair_type="max_attempts")
        
        repair_type = None
        details = {}
        
        try:
            if root_cause.type == RootCauseType.UNDEFINED_COLUMN:
                # PHASE 3: ADD MISSING COLUMN
                if root_cause.column_name and odoo_fields:
                    self._repair_add_column(
                        conn, table_name, root_cause.column_name, 
                        odoo_fields.get(root_cause.column_name, {})
                    )
                    repair_type = "add_column"
                    details["column_added"] = root_cause.column_name
                    
            elif root_cause.type in [
                RootCauseType.STRING_DATA_RIGHT_TRUNCATION,
                RootCauseType.DATATYPE_MISMATCH,
                RootCauseType.NUMERIC_VALUE_OUT_OF_RANGE,
            ]:
                # PHASE 4: MIGRATE TYPE
                if root_cause.column_name:
                    target_type = self._get_target_type(
                        root_cause.column_name, odoo_fields
                    )
                    self._repair_migrate_type(
                        conn, table_name, root_cause.column_name, target_type
                    )
                    repair_type = "migrate_type"
                    details["column"] = root_cause.column_name
                    details["new_type"] = target_type
                    
            elif root_cause.type == RootCauseType.NOT_NULL_VIOLATION:
                # PHASE 5: FIX NULL CONSTRAINT
                if root_cause.column_name:
                    is_required = self._check_if_field_required(
                        root_cause.column_name, odoo_fields
                    )
                    if not is_required:
                        self._repair_drop_not_null(conn, table_name, root_cause.column_name)
                        repair_type = "drop_not_null"
                        details["column"] = root_cause.column_name
                    else:
                        # Field is required in Odoo, can't auto-fix
                        return RepairResult(success=False, repair_type="required_field")
            
            # Record the repair pattern
            if repair_type and model:
                self._record_repair_pattern(model, table_name, root_cause, repair_type)
            
            # Retry the record
            if repair_type:
                conn.execute(text(f"SAVEPOINT {savepoint_name}"))
                try:
                    self._upsert_single(conn, table_name, record, primary_key_column)
                    conn.commit()
                    self._repairs_made.append({
                        "repair_type": repair_type,
                        "details": details,
                        "timestamp": datetime.utcnow().isoformat(),
                    })
                    return RepairResult(
                        success=True,
                        repair_type=repair_type,
                        details=details,
                        record_retried=True,
                        record_success=True,
                    )
                except SQLAlchemyError:
                    conn.execute(text(f"ROLLBACK TO SAVEPOINT {savepoint_name}"))
                    # Retry failed again, try next fix
                    return self._attempt_repair(
                        conn, table_name, record, primary_key_column,
                        root_cause, model, odoo_fields, savepoint_name,
                        attempt + 1
                    )
            
        except Exception as e:
            self._logger.error(
                "Repair attempt failed",
                repair_type=repair_type,
                error=str(e),
            )
        
        return RepairResult(success=False, repair_type=repair_type or "unknown")
    
    def _repair_add_column(
        self,
        conn: "Connection",
        table_name: str,
        column_name: str,
        field_def: dict,
    ) -> None:
        """Add a missing column to a table."""
        # Determine type from field definition
        field_type = field_def.get('type', 'char')
        pg_type = self._odoo_field_type_to_postgres(field_type)
        
        sql = text(f'''
            ALTER TABLE "{table_name}" 
            ADD COLUMN IF NOT EXISTS "{column_name}" {pg_type}
        ''')
        
        conn.execute(sql)
        conn.commit()
        
        self._logger.info(
            "Added missing column",
            table=table_name,
            column=column_name,
            type=pg_type,
        )
    
    def _repair_migrate_type(
        self,
        conn: "Connection",
        table_name: str,
        column_name: str,
        target_type: str,
    ) -> None:
        """Migrate column type."""
        sql = text(f'''
            ALTER TABLE "{table_name}"
            ALTER COLUMN "{column_name}" TYPE {target_type}
        ''')
        
        conn.execute(sql)
        conn.commit()
        
        self._logger.info(
            "Migrated column type",
            table=table_name,
            column=column_name,
            new_type=target_type,
        )
    
    def _repair_drop_not_null(
        self,
        conn: "Connection",
        table_name: str,
        column_name: str,
    ) -> None:
        """Drop NOT NULL constraint from column."""
        sql = text(f'''
            ALTER TABLE "{table_name}"
            ALTER COLUMN "{column_name}" DROP NOT NULL
        ''')
        
        conn.execute(sql)
        conn.commit()
        
        self._logger.info(
            "Dropped NOT NULL constraint",
            table=table_name,
            column=column_name,
        )
    
    def _odoo_field_type_to_postgres(self, odoo_type: str) -> str:
        """Convert Odoo field type to PostgreSQL type."""
        type_map = {
            'char': 'TEXT',
            'text': 'TEXT',
            'html': 'TEXT',
            'selection': 'TEXT',
            'float': 'NUMERIC(30,10)',
            'monetary': 'NUMERIC(30,10)',
            'integer': 'BIGINT',
            'bigint': 'BIGINT',
            'boolean': 'BOOLEAN',
            'date': 'DATE',
            'datetime': 'TIMESTAMP',
            'many2one': 'BIGINT',
            'binary': 'TEXT',
            'one2many': 'JSONB',
            'many2many': 'JSONB',
        }
        return type_map.get(odoo_type, 'TEXT')
    
    def _get_target_type(
        self,
        column_name: str,
        odoo_fields: Optional[dict],
    ) -> str:
        """Get target PostgreSQL type for a column."""
        if odoo_fields and column_name in odoo_fields:
            field_def = odoo_fields[column_name]
            return self._odoo_field_type_to_postgres(field_def.get('type', 'char'))
        
        # Default to safe types
        if 'price' in column_name.lower() or 'amount' in column_name.lower():
            return 'NUMERIC(30,10)'
        if 'date' in column_name.lower():
            return 'TIMESTAMP'
        return 'TEXT'
    
    def _check_if_field_required(
        self,
        column_name: str,
        odoo_fields: Optional[dict],
    ) -> bool:
        """Check if an Odoo field is required."""
        if odoo_fields and column_name in odoo_fields:
            return odoo_fields[column_name].get('required', False)
        return False
    
    # =========================================================================
    # PHASE 6: ADAPTIVE LEARNING
    # =========================================================================
    
    def _record_repair_pattern(
        self,
        model: str,
        table: str,
        root_cause: RootCause,
        fix_applied: str,
    ) -> None:
        """Record a repair pattern for future reference."""
        pattern_key = f"{model}:{root_cause.column_name}:{root_cause.type.value}"
        
        if pattern_key in self._error_patterns:
            pattern = self._error_patterns[pattern_key]
            pattern.occurrences += 1
            pattern.fix_applied = fix_applied
            pattern.timestamp = datetime.utcnow()
        else:
            self._error_patterns[pattern_key] = ErrorPattern(
                model=model,
                table=table,
                field=root_cause.column_name or "",
                error_type=root_cause.type,
                fix_applied=fix_applied,
            )
        
        # Also persist to database
        try:
            upsert_sql = text("""
                INSERT INTO sync_error_patterns 
                (model, table_name, field, error_type, fix_applied, occurrences, last_seen)
                VALUES (:model, :table, :field, :error_type, :fix_applied, :occurrences, CURRENT_TIMESTAMP)
                ON CONFLICT (model, field, error_type)
                DO UPDATE SET
                    fix_applied = EXCLUDED.fix_applied,
                    occurrences = sync_error_patterns.occurrences + 1,
                    last_seen = CURRENT_TIMESTAMP
            """)
            
            with self._pg.engine.connect() as conn:
                conn.execute(upsert_sql, {
                    "model": model,
                    "table": table,
                    "field": root_cause.column_name or "",
                    "error_type": root_cause.type.value,
                    "fix_applied": fix_applied,
                    "occurrences": 1,
                })
                conn.commit()
        except Exception as e:
            self._logger.debug("Could not persist error pattern", error=str(e))
    
    # =========================================================================
    # PHASE 8: ERROR SAMPLING
    # =========================================================================
    
    def _store_error_sample(
        self,
        model: str,
        table: str,
        record_id: Any,
        field: Optional[str],
        error: RootCause,
        value: Any,
    ) -> None:
        """Store error sample for debugging."""
        samples = self._error_samples.get(error.type, [])
        
        # Limit samples per type
        if len(samples) >= self._max_samples:
            return
        
        sample = ErrorSample(
            model=model,
            table=table,
            record_id=record_id,
            field=field,
            error_type=error.type,
            error_message=error.message,
            value_preview=str(value)[:200] if value is not None else None,
            stack_trace=traceback.format_exc(),
        )
        
        samples.append(sample)
        self._error_samples[error.type] = samples
    
    # =========================================================================
    # PHASE 9: REPORTING
    # =========================================================================
    
    def get_report(self) -> dict:
        """Generate self-healing report."""
        total_samples = sum(len(s) for s in self._error_samples.values())
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "repairs_made": len(self._repairs_made),
            "repairs": self._repairs_made,
            "patterns_learned": len(self._error_patterns),
            "error_samples": {
                rt.value: len(samples)
                for rt, samples in self._error_samples.items()
                if samples
            },
            "total_error_samples": total_samples,
        }
    
    def save_reports(self, reports_dir: str = "reports/self_healing") -> dict:
        """Save reports to disk."""
        import json
        import os
        
        os.makedirs(reports_dir, exist_ok=True)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        paths = {}
        
        # Save repair report
        report = self.get_report()
        report_path = os.path.join(reports_dir, f"repair_report_{timestamp}.json")
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        paths["repair_report"] = report_path
        
        # Save error samples
        if self._error_samples:
            samples_path = os.path.join(reports_dir, f"error_samples_{timestamp}.json")
            samples_data = {
                rt.value: [s.to_dict() for s in samples]
                for rt, samples in self._error_samples.items()
                if samples
            }
            with open(samples_path, 'w') as f:
                json.dump(samples_data, f, indent=2, default=str)
            paths["error_samples"] = samples_path
        
        # Save learned patterns
        if self._error_patterns:
            patterns_path = os.path.join(reports_dir, f"learned_patterns_{timestamp}.json")
            patterns_data = [p.to_dict() for p in self._error_patterns.values()]
            with open(patterns_path, 'w') as f:
                json.dump(patterns_data, f, indent=2, default=str)
            paths["learned_patterns"] = patterns_path
        
        return paths
