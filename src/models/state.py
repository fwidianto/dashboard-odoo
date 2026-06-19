"""Sync state tracking models and database operations."""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class SyncStatus(str, Enum):
    """Sync operation status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class DeletionStrategy(str, Enum):
    """Deletion handling strategies."""

    IGNORE = "ignore"
    SOFT_DELETE = "soft_delete"
    RECONCILE = "reconcile"


class SyncState(BaseModel):
    """State tracking for a model synchronization."""

    model_name: str = Field(..., description="Odoo model technical name")
    table_name: str = Field(..., description="PostgreSQL table name")
    last_sync_date: Optional[datetime] = Field(default=None, description="Last successful sync timestamp")
    last_sync_id: Optional[int] = Field(default=None, description="Last synced record ID")
    record_count: int = Field(default=0, description="Number of records synced")
    status: SyncStatus = Field(default=SyncStatus.PENDING, description="Current sync status")
    error_message: Optional[str] = Field(default=None, description="Last error message if any")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        """Pydantic configuration."""

        use_enum_values = True


class SyncAudit(BaseModel):
    """Audit record comparing Odoo and PostgreSQL record counts."""

    id: Optional[int] = Field(default=None, description="Audit record ID")
    model_name: str = Field(..., description="Odoo model technical name")
    table_name: str = Field(..., description="PostgreSQL table name")
    odoo_record_count: int = Field(default=0, description="Count of records in Odoo")
    postgres_record_count: int = Field(default=0, description="Count of records in PostgreSQL")
    difference: int = Field(default=0, description="Difference between counts")
    is_synced: bool = Field(default=True, description="Whether counts match")
    audit_date: datetime = Field(default_factory=datetime.utcnow, description="When audit was performed")
    notes: Optional[str] = Field(default=None, description="Additional notes")

    class Config:
        """Pydantic configuration."""

        from_attributes = True


class SyncHistory(BaseModel):
    """Historical record of sync operations."""

    id: Optional[int] = Field(default=None, description="History record ID")
    model_name: str = Field(..., description="Odoo model technical name")
    table_name: str = Field(..., description="PostgreSQL table name")
    sync_type: str = Field(..., description="Type of sync (full, incremental)")
    status: SyncStatus = Field(..., description="Sync status")
    started_at: datetime = Field(..., description="When sync started")
    completed_at: Optional[datetime] = Field(default=None, description="When sync completed")
    duration_seconds: Optional[float] = Field(default=None, description="Sync duration in seconds")
    records_processed: int = Field(default=0, description="Total records processed")
    records_inserted: int = Field(default=0, description="Records inserted")
    records_updated: int = Field(default=0, description="Records updated")
    records_deleted: int = Field(default=0, description="Records deleted/handled")
    errors: list[str] = Field(default_factory=list, description="List of errors")
    error_count: int = Field(default=0, description="Number of errors")
    odoo_count_before: Optional[int] = Field(default=None, description="Odoo count before sync")
    odoo_count_after: Optional[int] = Field(default=None, description="Odoo count after sync")
    postgres_count_before: Optional[int] = Field(default=None, description="PostgreSQL count before sync")
    postgres_count_after: Optional[int] = Field(default=None, description="PostgreSQL count after sync")

    class Config:
        """Pydantic configuration."""

        use_enum_values = True
        from_attributes = True

    def mark_complete(self, completed_at: Optional[datetime] = None):
        """Mark the sync as complete and calculate duration."""
        self.completed_at = completed_at or datetime.utcnow()
        if self.started_at and self.completed_at:
            self.duration_seconds = (self.completed_at - self.started_at).total_seconds()

    def add_error(self, error: str):
        """Add an error message."""
        self.errors.append(error)
        self.error_count = len(self.errors)

    @property
    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return self.error_count > 0


class SyncResult(BaseModel):
    """Result of a sync operation."""

    model_name: str
    table_name: str
    success: bool = True
    records_synced: int = 0
    records_updated: int = 0
    records_inserted: int = 0
    records_deleted: int = 0
    errors: list[str] = Field(default_factory=list)
    start_time: datetime = Field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    last_sync_id: Optional[int] = None  # Watermark for incremental sync
    
    # Counts for audit
    odoo_count_before: int = 0
    odoo_count_after: int = 0
    postgres_count_before: int = 0
    postgres_count_after: int = 0

    def mark_complete(self):
        """Mark the sync as complete and calculate duration."""
        self.end_time = datetime.utcnow()
        self.duration_seconds = (self.end_time - self.start_time).total_seconds()

    def add_error(self, error: str):
        """Add an error message."""
        self.errors.append(error)

    @property
    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0
    
    def to_history(self) -> SyncHistory:
        """Convert result to history record."""
        return SyncHistory(
            model_name=self.model_name,
            table_name=self.table_name,
            sync_type="incremental",
            status=SyncStatus.COMPLETED if self.success else SyncStatus.FAILED,
            started_at=self.start_time,
            completed_at=self.end_time,
            duration_seconds=self.duration_seconds,
            records_processed=self.records_synced,
            records_inserted=self.records_inserted,
            records_updated=self.records_updated,
            records_deleted=self.records_deleted,
            errors=self.errors,
            error_count=len(self.errors),
            odoo_count_before=self.odoo_count_before,
            odoo_count_after=self.odoo_count_after,
            postgres_count_before=self.postgres_count_before,
            postgres_count_after=self.postgres_count_after,
        )