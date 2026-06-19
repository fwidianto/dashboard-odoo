"""Synchronization engine orchestrating Odoo to PostgreSQL sync."""

from datetime import datetime
from typing import Optional

from src.clients.odoo_client import OdooClient
from src.clients.postgres_client import PostgresClient, DetailedError
from src.models.config import FieldConfig, ModelConfig, SyncConfig
from src.models.state import SyncResult, SyncStatus, SyncAudit, SyncHistory
from src.reporting.error_reporter import ErrorReporter
from src.reporting.schema_recommender import SchemaRecommender
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
        error_reporter: Optional[ErrorReporter] = None,
        schema_recommender: Optional[SchemaRecommender] = None,
    ):
        """
        Initialize the sync engine.

        Args:
            odoo_client: Odoo client instance (created if None).
            postgres_client: PostgreSQL client instance (created if None).
            state_manager: State manager instance (created if None).
            config: Sync configuration (loaded if None).
            error_reporter: Error reporter instance (created if None).
            schema_recommender: Schema recommender instance (created if None).
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
        self._error_reporter = error_reporter or ErrorReporter()
        self._schema_recommender = schema_recommender or SchemaRecommender()
        self._reports_dir = "reports"

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

    def initialize(self, model_names: Optional[list[str]] = None) -> None:
        """
        Initialize the sync engine and infrastructure.
        
        Args:
            model_names: Optional list of specific model names to initialize.
                        If None, all models are initialized.
        """
        self._logger.info("=" * 60)
        self._logger.info("INITIALIZE CALLED")
        self._logger.info("=" * 60)
        self._logger.info(
            "Model filter requested",
            model_names_requested=model_names,
            total_models_in_config=len(self.config.models),
        )
        
        # Test connections
        if not self._odoo.test_connection():
            raise SyncEngineError("Cannot connect to Odoo server")

        if not self._pg.test_connection():
            raise SyncEngineError("Cannot connect to PostgreSQL")

        # Initialize state tracking tables
        self._pg.create_all_tables()

        # Filter models if specific ones requested
        if model_names:
            models_to_init = [
                m for m in self.config.models 
                if m.odoo_model in model_names
            ]
        else:
            models_to_init = self.config.models

        self._logger.info("=" * 60)
        self._logger.info("MODEL FILTERING RESULT")
        self._logger.info("=" * 60)
        self._logger.info(
            "Models to initialize",
            requested=model_names,
            all_in_config=[m.odoo_model for m in self.config.models],
            filtered=[m.odoo_model for m in models_to_init],
            count=len(models_to_init),
        )
        self._logger.info("=" * 60)
        
        if not models_to_init:
            self._logger.warning(
                "No models match the requested filter!",
                requested=model_names,
            )
            return

        # Validate only requested models against Odoo and create tables
        for model_config in models_to_init:
            self._logger.info("-" * 40)
            self._logger.info(f"INITIALIZING MODEL: {model_config.odoo_model}")
            self._logger.info("-" * 40)
            
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
            
            # Get Odoo fields for validation report
            try:
                self._logger.info(f"  Fetching fields_get() for {model_config.odoo_model}")
                odoo_fields = self._odoo.get_model_fields(model_config.odoo_model)
                self._logger.info(f"  fields_get() returned {len(odoo_fields)} fields")
            except Exception as e:
                self._logger.warning(
                    f"Could not fetch Odoo fields for validation: {e}",
                    model=model_config.odoo_model,
                )
                odoo_fields = {}
            
            # Generate schema validation report (logs mismatches)
            self._logger.info(f"  Running schema validation for {model_config.odoo_model}")
            validation_report = self._pg.validate_schema_against_odoo(validated, odoo_fields)
            
            # Log the mismatch report
            if validation_report['mismatches']:
                self._logger.warning(
                    f"Schema mismatch report for {model_config.odoo_model}:",
                    mismatches=validation_report['mismatches'],
                )
            
            # Create table with validated fields
            self._logger.info(f"  Creating/Updating table schema for {model_config.postgres_table}")
            self._pg.ensure_table_schema(validated)
            self._logger.info(f"  COMPLETED: {model_config.odoo_model}")

        self._logger.info("=" * 60)
        self._logger.info(
            "Sync engine initialized",
            total_models_in_config=len(self.config.models),
            initialized_models_count=len(models_to_init),
            initialized_models=[m.odoo_model for m in models_to_init],
        )
        self._logger.info("=" * 60)

    def sync_model(
        self,
        model_config: ModelConfig,
        full_sync: bool = False,
        record_limit: Optional[int] = None,
    ) -> SyncResult:
        """
        Synchronize a single model from Odoo to PostgreSQL.

        Args:
            model_config: Model configuration.
            full_sync: If True, sync all records; if False, only incremental.
            record_limit: Optional limit of records to sync (for quick validation).

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
            record_limit=record_limit,
        )

        # Mark sync as started
        self._state_mgr.mark_sync_started(model_config)
        
        # Start error reporting batch for this model
        self._error_reporter.start_batch(
            model=model_config.odoo_model,
            table_name=model_config.postgres_table,
        )

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
            
            # Get total Odoo records for audit (always query without domain)
            total_odoo_records = self._odoo.count(model_config.odoo_model, [])
            result.odoo_count_before = total_odoo_records
            result.postgres_count_before = self._pg.get_table_row_count(model_config.postgres_table)

            # Get fields to sync from validated config (one2many/many2many already filtered)
            field_names = [f.odoo_field for f in validated.fields 
                          if f.field_type != "one2many" and f.field_type != "many2many"]
            pk_field = validated.get_primary_key_field()
            sync_date_field = validated.get_sync_date_field()
            
            # Create field type mapping for data profiling
            field_type_map = {
                f.postgres_column: f.postgres_type 
                for f in validated.fields 
                if f.field_type not in ("one2many", "many2many")
            }

            # Determine domain filter for incremental sync
            domain = []
            last_sync_date = None
            last_sync_id = None
            sync_date_field_name = sync_date_field.odoo_field if sync_date_field else None
            
            if not full_sync and sync_date_field:
                # CRITICAL DEBUG: Log we're reading sync state
                self._logger.info(
                    "READING SYNC STATE",
                    model=model_config.odoo_model,
                    action="get_last_sync_date",
                )
                last_sync_date = self._state_mgr.get_last_sync_date(model_config.odoo_model)
                last_sync_id = self._state_mgr.get_last_sync_id(model_config.odoo_model)
                
                # CRITICAL DEBUG: Log what we read
                self._logger.info(
                    "SYNC STATE READ",
                    model=model_config.odoo_model,
                    last_sync_date_read=last_sync_date,
                    last_sync_id_read=last_sync_id,
                )
                
                if last_sync_date is not None:
                    date_str = last_sync_date.strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Build proper incremental domain using (date, id) watermark:
                    # Fetch records where:
                    #   write_date > last_sync_date
                    #   OR (write_date = last_sync_date AND id > last_sync_id)
                    if last_sync_id is not None:
                        # Full watermark: use date + id
                        domain = [
                            "|",
                            (sync_date_field.odoo_field, ">", date_str),
                            "&",
                            (sync_date_field.odoo_field, "=", date_str),
                            ("id", ">", last_sync_id),
                        ]
                        self._logger.info(
                            "INCREMENTAL FILTER GENERATED",
                            model=model_config.odoo_model,
                            last_sync_date=date_str,
                            last_sync_date_type=type(last_sync_date).__name__,
                            last_sync_id=last_sync_id,
                            last_sync_id_type=type(last_sync_id).__name__,
                            domain=domain,
                        )
                        
                        # CRITICAL: Log exact values for debugging
                        self._logger.info(
                            "DOMAIN_DEBUG",
                            model=model_config.odoo_model,
                            date_str_repr=repr(date_str),
                            last_sync_id_repr=repr(last_sync_id),
                            last_sync_id_is_int=isinstance(last_sync_id, int),
                            sync_date_field=sync_date_field.odoo_field,
                            domain_tuple_0=(sync_date_field.odoo_field, ">", date_str),
                            domain_tuple_1=(sync_date_field.odoo_field, "=", date_str),
                            domain_tuple_2=("id", ">", last_sync_id),
                        )
                    else:
                        # First incremental run (only date available) - fall back to simple filter
                        domain = [(sync_date_field.odoo_field, ">=", date_str)]
                        self._logger.info(
                            "INCREMENTAL FILTER GENERATED (date only)",
                            model=model_config.odoo_model,
                            last_sync_date=date_str,
                            last_sync_id=None,
                            domain=domain,
                        )
                else:
                    # Log why incremental is falling back to full sync
                    self._logger.warning(
                        "No previous sync found - treating as full sync",
                        model=model_config.odoo_model,
                        reason="last_sync_date is None in sync_state table",
                        suggestion="Run full sync first: --mode full --models " + model_config.odoo_model,
                    )
            
            # Get batch size for this model
            batch_size = self.config.get_effective_batch_size(model_config)

            # Get count of records to sync (with domain filter for incremental)
            # This is the CRITICAL metric that proves incremental is working
            if full_sync:
                sync_count = total_odoo_records
                self._logger.info(
                    "=" * 60
                )
                self._logger.info("FULL SYNC MODE")
                self._logger.info(
                    "=" * 60
                )
                self._logger.info(
                    "Model:",
                    model=model_config.odoo_model,
                )
                self._logger.info(
                    "Fetching: ALL records (no domain filter)",
                )
                self._logger.info(
                    "Total records in Odoo:",
                    total=total_odoo_records,
                )
                self._logger.info(
                    "=" * 60
                )
            else:
                sync_count = self._odoo.count(model_config.odoo_model, domain)
                self._logger.info(
                    "=" * 60
                )
                self._logger.info("INCREMENTAL SYNC MODE")
                self._logger.info(
                    "=" * 60
                )
                self._logger.info(
                    "Model:",
                    model=model_config.odoo_model,
                )
                self._logger.info(
                    "Last sync timestamp:",
                    last_sync=last_sync_date.strftime("%Y-%m-%d %H:%M:%S") if last_sync_date else "Never (full sync needed)",
                )
                self._logger.info(
                    "Filtering field:",
                    field=sync_date_field.odoo_field if sync_date_field else "None",
                )
                self._logger.info(
                    "Generated domain:",
                    domain=domain,
                )
                self._logger.info(
                    "-" * 40
                )
                self._logger.info(
                    "Total records in Odoo:",
                    total=total_odoo_records,
                )
                self._logger.info(
                    "Records matching filter:",
                    changed=sync_count,
                )
                self._logger.info(
                    "-" * 40
                )
                if sync_count == 0:
                    self._logger.info(
                        "No records to sync - all up to date!",
                    )
                elif sync_count < total_odoo_records:
                    reduction_pct = (1 - sync_count / total_odoo_records) * 100
                    self._logger.info(
                        "INCREMENTAL SUCCESS: Fetching only {:.1f}% of records".format(
                            sync_count / total_odoo_records * 100
                        ),
                    )
                    self._logger.info(
                        "DATA SAVED: Skipped {} records (99.99% reduction)".format(
                            total_odoo_records - sync_count
                        ) if reduction_pct > 99 else "Records saved: {}".format(
                            total_odoo_records - sync_count
                        ),
                    )
                self._logger.info(
                    "=" * 60
                )

            # Process in batches
            records_synced = 0
            last_write_date = None
            last_id = None
            batches_processed = 0
            
            self._logger.info(
                "Starting batch processing",
                model=model_config.odoo_model,
                sync_date_field=sync_date_field.odoo_field if sync_date_field else "NONE",
                domain=domain,
                batch_size=batch_size,
            )
            
            # Define error callback for this model
            def error_callback(error: DetailedError) -> None:
                """Record error to the error reporter."""
                self._error_reporter.record_error(
                    model=model_config.odoo_model,
                    table_name=model_config.postgres_table or model_config.odoo_model.replace(".", "_"),
                    category=error.error_category,
                    record_id=error.record_id,
                    error_message=error.error_message,
                    column_name=error.column_name,
                    value=error.value_preview,
                )

            
            # Profile data for each record
            def profile_callback(record: dict) -> None:
                """Profile data values for schema recommendations."""
                for col, value in record.items():
                    col_type = field_type_map.get(col, "TEXT")
                    self._error_reporter.profile_data(col, col_type, value)
            for batch in self._odoo.read_batched(
                model=model_config.odoo_model,
                domain=domain,
                fields=field_names,
                batch_size=batch_size,
                order="id",
                total_limit=record_limit,
            ):
                # Transform records using validated config (skips invalid fields)
                transformed = self._transform_records(batch, validated)

                if not transformed:
                    continue
                
                # Profile data for schema analysis
                for record in transformed:
                    profile_callback(record)

                # Upsert to PostgreSQL (with error resilience - skips bad records)
                inserted, updated, errors = self._pg.upsert(
                    table_name=model_config.postgres_table,
                    records=transformed,
                    primary_key_column=pk_field.postgres_column,
                    error_callback=error_callback,
                )

                records_synced += len(transformed)
                result.records_inserted += inserted
                result.records_updated += updated
                
                # Record successful records to error reporter
                successful_count = inserted + updated
                self._error_reporter.record_success(successful_count)
                
                if errors > 0:
                    self._logger.warning(
                        "Some records failed to upsert",
                        model=model_config.odoo_model,
                        failed_count=errors,
                    )

                # CRITICAL: Track MAX write_date across ALL records in ALL batches
                # Do NOT use batch[-1] - examine every record
                if sync_date_field and batch:
                    write_date_field = sync_date_field.odoo_field
                    
                    # Log first and last record in batch for debugging
                    first_record = batch[0]
                    last_record = batch[-1]
                    self._logger.info(
                        "BATCH_BOUNDS",
                        model=model_config.odoo_model,
                        batch_index=batches_processed,
                        batch_size=len(batch),
                        first_record_id=first_record.get("id"),
                        first_record_write_date=first_record.get(write_date_field),
                        last_record_id=last_record.get("id"),
                        last_record_write_date=last_record.get(write_date_field),
                    )
                    
                    for record in batch:
                        record_id = record.get("id")
                        record_write_date = record.get(write_date_field)
                        
                        # Handle NULL/False/Invalid write_date - skip these records
                        # Odoo can return: None, False, "", "null", datetime, string
                        # Only accept datetime or string write_date values
                        if record_write_date is None:
                            self._logger.warning(
                                "RECORD_NULL_WRITE_DATE",
                                model=model_config.odoo_model,
                                batch_index=batches_processed,
                                record_id=record_id,
                                warning="Skipping NULL write_date for checkpoint calculation",
                            )
                            continue
                        
                        # Handle boolean False values from Odoo
                        if record_write_date is False:
                            self._logger.warning(
                                "RECORD_FALSE_WRITE_DATE",
                                model=model_config.odoo_model,
                                batch_index=batches_processed,
                                record_id=record_id,
                                warning="Skipping FALSE write_date for checkpoint calculation",
                            )
                            continue
                        
                        # Handle empty string or non-string/non-datetime values
                        if isinstance(record_write_date, bool):
                            self._logger.warning(
                                "RECORD_BOOL_WRITE_DATE",
                                model=model_config.odoo_model,
                                batch_index=batches_processed,
                                record_id=record_id,
                                record_write_date_type=type(record_write_date).__name__,
                                warning="Skipping non-datetime write_date for checkpoint calculation",
                            )
                            continue
                        
                        if not isinstance(record_write_date, (str, datetime)):
                            self._logger.warning(
                                "RECORD_INVALID_WRITE_DATE",
                                model=model_config.odoo_model,
                                batch_index=batches_processed,
                                record_id=record_id,
                                record_write_date_type=type(record_write_date).__name__,
                                record_write_date_value=repr(record_write_date),
                                warning="Skipping invalid write_date type for checkpoint calculation",
                            )
                            continue
                        
                        # Update checkpoint if this record has a higher write_date
                        # Add defensive check to prevent type comparison errors
                        try:
                            should_update = (last_write_date is None or record_write_date > last_write_date)
                        except TypeError as e:
                            self._logger.error(
                                "WRITE_DATE_COMPARISON_ERROR",
                                model=model_config.odoo_model,
                                batch_index=batches_processed,
                                record_id=record_id,
                                record_write_date=record_write_date,
                                record_write_date_type=type(record_write_date).__name__,
                                last_write_date=last_write_date,
                                last_write_date_type=type(last_write_date).__name__,
                                error=str(e),
                                warning="Skipping record due to comparison error",
                            )
                            continue
                        
                        if should_update:
                            self._logger.info(
                                "MAX_WRITE_DATE_FOUND",
                                model=model_config.odoo_model,
                                batch_index=batches_processed,
                                record_id=record_id,
                                record_write_date=record_write_date,
                                old_max_date=last_write_date,
                                old_max_id=last_id,
                                new_max_date=record_write_date,
                                new_max_id=record_id,
                            )
                            # Final validation: ensure we're not setting invalid values
                            if isinstance(record_write_date, (str, datetime)) and record_write_date:
                                last_write_date = record_write_date
                                last_id = record_id
                            else:
                                self._logger.warning(
                                    "SKIPPING_INVALID_ASSIGNMENT",
                                    model=model_config.odoo_model,
                                    record_id=record_id,
                                    record_write_date=record_write_date,
                                    warning="Not updating checkpoint with invalid value",
                                )
                        # If same write_date, use max id
                        elif record_write_date == last_write_date and record_id > (last_id or 0):
                            self._logger.info(
                                "MAX_ID_FOR_SAME_DATE",
                                model=model_config.odoo_model,
                                batch_index=batches_processed,
                                record_id=record_id,
                                same_date=record_write_date,
                                old_max_id=last_id,
                                new_max_id=record_id,
                            )
                            last_id = record_id

                batches_processed += 1

                self._logger.info(
                    "Batch processed",
                    model=model_config.odoo_model,
                    batch_index=batches_processed,
                    batch_size=len(batch),
                    total_synced=records_synced,
                    batches_total=batches_processed,
                    current_max_write_date=last_write_date,
                    current_max_id=last_id,
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
            self._logger.info(
                "FINAL STATE UPDATE",
                model=model_config.odoo_model,
                last_write_date_raw=last_write_date,
                records_synced=records_synced,
                batches_processed=batches_processed,
            )
            
            # FINAL CHECKPOINT LOGGING
            self._logger.info(
                "CHECKPOINT DECISION",
                model=model_config.odoo_model,
                total_records_synced=records_synced,
                final_last_write_date=last_write_date,
                final_last_id=last_id,
                final_checkpoint=f"date={last_write_date}, id={last_id}",
            )

            # CRITICAL: Log checkpoint details before saving
            self._logger.info(
                "CHECKPOINT_SAVING",
                model=model_config.odoo_model,
                raw_last_write_date=last_write_date,
                raw_last_write_date_type=type(last_write_date).__name__,
                raw_last_id=last_id,
                raw_last_id_type=type(last_id).__name__,
            )

            if last_write_date:
                parsed_end_time = self._parse_datetime(last_write_date)
                result.end_time = parsed_end_time
                result.last_sync_id = last_id  # Watermark for incremental sync
                self._logger.info(
                    "CHECKPOINT_SAVED",
                    model=model_config.odoo_model,
                    raw_last_write_date=last_write_date,
                    parsed_end_time=parsed_end_time,
                    raw_last_id=last_id,
                    last_sync_id_in_result=result.last_sync_id,
                )

            self._state_mgr.mark_sync_completed(model_config, result)
            
            # Create audit record
            self._create_audit_record(model_config, result)
            
            # Create history record
            self._create_history_record(model_config, result, "full" if full_sync else "incremental")

            # Final sync result logging
            self._logger.info("=" * 60)
            self._logger.info("SYNC COMPLETE")
            self._logger.info("=" * 60)
            self._logger.info("Model:", model=model_config.odoo_model)
            self._logger.info("Table:", table=model_config.postgres_table)
            self._logger.info("Mode:", mode="FULL" if full_sync else "INCREMENTAL")
            self._logger.info("-" * 40)
            self._logger.info("Records processed:", total=records_synced)
            self._logger.info("Records inserted:", inserted=result.records_inserted)
            self._logger.info("Records updated:", updated=result.records_updated)
            self._logger.info("Records deleted:", deleted=deleted_count)
            self._logger.info("Records failed:", failed=len(result.errors))
            self._logger.info("-" * 40)
            if full_sync:
                self._logger.info("Fetched {} records (all records)".format(records_synced))
            else:
                if sync_count < total_odoo_records:
                    saved = total_odoo_records - sync_count
                    self._logger.info("Fetched {} records (saved {} queries)".format(
                        records_synced, saved
                    ))
                else:
                    self._logger.info("Fetched {} records".format(records_synced))
            self._logger.info("Duration:", duration="{:.2f}s".format(result.duration_seconds) if result.duration_seconds else "N/A")
            self._logger.info("=" * 60)

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
        
        # End batch and print summary
        self._error_reporter.end_batch()
        self._error_reporter.print_batch_summary()
        
        # Record batch errors to result
        batch_summary = self._error_reporter.get_batch_summary()
        if batch_summary and batch_summary.errors_by_category:
            for cat, count in batch_summary.errors_by_category.items():
                result.add_error(f"{cat.value}: {count} records")

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
        record_limit: Optional[int] = None,
    ) -> list[SyncResult]:
        """
        Synchronize all configured models.

        Args:
            full_sync: If True, sync all records; if False, only incremental.
            model_names: Optional list of specific model names to sync.
            record_limit: Optional limit of records per model (for quick validation).

        Returns:
            List of SyncResult for each model.
        """
        self._logger.debug(
            "Sync all called",
            record_limit=record_limit,
        )
        self._logger.info(
            "Starting sync all",
            full_sync=full_sync,
            model_count=len(self.config.models),
            record_limit=record_limit,
        )
        
        # Validate and migrate schemas for selected models
        models_to_sync = [m for m in self.config.models 
                         if not model_names or m.odoo_model in model_names]
        schema_report = self._pg.validate_and_migrate_schema(models_to_sync)

        results = []
        for model_config in models_to_sync:

            result = self.sync_model(model_config, full_sync=full_sync, record_limit=record_limit)
            results.append(result)

        successful = sum(1 for r in results if r.success)
        self._logger.info(
            "Sync all completed",
            total=len(results),
            successful=successful,
            failed=len(results) - successful,
        )
        
        # Generate schema recommendations
        self._generate_schema_recommendations()

        # Export all reports
        if self._error_reporter.has_errors():
            self._error_reporter.export_all()
        
        # Print final sync health report
        self._error_reporter.print_summary()

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

                # Handle False/True for integer fields (Odoo sometimes returns False instead of null)
                if odoo_value is False:
                    if field.postgres_type.upper().startswith(('INT', 'NUMERIC', 'DECIMAL')):
                        odoo_value = None  # Convert False to NULL for numeric fields
                    elif field.postgres_type.upper() == 'BOOLEAN':
                        odoo_value = False  # Keep False for boolean fields
                    else:
                        odoo_value = None  # Convert False to NULL for other fields

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
    
    def get_error_reporter(self) -> ErrorReporter:
        """Get the error reporter instance."""
        return self._error_reporter
    
    def _generate_schema_recommendations(self) -> None:
        """Generate schema recommendations from collected error data."""
        for model_name, summary in self._error_reporter.get_sync_report().models.items():
            self._schema_recommender.add_batch_summary(summary)
        
        # Export recommendations
        self._schema_recommender.export()
        self._schema_recommender.print_recommendations()
    
    def get_schema_recommender(self) -> SchemaRecommender:
        """Get the schema recommender instance."""
        return self._schema_recommender