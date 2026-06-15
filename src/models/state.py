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


class SyncResult(BaseModel):
    """Result of a sync operation."""

    model_name: str
    table_name: str
    success: bool = True  # Default to True, set to False if errors occur
    records_synced: int = 0
    records_updated: int = 0
    records_inserted: int = 0
    errors: list[str] = Field(default_factory=list)
    start_time: datetime = Field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None

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