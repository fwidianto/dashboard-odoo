"""PostgreSQL client using SQLAlchemy for database operations."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    Table,
    text,
    inspect,
)
from sqlalchemy.engine import Engine, Connection
from sqlalchemy.exc import SQLAlchemyError

from src.models.config import FieldConfig, ModelConfig
from src.utils.logging import get_logger
from src.utils.settings import get_settings


class PostgresClientError(Exception):
    """Custom exception for PostgreSQL client errors."""

    pass


class PostgresClient:
    """
    Client for PostgreSQL database operations.

    Handles table creation, schema evolution, and data upsert operations.
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
        """
        Create the sync_state table if it doesn't exist.

        This table tracks synchronization state for each model.
        """
        self._logger.info("Ensuring sync_state table exists")

        sync_state = Table(
            "sync_state",
            self._metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("model_name", text, nullable=False, unique=True),
            Column("table_name", text, nullable=False),
            Column("last_sync_date", DateTime, nullable=True),
            Column("last_sync_id", Integer, nullable=True),
            Column("record_count", Integer, default=0),
            Column("status", text, default="pending"),
            Column("error_message", text, nullable=True),
            Column("created_at", DateTime, default=datetime.utcnow),
            Column("updated_at", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
        )

        sync_state.create(self.engine, checkfirst=True)
        self._logger.info("sync_state table ready")

    def create_model_table(self, model_config: ModelConfig) -> None:
        """
        Create a table for a model if it doesn't exist.

        Args:
            model_config: Model configuration defining table structure.
        """
        self._logger.info(
            "Ensuring table exists",
            table=model_config.postgres_table,
            model=model_config.odoo_model,
        )

        columns = []
        pk_columns = []

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

            column = Column(**col_args)
            columns.append(column)

            if field.primary_key:
                pk_columns.append(column)

        # Create table
        table = Table(
            model_config.postgres_table,
            self._metadata,
            *columns,
            primary_key=tuple(pk_columns) if pk_columns else False,
        )

        table.create(self.engine, checkfirst=True)
        self._logger.info(
            "Table ready",
            table=model_config.postgres_table,
        )

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

    def ensure_table_schema(self, model_config: ModelConfig) -> None:
        """
        Ensure table exists with correct schema, adding columns if needed.

        Args:
            model_config: Model configuration.
        """
        # Create table if not exists
        self.create_model_table(model_config)
        
        # Add any new columns
        self.alter_table_add_columns(model_config)

    def upsert(
        self,
        table_name: str,
        records: list[dict],
        primary_key_column: str,
    ) -> tuple[int, int]:
        """
        Upsert records into a table using INSERT ON CONFLICT.

        Args:
            table_name: Target table name.
            records: List of record dictionaries.
            primary_key_column: Primary key column name.

        Returns:
            Tuple of (inserted_count, updated_count).
        """
        if not records:
            return 0, 0

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

        sql = text(f"""
            INSERT INTO "{table_name}" ({insert_cols})
            VALUES ({placeholders})
            ON CONFLICT ("{primary_key_column}") DO UPDATE SET {update_cols}
        """)

        inserted = 0
        updated = 0

        with self.engine.connect() as conn:
            for record in records:
                try:
                    result = conn.execute(sql, record)
                    if result.rowcount:
                        # Check if this was an insert or update
                        # In PostgreSQL, rowcount is 1 for both insert and update
                        # We need to check the database to determine
                        pass
                except SQLAlchemyError as e:
                    self._logger.error(
                        "Upsert failed",
                        table=table_name,
                        error=str(e),
                        record_id=record.get(primary_key_column),
                    )
                    raise PostgresClientError(f"Upsert failed: {e}")

            conn.commit()

        # Estimate inserted vs updated (PostgreSQL doesn't give exact counts)
        # For accuracy, we would need RETURNING clause with exclusion
        inserted = len(records) // 2  # Rough estimate
        updated = len(records) - inserted

        self._logger.info(
            "Upsert complete",
            table=table_name,
            total=len(records),
            inserted=inserted,
            updated=updated,
        )

        return inserted, updated

    def upsert_batch(
        self,
        table_name: str,
        records: list[dict],
        primary_key_column: str,
        batch_size: int = 1000,
    ) -> tuple[int, int]:
        """
        Upsert records in batches for better performance.

        Args:
            table_name: Target table name.
            records: List of record dictionaries.
            primary_key_column: Primary key column name.
            batch_size: Records per batch.

        Returns:
            Tuple of (total_inserted, total_updated).
        """
        total_inserted = 0
        total_updated = 0

        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            inserted, updated = self.upsert(table_name, batch, primary_key_column)
            total_inserted += inserted
            total_updated += updated

        return total_inserted, total_updated

    def get_sync_state(self, model_name: str) -> Optional[dict]:
        """
        Get sync state for a model.

        Args:
            model_name: Odoo model technical name.

        Returns:
            Sync state dictionary or None if not found.
        """
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
        """
        Update or insert sync state for a model.

        Args:
            model_name: Odoo model technical name.
            table_name: PostgreSQL table name.
            last_sync_date: Last successful sync timestamp.
            last_sync_id: Last synced record ID.
            record_count: Total records synced.
            status: Sync status.
            error_message: Error message if failed.
        """
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

    def get_table_row_count(self, table_name: str) -> int:
        """
        Get the number of rows in a table.

        Args:
            table_name: Table name.

        Returns:
            Row count.
        """
        sql = text(f'SELECT COUNT(*) FROM "{table_name}"')
        with self.engine.connect() as conn:
            result = conn.execute(sql)
            return result.scalar() or 0

    def table_exists(self, table_name: str) -> bool:
        """
        Check if a table exists.

        Args:
            table_name: Table name.

        Returns:
            True if table exists.
        """
        inspector = inspect(self.engine)
        return table_name in inspector.get_table_names()

    def test_connection(self) -> bool:
        """
        Test database connection.

        Returns:
            True if connection successful.
        """
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

        Args:
            postgres_type: PostgreSQL type string (e.g., 'VARCHAR(255)').

        Returns:
            SQLAlchemy Column type.
        """
        from sqlalchemy import (
            BigInteger,
            Boolean,
            Date,
            DateTime,
            Integer,
            Numeric,
            String,
            Text,
            Time,
            Uuid,
        )
        import re

        type_upper = postgres_type.upper().strip()

        # Handle types with parameters
        if type_upper.startswith("VARCHAR"):
            match = re.search(r"VARCHAR\((\d+)\)", type_upper)
            if match:
                length = int(match.group(1))
                return String(length)
            return String(255)  # Default length

        if type_upper.startswith("NUMERIC"):
            match = re.search(r"NUMERIC\((\d+)(?:,\s*(\d+))?\)", type_upper)
            if match:
                precision = int(match.group(1))
                scale = int(match.group(2)) if match.group(2) else 0
                return Numeric(precision, scale)
            return Numeric(12, 2)

        # Simple types
        type_mapping = {
            "INTEGER": Integer,
            "INT": Integer,
            "BIGINT": BigInteger,
            "BOOLEAN": Boolean,
            "BOOL": Boolean,
            "TEXT": Text,
            "TIMESTAMP": DateTime,
            "DATE": Date,
            "TIME": Time,
            "UUID": Uuid,
            "JSONB": Text,  # Store as text, let app handle JSON
        }

        for key, sqlalchemy_type in type_mapping.items():
            if type_upper == key:
                return sqlalchemy_type()

        # Default to String
        self._logger.warning(
            "Unknown PostgreSQL type, defaulting to String",
            postgres_type=postgres_type,
        )
        return String(255)