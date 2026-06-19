"""State manager for tracking synchronization state."""

from datetime import datetime
from typing import Optional

from src.clients.postgres_client import PostgresClient
from src.models.config import ModelConfig
from src.models.state import SyncResult, SyncStatus
from src.utils.logging import get_logger


class StateManager:
    """
    Manages synchronization state persistence and retrieval.

    Handles tracking of sync progress, last sync dates, and error states.
    """

    def __init__(self, postgres_client: PostgresClient):
        """
        Initialize the state manager.

        Args:
            postgres_client: PostgreSQL client instance.
        """
        self._pg_client = postgres_client
        self._logger = get_logger("state_manager")

    def initialize(self) -> None:
        """Initialize the state tracking infrastructure."""
        self._pg_client.create_sync_state_table()
        self._logger.info("State manager initialized")

    def get_last_sync_date(self, model_name: str) -> Optional[datetime]:
        """
        Get the last successful sync date for a model.

        Args:
            model_name: Odoo model technical name.

        Returns:
            Last sync datetime or None if never synced.
        """
        state = self._pg_client.get_sync_state(model_name)
        if state and state.get("last_sync_date"):
            return state["last_sync_date"]
        return None

    def get_last_sync_id(self, model_name: str) -> Optional[int]:
        """
        Get the last synced record ID for a model.

        Args:
            model_name: Odoo model technical name.

        Returns:
            Last sync ID or None if never synced.
        """
        state = self._pg_client.get_sync_state(model_name)
        if state:
            return state.get("last_sync_id")
        return None

    def get_sync_status(self, model_name: str) -> Optional[SyncStatus]:
        """
        Get the current sync status for a model.

        Args:
            model_name: Odoo model technical name.

        Returns:
            SyncStatus or None if never synced.
        """
        state = self._pg_client.get_sync_state(model_name)
        if state:
            status_str = state.get("status", "pending")
            try:
                return SyncStatus(status_str)
            except ValueError:
                return SyncStatus.PENDING
        return None

    def mark_sync_started(self, model_config: ModelConfig) -> None:
        """
        Mark a sync operation as started.

        IMPORTANT: This only updates the status to 'running'. It does NOT
        update last_sync_date because that would overwrite the timestamp
        from the previous successful sync.
        """
        # First, get the current state to preserve last_sync_date
        current_state = self._pg_client.get_sync_state(model_config.odoo_model)
        
        if current_state:
            # Preserve existing last_sync_date - only update status
            self._pg_client.update_sync_state(
                model_name=model_config.odoo_model,
                table_name=model_config.postgres_table,
                last_sync_date=current_state.get("last_sync_date"),  # PRESERVE!
                status=SyncStatus.RUNNING.value,
            )
        else:
            # No existing state - create new one without last_sync_date
            self._pg_client.update_sync_state(
                model_name=model_config.odoo_model,
                table_name=model_config.postgres_table,
                status=SyncStatus.RUNNING.value,
            )
        
        self._logger.info("Sync started", model=model_config.odoo_model)

    def mark_sync_completed(
        self,
        model_config: ModelConfig,
        result: SyncResult,
    ) -> None:
        """
        Mark a sync operation as completed.

        Args:
            model_config: Model configuration.
            result: Sync result with statistics.
        """
        # Get the last record's write_date
        # Use result's end_time and last_sync_id for watermark
        last_sync_date = result.end_time
        last_sync_id = result.last_sync_id

        self._logger.info(
            "SAVING SYNC STATE",
            model=model_config.odoo_model,
            records_synced=result.records_synced,
            result_end_time=result.end_time,
            last_sync_date_about_to_save=last_sync_date,
            success=result.success,
        )

        self._pg_client.update_sync_state(
            model_name=model_config.odoo_model,
            table_name=model_config.postgres_table,
            last_sync_date=last_sync_date,
            last_sync_id=last_sync_id,
            record_count=result.records_synced,
            status=SyncStatus.COMPLETED.value if result.success else SyncStatus.PARTIAL.value,
            error_message="; ".join(result.errors) if result.errors else None,
        )
        
        self._logger.info(
            "Sync completed",
            model=model_config.odoo_model,
            records=result.records_synced,
            status=result.success,
        )

    def mark_sync_failed(
        self,
        model_config: ModelConfig,
        error: str,
        record_count: int = 0,
    ) -> None:
        """
        Mark a sync operation as failed.

        IMPORTANT: This preserves the last_sync_date from the previous
        successful sync. Only the status and error_message are updated.
        """
        # Get current state to preserve last_sync_date
        current_state = self._pg_client.get_sync_state(model_config.odoo_model)
        
        self._pg_client.update_sync_state(
            model_name=model_config.odoo_model,
            table_name=model_config.postgres_table,
            last_sync_date=current_state.get("last_sync_date") if current_state else None,  # PRESERVE!
            record_count=record_count,
            status=SyncStatus.FAILED.value,
            error_message=error,
        )
        self._logger.error(
            "Sync failed",
            model=model_config.odoo_model,
            error=error,
            records_before_failure=record_count,
        )

    def get_all_sync_states(self) -> list[dict]:
        """
        Get sync states for all models.

        Returns:
            List of sync state dictionaries.
        """
        from sqlalchemy import text

        sql = text("""
            SELECT model_name, table_name, last_sync_date, last_sync_id,
                   record_count, status, error_message, created_at, updated_at
            FROM sync_state
            ORDER BY model_name
        """)

        with self._pg_client.engine.connect() as conn:
            result = conn.execute(sql)
            rows = result.fetchall()

        return [
            {
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
            for row in rows
        ]

    def reset_model_state(self, model_name: str) -> None:
        """
        Reset sync state for a model (for full re-sync).

        Args:
            model_name: Odoo model technical name.
        """
        state = self._pg_client.get_sync_state(model_name)
        if state:
            self._pg_client.update_sync_state(
                model_name=model_name,
                table_name=state["table_name"],
                status=SyncStatus.PENDING.value,
            )
            self._logger.info("Sync state reset", model=model_name)
        else:
            self._logger.warning("No sync state found to reset", model=model_name)

    def reset_all_states(self) -> None:
        """Reset sync states for all models."""
        states = self.get_all_sync_states()
        for state in states:
            self._pg_client.update_sync_state(
                model_name=state["model_name"],
                table_name=state["table_name"],
                status=SyncStatus.PENDING.value,
            )
        self._logger.info("All sync states reset", count=len(states))