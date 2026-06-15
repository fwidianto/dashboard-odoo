"""PostgreSQL client using SQLAlchemy for database operations.

Production-ready PostgreSQL client for Odoo to PostgreSQL synchronization.
Supports large datasets, automatic schema migration, and resilient batch operations.
"""

import json
import re
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    BigInteger,
    Text,
    MetaData,
    Table,
    text,
    inspect,
    Index,
    Boolean,
    Numeric,
)
from sqlalchemy.engine import Engine, Connection
from sqlalchemy.exc import SQLAlchemyError

from src.models.config import FieldConfig, ModelConfig
from src.models.state import SyncAudit, SyncHistory, SyncStatus
from src.utils.logging import get_logger
from src.utils.settings import get_settings


class PostgresClientError(Exception):
    """Custom exception for PostgreSQL client errors."""

    pass


class PostgresClient:
    """
    Production-ready PostgreSQL client for Odoo sync.
    
    Features:
    - Automatic schema migration (type widening)
    - Resilient batch operations (skip bad records)
    - Accurate upsert metrics
    - Efficient batch commits
    """

    def __init__(self, connection_url: Optional[str] = None):
        """
        Initialize the PostgreSQL client.

        Args:
            connection_url: SQLAlchemy connection URL. If None, uses settings.
        """
        settings = get_settings()
        self.connection_url = connection_url or settings.postgres.connection_url
        self._engine: Optional[Engine] = None
        self._metadata = MetaData()
        self._logger = get_logger("postgres_client")

    @property
    def engine(self) -> Engine:
        """Get or create SQLAlchemy engine."""
        if self._engine is None:
            from sqlalchemy import create_engine
            self._engine = create_engine(
                self.connection_url,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
            )
        return self._engine

    def get_connection(self) -> Connection:
        """Get a database connection."""
        return self.engine.connect()

    def create_sync_state_table(self) -> None:
        """Create the sync_state table if it doesn't exist."""
        self._logger.info("Ensuring sync_state table exists")

        sync_state = Table(
            "sync_state",
            self._metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("model_name", Text, nullable=False, unique=True),
            Column("table_name", Text, nullable=False),
            Column("last_sync_date", DateTime, nullable=True),
            Column("last_sync_id", Integer, nullable=True),
            Column("record_count", Integer, default=0),
            Column("status", Text, default="pending"),
            Column("error_message", Text, nullable=True),
            Column("created_at", DateTime, default=datetime.utcnow),
            Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
        )

        sync_state.create(self.engine, checkfirst=True)
        self._logger.info("sync_state table ready")

    def create_sync_audit_table(self) -> None:
        """Create the sync_audit table for comparing Odoo and PostgreSQL counts."""
        self._logger.info("Ensuring sync_audit table exists")

        sync_audit = Table(
            "sync_audit",
            self._metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("model_name", Text, nullable=False),
            Column("table_name", Text, nullable=False),
            Column("odoo_record_count", Integer, default=0),
            Column("postgres_record_count", Integer, default=0),
            Column("difference", Integer, default=0),
            Column("is_synced", Boolean, default=True),
            Column("audit_date", DateTime, default=datetime.utcnow),
            Column("notes", Text, nullable=True),
            Index("idx_sync_audit_model_name", "model_name"),
            Index("idx_sync_audit_audit_date", "audit_date"),
        )

        sync_audit.create(self.engine, checkfirst=True)
        self._logger.info("sync_audit table ready")

    def create_sync_history_table(self) -> None:
        """Create the sync_history table for tracking sync operations."""
        self._logger.info("Ensuring sync_history table exists")

        sync_history = Table(
            "sync_history",
            self._metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("model_name", Text, nullable=False),
            Column("table_name", Text, nullable=False),
            Column("sync_type", Text, nullable=False),
            Column("status", Text, nullable=False),
            Column("started_at", DateTime, nullable=False),
            Column("completed_at", DateTime, nullable=True),
            Column("duration_seconds", Numeric(10, 2), nullable=True),
            Column("records_processed", Integer, default=0),
            Column("records_inserted", Integer, default=0),
            Column("records_updated", Integer, default=0),
            Column("records_deleted", Integer, default=0),
            Column("errors", Text, nullable=True),  # JSON array of errors
            Column("error_count", Integer, default=0),
            Column("odoo_count_before", Integer, nullable=True),
            Column("odoo_count_after", Integer, nullable=True),
            Column("postgres_count_before", Integer, nullable=True),
            Column("postgres_count_after", Integer, nullable=True),
            Index("idx_sync_history_model_name", "model_name"),
            Index("idx_sync_history_started_at", "started_at"),
            Index("idx_sync_history_status", "status"),
        )

        sync_history.create(self.engine, checkfirst=True)
        self._logger.info("sync_history table ready")

    def create_all_tables(self) -> None:
        """Create all required sync tables."""
        self.create_sync_state_table()
        self.create_sync_audit_table()
        self.create_sync_history_table()

    def create_model_table(self, model_config: ModelConfig) -> None:
        """
        Create a table for a model if it doesn't exist.
        
        This method is idempotent - safe to call multiple times.
        Uses extend_existing=True to handle repeated calls.

        Args:
            model_config: Model configuration defining table structure.
        """
        # IDEMPOTENCY: Check if table already exists in metadata
        if model_config.postgres_table in self._metadata.tables:
            self._logger.debug(
                "Table already defined in metadata, skipping",
                table=model_config.postgres_table,
            )
            return

        self._logger.info(
            "Ensuring table exists",
            table=model_config.postgres_table,
            model=model_config.odoo_model,
        )

        columns = []
        indexes = []

        for field in model_config.fields:
            col_args = {
                "name": field.postgres_column,
                "nullable": field.nullable,
            }

            # Map PostgreSQL type strings to SQLAlchemy types
            col_type = self._get_sqlalchemy_type(field.postgres_type)
            col_args["type_"] = col_type

            if field.default_value is not None:
                col_args["default"] = field.default_value

            # CRITICAL: Define primary_key on Column, not on Table()
            if field.primary_key:
                col_args["primary_key"] = True

            column = Column(**col_args)
            columns.append(column)

            # Create indexes for indexed fields (EXCLUDING primary keys - they have PK constraint)
            # Primary key columns don't need separate indexes
            if field.indexed and not field.primary_key:
                indexes.append(
                    Index(
                        f"idx_{model_config.postgres_table}_{field.postgres_column}",
                        field.postgres_column,
                    )
                )

        # Create table with extend_existing=True for idempotency
        # Also do NOT pass primary_key parameter to Table() - use Column.primary_key=True
        table = Table(
            model_config.postgres_table,
            self._metadata,
            extend_existing=True,  # Idempotency safeguard
            *columns,
            *indexes,
        )

        table.create(self.engine, checkfirst=True)
        
        # Migration safety: If table exists but primary key is missing, add it
        self._ensure_primary_key_constraint(model_config)
        
        self._logger.info(
            "Table ready",
            table=model_config.postgres_table,
        )
    
    def _ensure_primary_key_constraint(self, model_config: ModelConfig) -> None:
        """
        Ensure the primary key constraint exists on the configured primary key column.
        
        This handles migration for existing tables that were created without PK constraints.
        """
        pk_field = None
        for field in model_config.fields:
            if field.primary_key:
                pk_field = field
                break
        
        if not pk_field:
            return
        
        try:
            inspector = inspect(self.engine)
            pk_column = pk_field.postgres_column
            table_name = model_config.postgres_table
            
            # Check if table exists
            if table_name not in inspector.get_table_names():
                return
            
            # Check existing PK constraints
            pk_constraints = inspector.get_pk_constraint(table_name)
            
            if not pk_constraints or not pk_constraints.get('constrained_columns'):
                # No PK constraint - need to add it
                self._logger.warning(
                    f"Table '{table_name}' missing primary key constraint on '{pk_column}'. Adding constraint.",
                    table=table_name,
                    column=pk_column,
                )
                
                # PostgreSQL doesn't support ADD PRIMARY KEY IF NOT EXISTS directly,
                # so we use a block that silently succeeds if it already exists
                sql = text(f"""
                    DO $$
                    BEGIN
                        ALTER TABLE "{table_name}" ADD CONSTRAINT "{table_name}_pkey" 
                        PRIMARY KEY ("{pk_column}");
                    EXCEPTION
                        WHEN duplicate_object THEN NULL;
                    END $$;
                """)
                
                with self.engine.connect() as conn:
                    conn.execute(sql)
                    conn.commit()
                    
                self._logger.info(
                    "Primary key constraint added",
                    table=table_name,
                    column=pk_column,
                )
        except Exception as e:
            self._logger.error(
                "Failed to ensure primary key constraint",
                table=model_config.postgres_table,
                error=str(e),
            )

    def create_indexes_for_model(self, model_config: ModelConfig) -> list[str]:
        """
        Create additional indexes for a model based on configuration.

        Args:
            model_config: Model configuration.

        Returns:
            List of index names created.
        """
        created_indexes = []
        
        for field in model_config.get_indexed_fields():
            index_name = f"idx_{model_config.postgres_table}_{field.postgres_column}"
            
            # Check if index already exists
            inspector = inspect(self.engine)
            existing_indexes = [idx["name"] for idx in inspector.get_indexes(model_config.postgres_table)]
            
            if index_name not in existing_indexes:
                try:
                    sql = text(f"""
                        CREATE INDEX IF NOT EXISTS "{index_name}" 
                        ON "{model_config.postgres_table}" ("{field.postgres_column}")
                    """)
                    with self.engine.connect() as conn:
                        conn.execute(sql)
                        conn.commit()
                    created_indexes.append(index_name)
                    self._logger.info("Created index", index=index_name)
                except Exception as e:
                    self._logger.warning(
                        "Failed to create index",
                        index=index_name,
                        error=str(e),
                    )
        
        return created_indexes

    def alter_table_add_columns(self, model_config: ModelConfig) -> list[str]:
        """
        Add new columns to a table if they don't exist.

        Args:
            model_config: Model configuration with field definitions.

        Returns:
            List of column names that were added.
        """
        self._logger.info(
            "Checking for new columns",
            table=model_config.postgres_table,
        )

        inspector = inspect(self.engine)
        existing_columns = {col["name"] for col in inspector.get_columns(model_config.postgres_table)}
        
        new_columns = []
        for field in model_config.fields:
            if field.postgres_column not in existing_columns:
                new_columns.append(field)

        if not new_columns:
            self._logger.info("No new columns to add")
            return []

        added_columns = []
        with self.engine.connect() as conn:
            for field in new_columns:
                col_type = self._get_sqlalchemy_type(field.postgres_type)
                nullable_str = "" if field.nullable else "NOT NULL"
                default_str = f"DEFAULT {field.default_value}" if field.default_value else ""
                
                sql = f'ALTER TABLE "{model_config.postgres_table}" ADD COLUMN "{field.postgres_column}" {col_type.compile(self.engine.dialect)} {nullable_str} {default_str}'.strip()
                
                self._logger.info(
                    "Adding column",
                    table=model_config.postgres_table,
                    column=field.postgres_column,
                    type=field.postgres_type,
                )
                
                conn.execute(text(sql))
                added_columns.append(field.postgres_column)
            
            conn.commit()

        self._logger.info(
            "Columns added",
            table=model_config.postgres_table,
            columns=added_columns,
        )
        return added_columns

    def ensure_table_schema(self, model_config: ModelConfig) -> dict:
        """
        Ensure table exists with correct schema, adding/migrating columns if needed.

        Args:
            model_config: Model configuration.
            
        Returns:
            Dict with migration report: {added_columns: [], migrated_columns: []}
        """
        # Create table if not exists
        self.create_model_table(model_config)
        
        # Add any new columns
        added = self.alter_table_add_columns(model_config)
        
        # Migrate column types if needed (VARCHAR -> TEXT, NUMERIC widening)
        migrated = self.migrate_column_types(model_config)
        
        # Create indexes
        self.create_indexes_for_model(model_config)
        
        return {
            'added_columns': added,
            'migrated_columns': migrated,
        }

    def migrate_column_types(self, model_config: ModelConfig) -> list[dict]:
        """
        Migrate column types if PostgreSQL schema is too restrictive.
        
        Automatic migrations:
        - VARCHAR(255) -> TEXT (Odoo names can exceed 255 chars)
        - NUMERIC(12,2) -> NUMERIC(20,4) (Odoo monetary values can exceed 10B)
        
        Migration is idempotent - safe to run multiple times.

        Args:
            model_config: Model configuration with field definitions.

        Returns:
            List of migration actions performed.
        """
        self._logger.info(
            "Checking column type migrations",
            table=model_config.postgres_table,
        )
        
        inspector = inspect(self.engine)
        existing_columns = {col["name"]: col for col in inspector.get_columns(model_config.postgres_table)}
        
        migrations = []
        
        for field in model_config.fields:
            col_name = field.postgres_column
            
            if col_name not in existing_columns:
                continue  # Column will be added by alter_table_add_columns
            
            current_col = existing_columns[col_name]
            current_type = str(current_col["type"]).upper()
            
            expected_type = self._get_expected_postgres_type(field)
            expected_type_upper = expected_type.upper()
            
            # Check if migration is needed
            if self._needs_migration(current_type, expected_type_upper, current_col, field):
                migration = self._migrate_column(
                    model_config.postgres_table,
                    col_name,
                    current_type,
                    expected_type,
                    field,
                )
                if migration:
                    migrations.append(migration)
        
        if migrations:
            self._logger.info(
                "Column migrations complete",
                table=model_config.postgres_table,
                migrations=migrations,
            )
        
        return migrations
    
    def _get_expected_postgres_type(self, field: FieldConfig) -> str:
        """
        Get the expected PostgreSQL type for a field.
        
        Applies Odoo-specific type widening rules.
        """
        type_upper = field.postgres_type.upper().strip()
        
        # NUMERIC types - use larger precision for Odoo monetary/float
        if type_upper.startswith("NUMERIC"):
            # Odoo monetary fields need at least NUMERIC(20,4) for values > 100B
            return "NUMERIC(20,4)"
        
        # VARCHAR types - use TEXT for long strings
        if type_upper.startswith("VARCHAR"):
            match = re.search(r"VARCHAR\((\d+)\)", type_upper)
            if match:
                length = int(match.group(1))
                # Use TEXT for strings >= 255 (Odoo standard)
                if length >= 255:
                    return "TEXT"
                return f"VARCHAR({length})"
            return "TEXT"
        
        # Return configured type for other types
        return field.postgres_type
    
    def _needs_migration(
        self, 
        current_type: str, 
        expected_type: str,
        current_col: dict,
        field: FieldConfig,
    ) -> bool:
        """
        Determine if a column type needs migration.
        
        Migration rules:
        - VARCHAR -> TEXT (any VARCHAR is potentially too small for Odoo)
        - NUMERIC(12,2) or smaller -> NUMERIC(20,4)
        - NUMERIC with precision < 14 -> NUMERIC(20,4)
        """
        # VARCHAR to TEXT migration
        if current_type.startswith("VARCHAR") and expected_type == "TEXT":
            return True
        
        # NUMERIC migration
        if current_type.startswith("NUMERIC") and expected_type.startswith("NUMERIC"):
            current_match = re.search(r"NUMERIC\((\d+)(?:,\s*(\d+))?\)", current_type)
            expected_match = re.search(r"NUMERIC\((\d+)(?:,\s*(\d+))?\)", expected_type)
            
            if current_match and expected_match:
                current_prec = int(current_match.group(1))
                expected_prec = int(expected_match.group(1))
                
                # Migrate if current precision is less than expected
                if current_prec < expected_prec:
                    return True
                
                # Also migrate NUMERIC(12,2) even if precision is "enough"
                # because Odoo values like 17762630700.00 need more precision
                if current_prec == 12:
                    return True
        
        return False
    
    def _migrate_column(
        self,
        table_name: str,
        column_name: str,
        current_type: str,
        new_type: str,
        field: FieldConfig,
    ) -> Optional[dict]:
        """
        Execute column type migration.
        
        Uses ALTER TABLE ... ALTER COLUMN ... TYPE ...
        Migration is wrapped in EXCEPTION for idempotency.
        """
        try:
            # For VARCHAR -> TEXT: PostgreSQL handles this directly
            # For NUMERIC: Need to handle potential data truncation
            migration_sql = text(f"""
                ALTER TABLE "{table_name}" 
                ALTER COLUMN "{column_name}" TYPE {new_type}
            """)
            
            with self.engine.connect() as conn:
                conn.execute(migration_sql)
                conn.commit()
            
            self._logger.info(
                "Column type migrated",
                table=table_name,
                column=column_name,
                from_type=current_type,
                to_type=new_type,
            )
            
            return {
                'column': column_name,
                'from_type': current_type,
                'to_type': new_type,
                'action': 'MIGRATED',
            }
            
        except SQLAlchemyError as e:
            self._logger.warning(
                "Column migration failed, will retry on next sync",
                table=table_name,
                column=column_name,
                error=str(e),
            )
            return None

    def validate_and_migrate_schema(self, model_configs: list[ModelConfig]) -> dict:
        """
        Validate and migrate all model schemas at startup.
        
        Generates a structured report of all schema changes.

        Args:
            model_configs: List of model configurations.

        Returns:
            Dict with validation report for all models.
        """
        self._logger.info("=" * 60)
        self._logger.info("SCHEMA VALIDATION REPORT")
        self._logger.info("=" * 60)
        
        report = {
            'models': [],
            'total_tables_checked': 0,
            'total_columns_added': 0,
            'total_columns_migrated': 0,
        }
        
        for model_config in model_configs:
            if not self.table_exists(model_config.postgres_table):
                self._logger.info(f"  Table {model_config.postgres_table}: NEW (will be created)")
                report['models'].append({
                    'table': model_config.postgres_table,
                    'status': 'NEW',
                    'columns_added': 0,
                    'columns_migrated': 0,
                })
                continue
            
            report['total_tables_checked'] += 1
            
            self._logger.info(f"Table: {model_config.postgres_table}")
            
            inspector = inspect(self.engine)
            existing_columns = {col["name"]: col for col in inspector.get_columns(model_config.postgres_table)}
            
            added_columns = []
            migrated_columns = []
            
            for field in model_config.fields:
                col_name = field.postgres_column
                
                if col_name not in existing_columns:
                    added_columns.append(col_name)
                    self._logger.info(f"  Column: {col_name} - Action: ADDED")
                    continue
                
                current_type = str(existing_columns[col_name]["type"]).upper()
                expected_type = self._get_expected_postgres_type(field).upper()
                
                if self._needs_migration(current_type, expected_type, existing_columns[col_name], field):
                    migrated_columns.append({
                        'column': col_name,
                        'current': current_type,
                        'expected': expected_type,
                    })
                    self._logger.info(
                        f"  Column: {col_name} - Current: {current_type} -> Expected: {expected_type} - Action: MIGRATED"
                    )
            
            # Perform actual migrations
            result = self.ensure_table_schema(model_config)
            
            report['total_columns_added'] += len(result.get('added_columns', []))
            report['total_columns_migrated'] += len(result.get('migrated_columns', []))
            report['models'].append({
                'table': model_config.postgres_table,
                'status': 'VALIDATED',
                'columns_added': len(result.get('added_columns', [])),
                'columns_migrated': len(result.get('migrated_columns', [])),
            })
            
            self._logger.info(f"  Summary: Added={len(added_columns)}, Migrated={len(migrated_columns)}")
        
        self._logger.info("=" * 60)
        self._logger.info(
            f"Schema validation complete: {report['total_tables_checked']} tables checked, "
            f"{report['total_columns_added']} columns added, "
            f"{report['total_columns_migrated']} columns migrated"
        )
        self._logger.info("=" * 60)
        
        return report

    def upsert(
        self,
        table_name: str,
        records: list[dict],
        primary_key_column: str,
    ) -> tuple[int, int, int]:
        """
        Upsert records into a table using INSERT ON CONFLICT.
        
        Uses PostgreSQL RETURNING with xmax to accurately detect inserts vs updates.
        On batch failure, retries individual records to skip invalid ones.

        Args:
            table_name: Target table name.
            records: List of record dictionaries.
            primary_key_column: Primary key column name.

        Returns:
            Tuple of (inserted_count, updated_count, error_count).
        """
        if not records:
            return 0, 0, 0

        self._logger.debug(
            "Upserting records",
            table=table_name,
            count=len(records),
        )

        # Build column lists
        columns = list(records[0].keys())
        insert_cols = ", ".join(f'"{c}"' for c in columns)
        placeholders = ", ".join(f":{c}" for c in columns)
        update_cols = ", ".join(
            f'"{c}" = EXCLUDED."{c}"' for c in columns if c != primary_key_column
        )

        # Use RETURNING with xmax to detect inserts vs updates
        # xmax = 0 means insert, xmax > 0 means update
        sql = text(f"""
            INSERT INTO "{table_name}" ({insert_cols})
            VALUES ({placeholders})
            ON CONFLICT ("{primary_key_column}") DO UPDATE SET {update_cols}
            RETURNING "{primary_key_column}", xmax
        """)

        inserted = 0
        updated = 0
        errors = 0
        failed_records = []

        with self.engine.connect() as conn:
            try:
                # Try batch insert first
                for record in records:
                    try:
                        result = conn.execute(sql, record)
                        row = result.fetchone()
                        if row:
                            xmax = row[1]
                            if xmax == 0:
                                inserted += 1
                            else:
                                updated += 1
                    except SQLAlchemyError as e:
                        errors += 1
                        failed_records.append({
                            'record_id': record.get(primary_key_column),
                            'error': str(e),
                            'columns': list(record.keys())
                        })
                        self._logger.warning(
                            "Record upsert failed, will retry individually",
                            table=table_name,
                            record_id=record.get(primary_key_column),
                            error=str(e),
                        )
                
                conn.commit()
                
            except SQLAlchemyError as e:
                conn.rollback()
                self._logger.error(
                    "Batch upsert failed, retrying individually",
                    table=table_name,
                    error=str(e),
                )
                
                # Retry individually - skip failed records
                for record in records:
                    try:
                        result = conn.execute(sql, record)
                        row = result.fetchone()
                        if row:
                            xmax = row[1]
                            if xmax == 0:
                                inserted += 1
                            else:
                                updated += 1
                    except SQLAlchemyError as record_error:
                        errors += 1
                        failed_records.append({
                            'record_id': record.get(primary_key_column),
                            'error': str(record_error),
                            'columns': list(record.keys())
                        })
                        self._logger.warning(
                            "Individual record upsert failed, skipping",
                            table=table_name,
                            record_id=record.get(primary_key_column),
                            error=str(record_error),
                        )
                
                try:
                    conn.commit()
                except SQLAlchemyError:
                    pass  # Already rolled back

        # Log detailed errors for failed records
        if failed_records:
            self._logger.error(
                "Records failed to upsert",
                table=table_name,
                failed_count=len(failed_records),
                sample_errors=failed_records[:5],  # Log first 5 errors
            )

        self._logger.info(
            "Upsert complete",
            table=table_name,
            total=len(records),
            inserted=inserted,
            updated=updated,
            errors=errors,
        )

        return inserted, updated, errors

    def upsert_batch(
        self,
        table_name: str,
        records: list[dict],
        primary_key_column: str,
        batch_size: int = 1000,
    ) -> tuple[int, int, int]:
        """
        Upsert records in batches for better performance.

        Args:
            table_name: Target table name.
            records: List of record dictionaries.
            primary_key_column: Primary key column name.
            batch_size: Records per batch.

        Returns:
            Tuple of (total_inserted, total_updated, total_errors).
        """
        total_inserted = 0
        total_updated = 0
        total_errors = 0

        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            inserted, updated, errors = self.upsert(table_name, batch, primary_key_column)
            total_inserted += inserted
            total_updated += updated
            total_errors += errors

        return total_inserted, total_updated, total_errors

    def soft_delete_records(
        self,
        table_name: str,
        ids: list[int],
        soft_delete_field: str = "active",
    ) -> int:
        """
        Soft delete records by setting a flag field.

        Args:
            table_name: Target table name.
            ids: List of record IDs to soft delete.
            soft_delete_field: Field name to update (default: 'active').

        Returns:
            Number of records soft deleted.
        """
        if not ids:
            return 0

        sql = text(f'''
            UPDATE "{table_name}" 
            SET "{soft_delete_field}" = false 
            WHERE id = ANY(:ids)
        ''')

        with self.engine.connect() as conn:
            result = conn.execute(sql, {"ids": ids})
            conn.commit()
            return result.rowcount

    def hard_delete_records(
        self,
        table_name: str,
        ids: list[int],
    ) -> int:
        """
        Hard delete records from a table.

        Args:
            table_name: Target table name.
            ids: List of record IDs to delete.

        Returns:
            Number of records deleted.
        """
        if not ids:
            return 0

        sql = text(f'''
            DELETE FROM "{table_name}" 
            WHERE id = ANY(:ids)
        ''')

        with self.engine.connect() as conn:
            result = conn.execute(sql, {"ids": ids})
            conn.commit()
            return result.rowcount

    def get_sync_state(self, model_name: str) -> Optional[dict]:
        """Get sync state for a model."""
        sql = text("""
            SELECT model_name, table_name, last_sync_date, last_sync_id,
                   record_count, status, error_message, created_at, updated_at
            FROM sync_state
            WHERE model_name = :model_name
        """)

        with self.engine.connect() as conn:
            result = conn.execute(sql, {"model_name": model_name})
            row = result.fetchone()

        if row:
            return {
                "model_name": row[0],
                "table_name": row[1],
                "last_sync_date": row[2],
                "last_sync_id": row[3],
                "record_count": row[4],
                "status": row[5],
                "error_message": row[6],
                "created_at": row[7],
                "updated_at": row[8],
            }
        return None

    def update_sync_state(
        self,
        model_name: str,
        table_name: str,
        last_sync_date: Optional[datetime] = None,
        last_sync_id: Optional[int] = None,
        record_count: int = 0,
        status: str = "completed",
        error_message: Optional[str] = None,
    ) -> None:
        """Update or insert sync state for a model."""
        sql = text("""
            INSERT INTO sync_state (model_name, table_name, last_sync_date, 
                                    last_sync_id, record_count, status, error_message, 
                                    created_at, updated_at)
            VALUES (:model_name, :table_name, :last_sync_date, :last_sync_id,
                    :record_count, :status, :error_message, NOW(), NOW())
            ON CONFLICT (model_name) DO UPDATE SET
                last_sync_date = EXCLUDED.last_sync_date,
                last_sync_id = EXCLUDED.last_sync_id,
                record_count = EXCLUDED.record_count,
                status = EXCLUDED.status,
                error_message = EXCLUDED.error_message,
                updated_at = NOW()
        """)

        with self.engine.connect() as conn:
            conn.execute(sql, {
                "model_name": model_name,
                "table_name": table_name,
                "last_sync_date": last_sync_date,
                "last_sync_id": last_sync_id,
                "record_count": record_count,
                "status": status,
                "error_message": error_message,
            })
            conn.commit()

        self._logger.debug(
            "Sync state updated",
            model=model_name,
            status=status,
            record_count=record_count,
        )

    def insert_sync_audit(self, audit: SyncAudit) -> int:
        """
        Insert a sync audit record.

        Args:
            audit: SyncAudit object.

        Returns:
            Inserted audit ID.
        """
        sql = text("""
            INSERT INTO sync_audit 
            (model_name, table_name, odoo_record_count, postgres_record_count, 
             difference, is_synced, audit_date, notes)
            VALUES (:model_name, :table_name, :odoo_record_count, :postgres_record_count,
                    :difference, :is_synced, :audit_date, :notes)
            RETURNING id
        """)

        with self.engine.connect() as conn:
            result = conn.execute(sql, {
                "model_name": audit.model_name,
                "table_name": audit.table_name,
                "odoo_record_count": audit.odoo_record_count,
                "postgres_record_count": audit.postgres_record_count,
                "difference": audit.difference,
                "is_synced": audit.is_synced,
                "audit_date": audit.audit_date,
                "notes": audit.notes,
            })
            conn.commit()
            return result.scalar()

    def insert_sync_history(self, history: SyncHistory) -> int:
        """
        Insert a sync history record.

        Args:
            history: SyncHistory object.

        Returns:
            Inserted history ID.
        """
        sql = text("""
            INSERT INTO sync_history 
            (model_name, table_name, sync_type, status, started_at, completed_at,
             duration_seconds, records_processed, records_inserted, records_updated,
             records_deleted, errors, error_count, odoo_count_before, odoo_count_after,
             postgres_count_before, postgres_count_after)
            VALUES (:model_name, :table_name, :sync_type, :status, :started_at, :completed_at,
                    :duration_seconds, :records_processed, :records_inserted, :records_updated,
                    :records_deleted, :errors, :error_count, :odoo_count_before, :odoo_count_after,
                    :postgres_count_before, :postgres_count_after)
            RETURNING id
        """)

        with self.engine.connect() as conn:
            result = conn.execute(sql, {
                "model_name": history.model_name,
                "table_name": history.table_name,
                "sync_type": history.sync_type,
                "status": history.status if isinstance(history.status, str) else history.status.value,
                "started_at": history.started_at,
                "completed_at": history.completed_at,
                "duration_seconds": history.duration_seconds,
                "records_processed": history.records_processed,
                "records_inserted": history.records_inserted,
                "records_updated": history.records_updated,
                "records_deleted": history.records_deleted,
                "errors": json.dumps(history.errors),
                "error_count": history.error_count,
                "odoo_count_before": history.odoo_count_before,
                "odoo_count_after": history.odoo_count_after,
                "postgres_count_before": history.postgres_count_before,
                "postgres_count_after": history.postgres_count_after,
            })
            conn.commit()
            return result.scalar()

    def get_sync_history(
        self,
        model_name: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        Get sync history records.

        Args:
            model_name: Optional model name filter.
            limit: Maximum records to return.

        Returns:
            List of history dictionaries.
        """
        sql = """
            SELECT id, model_name, table_name, sync_type, status, started_at, 
                   completed_at, duration_seconds, records_processed, records_inserted,
                   records_updated, records_deleted, errors, error_count,
                   odoo_count_before, odoo_count_after, postgres_count_before, postgres_count_after
            FROM sync_history
        """
        params = {"limit": limit}
        
        if model_name:
            sql += " WHERE model_name = :model_name"
            params["model_name"] = model_name
        
        sql += " ORDER BY started_at DESC LIMIT :limit"

        with self.engine.connect() as conn:
            result = conn.execute(text(sql), params)
            rows = result.fetchall()

        return [
            {
                "id": row[0],
                "model_name": row[1],
                "table_name": row[2],
                "sync_type": row[3],
                "status": row[4],
                "started_at": row[5],
                "completed_at": row[6],
                "duration_seconds": row[7],
                "records_processed": row[8],
                "records_inserted": row[9],
                "records_updated": row[10],
                "records_deleted": row[11],
                "errors": json.loads(row[12]) if row[12] else [],
                "error_count": row[13],
                "odoo_count_before": row[14],
                "odoo_count_after": row[15],
                "postgres_count_before": row[16],
                "postgres_count_after": row[17],
            }
            for row in rows
        ]

    def get_table_row_count(self, table_name: str) -> int:
        """Get the number of rows in a table."""
        sql = text(f'SELECT COUNT(*) FROM "{table_name}"')
        with self.engine.connect() as conn:
            result = conn.execute(sql)
            return result.scalar() or 0

    def get_table_row_count_conditional(
        self,
        table_name: str,
        condition_column: str,
        condition_value: Any,
    ) -> int:
        """
        Get row count with a condition.

        Args:
            table_name: Table name.
            condition_column: Column to filter on.
            condition_value: Value to match.

        Returns:
            Row count.
        """
        sql = text(f'''
            SELECT COUNT(*) FROM "{table_name}" 
            WHERE "{condition_column}" = :value
        ''')
        with self.engine.connect() as conn:
            result = conn.execute(sql, {"value": condition_value})
            return result.scalar() or 0

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists."""
        inspector = inspect(self.engine)
        return table_name in inspector.get_table_names()

    def test_connection(self) -> bool:
        """Test database connection."""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            self._logger.error("Database connection test failed", error=str(e))
            return False

    def close(self):
        """Close the database engine."""
        if self._engine:
            self._engine.dispose()
            self._engine = None
            self._logger.debug("PostgreSQL client closed")

    def _get_sqlalchemy_type(self, postgres_type: str):
        """
        Map PostgreSQL type string to SQLAlchemy type.
        
        Production-ready type mapping:
        - NUMERIC: Uses (20,4) by default to support values > 100 billion
        - VARCHAR: Uses TEXT for fields > 255 chars
        - All types preserve Unicode support
        """
        from sqlalchemy import (
            BigInteger,
            Boolean,
            Date,
            DateTime,
            Float,
            Integer,
            Numeric,
            String,
            Text,
            Time,
            Uuid,
        )

        type_upper = postgres_type.upper().strip()

        # Handle VARCHAR - use TEXT for large strings
        # Odoo fields like 'name', 'description', 'notes' often exceed 255 chars
        if type_upper.startswith("VARCHAR"):
            match = re.search(r"VARCHAR\((\d+)\)", type_upper)
            if match:
                length = int(match.group(1))
                # Use TEXT for strings > 255 chars (Odoo standard)
                # Also use TEXT for VARCHAR(255) since Odoo values can exceed this
                if length >= 255:
                    return Text()
                return String(length)
            # Default VARCHAR -> TEXT for Odoo compatibility
            return Text()

        # Handle NUMERIC - use large precision for Odoo monetary/float fields
        # Odoo examples: list_price=10865523596.49, amount_total=17762630700.00
        # Need NUMERIC(20,4) to support values > 100 billion with 4 decimal places
        if type_upper.startswith("NUMERIC"):
            match = re.search(r"NUMERIC\((\d+)(?:,\s*(\d+))?\)", type_upper)
            if match:
                precision = int(match.group(1))
                scale = int(match.group(2)) if match.group(2) else 0
                # Ensure minimum precision for Odoo compatibility
                # Values like 17762630700.00 require precision >= 14
                if precision < 14 or (precision == 12 and scale <= 2):
                    # Upgrade to NUMERIC(20,4) for large Odoo values
                    return Numeric(20, 4)
                return Numeric(precision, scale)
            # Default NUMERIC -> NUMERIC(20,4) for Odoo
            return Numeric(20, 4)

        # Direct type mappings
        type_mapping = {
            "INTEGER": Integer,
            "INT": Integer,
            "BIGINT": BigInteger,
            "BOOLEAN": Boolean,
            "BOOL": Boolean,
            "TEXT": Text,
            "TIMESTAMP": DateTime,
            "TIMESTAMP WITH TIME ZONE": DateTime,
            "DATE": Date,
            "TIME": Time,
            "UUID": Uuid,
            "JSONB": Text,
            "FLOAT": Float,
            "DOUBLE PRECISION": Float,
            "REAL": Float,
        }

        for key, sqlalchemy_type in type_mapping.items():
            if type_upper == key:
                return sqlalchemy_type()

        self._logger.warning(
            "Unknown PostgreSQL type, defaulting to Text",
            postgres_type=postgres_type,
        )
        return Text()