"""Synchronization engine orchestrating Odoo to PostgreSQL sync."""

from datetime import datetime
from typing import Optional

from src.clients.odoo_client import OdooClient
from src.clients.postgres_client import PostgresClient
from src.models.config import FieldConfig, ModelConfig, SyncConfig
from src.models.state import SyncResult
from src.state.state_manager import StateManager
from src.utils.logging import get_logger
from src.utils.settings import get_settings


class SyncEngineError(Exception):
    """Custom exception for sync engine errors."""

    pass


class SyncEngine:
    """
    Main synchronization engine coordinating Odoo to PostgreSQL sync.

    Handles full and incremental sync modes, batch processing, and error recovery.
    """

    def __init__(
        self,
        odoo_client: Optional[OdooClient] = None,
        postgres_client: Optional[PostgresClient] = None,
        state_manager: Optional[StateManager] = None,
        config: Optional[SyncConfig] = None,
    ):
        """
        Initialize the sync engine.

        Args:
            odoo_client: Odoo client instance (created if None).
            postgres_client: PostgreSQL client instance (created if None).
            state_manager: State manager instance (created if None).
            config: Sync configuration (loaded if None).
        """
        self._logger = get_logger("sync_engine")
        settings = get_settings()

        self._odoo = odoo_client or OdooClient()
        self._pg = postgres_client or PostgresClient()
        self._state_mgr = state_manager or StateManager(self._pg)
        self._config = config
        self._batch_size = settings.sync.batch_size

    @property
    def config(self) -> SyncConfig:
        """Get sync configuration, loading if necessary."""
        if self._config is None:
            from src.utils.config_loader import get_config
            self._config = get_config()
        return self._config

    def initialize(self) -> None:
        """Initialize the sync engine and infrastructure."""
        self._logger.info("Initializing sync engine")

        # Test connections
        if not self._odoo.test_connection():
            raise SyncEngineError("Cannot connect to Odoo server")

        if not self._pg.test_connection():
            raise SyncEngineError("Cannot connect to PostgreSQL")

        # Initialize state tracking
        self._state_mgr.initialize()

        # Ensure all tables exist with correct schema
        for model_config in self.config.models:
            self._pg.ensure_table_schema(model_config)

        self._logger.info("Sync engine initialized", models=len(self.config.models))

    def sync_model(
        self,
        model_config: ModelConfig,
        full_sync: bool = False,
    ) -> SyncResult:
        """
        Synchronize a single model from Odoo to PostgreSQL.

        Args:
            model_config: Model configuration.
            full_sync: If True, sync all records; if False, only incremental.

        Returns:
            SyncResult with statistics.
        """
        result = SyncResult(
            model_name=model_config.odoo_model,
            table_name=model_config.postgres_table,
        )

        self._logger.info(
            "Starting model sync",
            model=model_config.odoo_model,
            table=model_config.postgres_table,
            full_sync=full_sync,
        )

        # Mark sync as started
        self._state_mgr.mark_sync_started(model_config)

        try:
            # Get fields to sync
            field_names = [f.odoo_field for f in model_config.fields]
            pk_field = model_config.get_primary_key_field()
            sync_date_field = model_config.get_sync_date_field()

            # Determine domain filter
            domain = []
            if not full_sync and sync_date_field:
                last_sync = self._state_mgr.get_last_sync_date(model_config.odoo_model)
                if last_sync:
                    date_str = last_sync.strftime("%Y-%m-%d %H:%M:%S")
                    domain = [(sync_date_field.odoo_field, ">=", date_str)]
                    self._logger.info(
                        "Incremental sync",
                        model=model_config.odoo_model,
                        since=last_sync,
                    )

            # Get total count for logging
            total_count = self._odoo.count(model_config.odoo_model, domain)
            self._logger.info(
                "Records to sync",
                model=model_config.odoo_model,
                count=total_count,
            )

            # Process in batches
            records_synced = 0
            last_write_date = None
            last_id = None

            for batch in self._odoo.read_batched(
                model=model_config.odoo_model,
                domain=domain,
                fields=field_names,
                batch_size=self._batch_size,
                order="id",
            ):
                # Transform records
                transformed = self._transform_records(batch, model_config)

                if not transformed:
                    continue

                # Upsert to PostgreSQL
                inserted, updated = self._pg.upsert(
                    table_name=model_config.postgres_table,
                    records=transformed,
                    primary_key_column=pk_field.postgres_column,
                )

                records_synced += len(transformed)
                result.records_inserted += inserted
                result.records_updated += updated

                # Track last record for state update
                if batch:
                    last_record = batch[-1]
                    last_id = last_record.get("id")
                    if sync_date_field and sync_date_field.odoo_field in last_record:
                        last_write_date = last_record[sync_date_field.odoo_field]

                self._logger.debug(
                    "Batch processed",
                    model=model_config.odoo_model,
                    batch_size=len(batch),
                    total_synced=records_synced,
                )

            result.records_synced = records_synced
            result.mark_complete()

            # Update state with final info
            if last_write_date:
                result.end_time = self._parse_datetime(last_write_date)

            self._state_mgr.mark_sync_completed(model_config, result)

            self._logger.info(
                "Model sync completed",
                model=model_config.odoo_model,
                records=records_synced,
                duration=result.duration_seconds,
            )

        except Exception as e:
            result.add_error(str(e))
            result.mark_complete()
            self._state_mgr.mark_sync_failed(
                model_config,
                str(e),
                result.records_synced,
            )
            self._logger.error(
                "Model sync failed",
                model=model_config.odoo_model,
                error=str(e),
            )

        return result

    def sync_all(
        self,
        full_sync: bool = False,
        model_names: Optional[list[str]] = None,
    ) -> list[SyncResult]:
        """
        Synchronize all configured models.

        Args:
            full_sync: If True, sync all records; if False, only incremental.
            model_names: Optional list of specific model names to sync.

        Returns:
            List of SyncResult for each model.
        """
        self._logger.info(
            "Starting sync all",
            full_sync=full_sync,
            model_count=len(self.config.models),
        )

        results = []
        for model_config in self.config.models:
            # Filter by model names if specified
            if model_names and model_config.odoo_model not in model_names:
                continue

            result = self.sync_model(model_config, full_sync=full_sync)
            results.append(result)

        successful = sum(1 for r in results if r.success)
        self._logger.info(
            "Sync all completed",
            total=len(results),
            successful=successful,
            failed=len(results) - successful,
        )

        return results

    def sync_model_incremental(self, model_config: ModelConfig) -> SyncResult:
        """
        Perform incremental sync for a model.

        Args:
            model_config: Model configuration.

        Returns:
            SyncResult with statistics.
        """
        return self.sync_model(model_config, full_sync=False)

    def sync_model_full(self, model_config: ModelConfig) -> SyncResult:
        """
        Perform full sync for a model.

        Args:
            model_config: Model configuration.

        Returns:
            SyncResult with statistics.
        """
        return self.sync_model(model_config, full_sync=True)

    def _transform_records(
        self,
        records: list[dict],
        model_config: ModelConfig,
    ) -> list[dict]:
        """
        Transform Odoo records to PostgreSQL format.

        Args:
            records: List of Odoo record dictionaries.
            model_config: Model configuration with field mappings.

        Returns:
            List of transformed records ready for PostgreSQL.
        """
        transformed = []

        for record in records:
            transformed_record = {}

            for field in model_config.fields:
                odoo_value = record.get(field.odoo_field)
                
                # Handle None values
                if odoo_value is None:
                    if field.default_value is not None:
                        transformed_record[field.postgres_column] = field.default_value
                    elif field.nullable:
                        transformed_record[field.postgres_column] = None
                    else:
                        # Use appropriate default for non-nullable
                        transformed_record[field.postgres_column] = self._get_type_default(
                            field.postgres_type
                        )
                    continue

                # Handle datetime conversion
                if isinstance(odoo_value, str) and "T" in odoo_value:
                    # ISO format datetime from Odoo
                    odoo_value = self._parse_datetime(odoo_value)

                # Handle relational fields (many2one returns [id, name])
                if isinstance(odoo_value, list) and len(odoo_value) == 2:
                    if isinstance(odoo_value[0], int):
                        odoo_value = odoo_value[0]  # Extract ID

                # Handle float fields
                if isinstance(odoo_value, float):
                    odoo_value = odoo_value

                transformed_record[field.postgres_column] = odoo_value

            transformed.append(transformed_record)

        return transformed

    def _parse_datetime(self, value) -> Optional[datetime]:
        """Parse datetime from various formats."""
        if value is None:
            return None

        if isinstance(value, datetime):
            return value

        if isinstance(value, str):
            try:
                # Try ISO format
                if "T" in value:
                    value = value.replace("T", " ")
                # Remove timezone info
                if "+" in value:
                    value = value.split("+")[0]
                return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f")
                except ValueError:
                    return None

        return None

    def _get_type_default(self, postgres_type: str):
        """Get default value for a PostgreSQL type."""
        type_upper = postgres_type.upper()
        
        if "INT" in type_upper:
            return 0
        if "NUMERIC" in type_upper or "DECIMAL" in type_upper:
            return 0.0
        if "BOOL" in type_upper:
            return False
        if "VARCHAR" in type_upper or "TEXT" in type_upper:
            return ""
        
        return None

    def get_sync_status(self) -> dict:
        """
        Get status of all model syncs.

        Returns:
            Dictionary with sync status for all models.
        """
        states = self._state_mgr.get_all_sync_states()
        return {
            "total_models": len(self.config.models),
            "synced_models": len(states),
            "models": states,
        }

    def validate_configuration(self) -> list[str]:
        """
        Validate the current configuration.

        Returns:
            List of validation errors (empty if valid).
        """
        errors = []

        for model_config in self.config.models:
            # Check model exists in Odoo
            try:
                fields = self._odoo.get_model_fields(model_config.odoo_model)
                if not fields:
                    errors.append(
                        f"Model '{model_config.odoo_model}' not found in Odoo"
                    )
            except Exception as e:
                errors.append(
                    f"Cannot access model '{model_config.odoo_model}': {e}"
                )

            # Check field mappings
            for field in model_config.fields:
                if field.primary_key and field.odoo_field != "id":
                    errors.append(
                        f"Model '{model_config.odoo_model}': "
                        f"Primary key should map from 'id' field"
                    )

        return errors

    def close(self) -> None:
        """Clean up resources."""
        self._odoo.close()
        self._pg.close()
        self._logger.debug("Sync engine closed")