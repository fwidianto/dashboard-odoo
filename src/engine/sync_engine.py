"""Synchronization engine orchestrating Odoo to PostgreSQL sync."""

from datetime import datetime
from typing import Optional

from src.clients.odoo_client import OdooClient
from src.clients.postgres_client import PostgresClient
from src.models.config import FieldConfig, ModelConfig, SyncConfig
from src.models.state import SyncResult, SyncStatus, SyncAudit, SyncHistory
from src.state.state_manager import StateManager
from src.utils.logging import get_logger
from src.utils.settings import get_settings
from src.utils.config_loader import ValidatedModelConfig


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

        self._odoo = odoo_client or OdooClient(
            max_retries=config.max_retries if config else 3,
            retry_delay=config.retry_delay_seconds if config else 5,
        )
        self._pg = postgres_client or PostgresClient()
        self._state_mgr = state_manager or StateManager(self._pg)
        self._config = config
        self._batch_size = settings.sync.batch_size
        self._validated_models: dict[str, ValidatedModelConfig] = {}

    @property
    def config(self) -> SyncConfig:
        """Get sync configuration, loading if necessary."""
        if self._config is None:
            from src.utils.config_loader import get_config
            self._config = get_config()
        return self._config

    def _get_validated_model(self, model_config: ModelConfig) -> ValidatedModelConfig:
        """
        Get validated model config, fetching Odoo fields if needed.
        
        This caches validated models to avoid repeated fields_get() calls.
        """
        if model_config.odoo_model not in self._validated_models:
            try:
                # Fetch actual Odoo fields
                odoo_fields = self._odoo.get_model_fields(model_config.odoo_model)
                
                # Create validated config (skips invalid fields with warnings)
                validated = ValidatedModelConfig(model_config, odoo_fields)
                self._validated_models[model_config.odoo_model] = validated
                
                # Log skipped fields
                if validated.skipped_fields:
                    self._logger.warning(
                        f"Model '{model_config.odoo_model}': Skipped invalid fields: {validated.skipped_fields}",
                        model=model_config.odoo_model,
                        skipped_fields=validated.skipped_fields,
                        valid_fields=[f.odoo_field for f in validated.fields],
                    )
                
            except Exception as e:
                self._logger.error(
                    f"Failed to validate fields for model '{model_config.odoo_model}'. Using all configured fields.",
                    model=model_config.odoo_model,
                    error=str(e),
                )
                # Return original config if validation fails
                self._validated_models[model_config.odoo_model] = model_config
        
        return self._validated_models[model_config.odoo_model]

    def initialize(self) -> None:
        """Initialize the sync engine and infrastructure."""
        self._logger.info("Initializing sync engine")

        # Test connections
        if not self._odoo.test_connection():
            raise SyncEngineError("Cannot connect to Odoo server")

        if not self._pg.test_connection():
            raise SyncEngineError("Cannot connect to PostgreSQL")

        # Initialize state tracking tables
        self._pg.create_all_tables()

        # Validate all models against Odoo and create tables
        for model_config in self.config.models:
            # Get validated model (validates fields against Odoo)
            validated = self._get_validated_model(model_config)
            
            # Check if we still have a valid primary key after validation
            if not validated.has_valid_primary_key:
                self._logger.error(
                    f"Model '{model_config.odoo_model}' has no valid primary key after field validation. "
                    f"Original field 'id' may not exist in Odoo.",
                    model=model_config.odoo_model,
                )
                continue
            
            # Create table with validated fields
            self._pg.ensure_table_schema(validated)

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
            # Get validated model (skips invalid fields with warnings)
            validated = self._get_validated_model(model_config)
            
            # Check if we have valid fields after validation
            if not validated.has_valid_primary_key:
                result.errors.append(
                    f"Model '{model_config.odoo_model}' has no valid primary key. "
                    f"Cannot sync."
                )
                result.mark_complete()
                return result
            
            # Get counts before sync for audit
            result.odoo_count_before = self._odoo.count(model_config.odoo_model, [])
            result.postgres_count_before = self._pg.get_table_row_count(model_config.postgres_table)

            # Get fields to sync from validated config (one2many/many2many already filtered)
            field_names = [f.odoo_field for f in validated.fields 
                          if f.field_type != "one2many" and f.field_type != "many2many"]
            pk_field = validated.get_primary_key_field()
            sync_date_field = validated.get_sync_date_field()

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

            # Get batch size for this model
            batch_size = self.config.get_effective_batch_size(model_config)

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
                batch_size=batch_size,
                order="id",
            ):
                # Transform records using validated config (skips invalid fields)
                transformed = self._transform_records(batch, validated)

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

            # Handle deletion strategy
            deleted_count = self._handle_deletions(model_config, full_sync)
            result.records_deleted = deleted_count

            result.records_synced = records_synced
            result.mark_complete()

            # Get counts after sync for audit
            result.odoo_count_after = self._odoo.count(model_config.odoo_model, [])
            result.postgres_count_after = self._pg.get_table_row_count(model_config.postgres_table)

            # Update state with final info
            if last_write_date:
                result.end_time = self._parse_datetime(last_write_date)

            self._state_mgr.mark_sync_completed(model_config, result)
            
            # Create audit record
            self._create_audit_record(model_config, result)
            
            # Create history record
            self._create_history_record(model_config, result, "full" if full_sync else "incremental")

            self._logger.info(
                "Model sync completed",
                model=model_config.odoo_model,
                records=records_synced,
                deleted=deleted_count,
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
            # Create history record for failure
            self._create_history_record(model_config, result, "full" if full_sync else "incremental")
            self._logger.error(
                "Model sync failed",
                model=model_config.odoo_model,
                error=str(e),
            )

        return result

    def _handle_deletions(self, model_config: ModelConfig, full_sync: bool) -> int:
        """
        Handle records deleted in Odoo based on deletion strategy.
        
        Args:
            model_config: Model configuration.
            full_sync: Whether this is a full sync.
            
        Returns:
            Number of records handled.
        """
        strategy = model_config.deletion_strategy or self.config.default_deletion_strategy
        
        if strategy == "ignore":
            return 0
        
        # For soft_delete and reconcile, we need to track which records exist in PG
        # but not in Odoo. This is more complex and requires tracking.
        # For now, return 0 - implement based on specific requirements.
        if strategy in ("soft_delete", "reconcile"):
            self._logger.debug(
                "Deletion strategy",
                model=model_config.odoo_model,
                strategy=strategy,
            )
            # In a full implementation, you would:
            # 1. Get all IDs from Odoo
            # 2. Get all IDs from PostgreSQL
            # 3. Find IDs in PG but not in Odoo
            # 4. Apply soft_delete (set active=false) or reconcile (delete)
            return 0
        
        return 0

    def _create_audit_record(self, model_config: ModelConfig, result: SyncResult) -> None:
        """Create an audit record comparing Odoo and PostgreSQL counts."""
        odoo_count = result.odoo_count_after or 0
        pg_count = result.postgres_count_after or 0
        difference = abs(odoo_count - pg_count)
        is_synced = odoo_count == pg_count
        
        audit = SyncAudit(
            model_name=model_config.odoo_model,
            table_name=model_config.postgres_table,
            odoo_record_count=odoo_count,
            postgres_record_count=pg_count,
            difference=difference,
            is_synced=is_synced,
            notes=f"Sync completed with {result.records_synced} records processed" if is_synced else f"Count mismatch: Odoo={odoo_count}, PG={pg_count}",
        )
        
        self._pg.insert_sync_audit(audit)

    def _create_history_record(self, model_config: ModelConfig, result: SyncResult, sync_type: str) -> None:
        """Create a history record for the sync operation."""
        history = result.to_history()
        history.sync_type = sync_type
        
        self._pg.insert_sync_history(history)

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
        """Perform incremental sync for a model."""
        return self.sync_model(model_config, full_sync=False)

    def sync_model_full(self, model_config: ModelConfig) -> SyncResult:
        """Perform full sync for a model."""
        return self.sync_model(model_config, full_sync=True)

    def _transform_records(
        self,
        records: list[dict],
        model_config: ModelConfig,
    ) -> list[dict]:
        """
        Transform Odoo records to PostgreSQL format.
        
        Handles:
        - Many2one fields (store only FK ID)
        - One2many fields (skip - handled separately)
        - Many2many fields (skip - handled separately)
        - Datetime conversion
        - Default values
        - Invalid fields are automatically skipped
        """
        transformed = []
        valid_field_names = {f.odoo_field for f in model_config.fields}
        
        for record in records:
            transformed_record = {}
            
            for field in model_config.fields:
                # Skip one2many and many2many fields
                if field.field_type in ("one2many", "many2many"):
                    continue
                
                # Skip if field not in record (field was filtered out)
                if field.odoo_field not in record:
                    continue
                
                odoo_value = record.get(field.odoo_field)
                
                # Handle None values
                if odoo_value is None:
                    if field.default_value is not None:
                        transformed_record[field.postgres_column] = field.default_value
                    elif field.nullable:
                        transformed_record[field.postgres_column] = None
                    else:
                        transformed_record[field.postgres_column] = self._get_type_default(
                            field.postgres_type
                        )
                    continue

                # Handle many2one fields - extract just the ID
                if field.field_type == "many2one" or isinstance(odoo_value, list):
                    if isinstance(odoo_value, list) and len(odoo_value) >= 2:
                        # Odoo returns [id, name] for many2one
                        odoo_value = odoo_value[0] if isinstance(odoo_value[0], int) else None
                    elif isinstance(odoo_value, int):
                        pass  # Already just an ID
                    else:
                        odoo_value = None

                # Handle datetime conversion
                if isinstance(odoo_value, str) and "T" in odoo_value:
                    odoo_value = self._parse_datetime(odoo_value)

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
                if "T" in value:
                    value = value.replace("T", " ")
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

    def get_sync_history(self, model_name: Optional[str] = None, limit: int = 100) -> list[dict]:
        """
        Get sync history records.
        
        Args:
            model_name: Optional model name filter.
            limit: Maximum records to return.
            
        Returns:
            List of history dictionaries.
        """
        return self._pg.get_sync_history(model_name=model_name, limit=limit)

    def get_sync_audit(self, model_name: Optional[str] = None, limit: int = 100) -> list[dict]:
        """
        Get sync audit records.
        
        Args:
            model_name: Optional model name filter.
            limit: Maximum records to return.
            
        Returns:
            List of audit dictionaries.
        """
        # This would need to be implemented in postgres_client
        # For now, return empty list
        return []

    def validate_configuration(self) -> list[str]:
        """Validate the current configuration."""
        errors = []

        for model_config in self.config.models:
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