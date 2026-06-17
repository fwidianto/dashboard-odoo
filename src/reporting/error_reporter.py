"""Production-grade error reporting and diagnostics for sync operations.

This module provides comprehensive error tracking, classification, aggregation,
and reporting capabilities for Odoo to PostgreSQL synchronization.
"""

import csv
import json
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.reporting.error_enums import ErrorCategory

# Configuration constants
MAX_SAMPLE_RECORDS = 5
VALUE_PREVIEW_LENGTH = 200


@dataclass
class ErrorRecord:
    """Individual error record with classification and context."""
    
    model: str
    record_id: Optional[int]
    error_category: ErrorCategory
    error_message: str
    column_name: Optional[str] = None
    value_preview: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for export."""
        return {
            "model": self.model,
            "record_id": self.record_id,
            "error_category": self.error_category.value,
            "error_message": self.error_message,
            "column_name": self.column_name,
            "value_preview": self.value_preview,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class BatchErrorSummary:
    """Error summary for a single batch or model sync."""
    
    model: str
    processed: int = 0
    success: int = 0
    failed: int = 0
    errors_by_category: dict[ErrorCategory, int] = field(default_factory=dict)
    sample_records: dict[ErrorCategory, list[dict]] = field(default_factory=lambda: defaultdict(list))
    
    @property
    def error_rate(self) -> float:
        """Calculate error rate as percentage."""
        # processed = successes + errors attempted
        # error_rate = failures / total_attempts * 100
        if self.processed == 0:
            return 0.0
        return (self.failed / self.processed) * 100
    
    def add_error(self, category: ErrorCategory, record_id: Optional[int] = None,
                  error_message: str = "", column_name: Optional[str] = None,
                  value_preview: Optional[str] = None) -> None:
        """Add an error to the summary."""
        self.processed += 1  # Each record attempted counts as processed
        self.failed += 1
        self.errors_by_category[category] = self.errors_by_category.get(category, 0) + 1
        
        # Store sample record if we don't have enough
        if len(self.sample_records[category]) < MAX_SAMPLE_RECORDS:
            self.sample_records[category].append({
                "record_id": record_id,
                "column": column_name,
                "example_value": value_preview[:VALUE_PREVIEW_LENGTH] if value_preview else None,
            })
    
    def record_success(self, count: int = 1) -> None:
        """Record successful operations."""
        self.processed += count
        self.success += count
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export."""
        return {
            "processed": self.processed,
            "success": self.success,
            "failed": self.failed,
            "error_rate": round(self.error_rate, 2),
            "errors": {cat.value: count for cat, count in self.errors_by_category.items()},
        }


@dataclass
class SyncErrorReport:
    """Complete sync error report for an entire sync run."""
    
    run_timestamp: datetime = field(default_factory=datetime.utcnow)
    models: dict[str, BatchErrorSummary] = field(default_factory=dict)
    
    def add_model_summary(self, model_name: str, summary: BatchErrorSummary) -> None:
        """Add a model summary to the report."""
        self.models[model_name] = summary
    
    def get_total_processed(self) -> int:
        """Get total records processed across all models."""
        return sum(s.processed for s in self.models.values())
    
    def get_total_success(self) -> int:
        """Get total successful records across all models."""
        return sum(s.success for s in self.models.values())
    
    def get_total_failed(self) -> int:
        """Get total failed records across all models."""
        return sum(s.failed for s in self.models.values())
    
    def get_overall_error_rate(self) -> float:
        """Calculate overall error rate as percentage."""
        total = self.get_total_processed()
        if total == 0:
            return 0.0
        return (self.get_total_failed() / total) * 100
    
    def get_top_failure_causes(self, limit: int = 5) -> list[tuple[ErrorCategory, int]]:
        """Get the top failure causes across all models."""
        category_totals: dict[ErrorCategory, int] = defaultdict(int)
        for summary in self.models.values():
            for cat, count in summary.errors_by_category.items():
                category_totals[cat] += count
        
        return sorted(category_totals.items(), key=lambda x: x[1], reverse=True)[:limit]
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export."""
        return {
            "run_timestamp": self.run_timestamp.isoformat(),
            "models": {name: summary.to_dict() for name, summary in self.models.items()},
        }


class ErrorReporter:
    """
    Production-grade error reporter for sync operations.
    
    Responsibilities:
    - Collect and classify errors
    - Aggregate statistics
    - Export CSV and JSON reports
    - Print final summaries
    
    Usage:
        reporter = ErrorReporter()
        reporter.start_batch("product.template")
        # ... process records ...
        reporter.record_error(category, record_id, message)
        reporter.end_batch()
        reporter.export()
        reporter.print_summary()
    """
    
    def __init__(self, reports_dir: Optional[str] = None):
        """
        Initialize the error reporter.
        
        Args:
            reports_dir: Directory for export files. Defaults to reports/errors/.
        """
        if reports_dir is None:
            self.reports_dir = Path("reports/errors")
        else:
            self.reports_dir = Path(reports_dir)
        
        self._current_model: Optional[str] = None
        self._current_batch: Optional[BatchErrorSummary] = None
        self._all_errors: list[ErrorRecord] = []
        self._sync_report: SyncErrorReport = SyncErrorReport()
        
        # Ensure reports directory exists
        self.reports_dir.mkdir(parents=True, exist_ok=True)
    
    def start_batch(self, model: str) -> None:
        """
        Start a new batch for a model.
        
        Args:
            model: Model name (e.g., "product.template").
        """
        self._current_model = model
        self._current_batch = BatchErrorSummary(model=model)
    
    def record_success(self, count: int = 1) -> None:
        """
        Record successful operations in current batch.
        
        Args:
            count: Number of successful records.
        """
        if self._current_batch:
            self._current_batch.record_success(count)
    
    def record_error(
        self,
        error_category: ErrorCategory,
        record_id: Optional[int] = None,
        error_message: str = "",
        column_name: Optional[str] = None,
        value: Optional[str] = None,
    ) -> None:
        """
        Record an error for the current batch.
        
        Args:
            error_category: Category of the error.
            record_id: ID of the failed record.
            error_message: Error message text.
            column_name: Name of the column that caused the error.
            value: Value that caused the error (for preview).
        """
        if not self._current_model:
            return
        
        # Create error record
        error_record = ErrorRecord(
            model=self._current_model,
            record_id=record_id,
            error_category=error_category,
            error_message=error_message,
            column_name=column_name,
            value_preview=value[:VALUE_PREVIEW_LENGTH] if value else None,
        )
        self._all_errors.append(error_record)
        
        # Update batch summary
        if self._current_batch:
            self._current_batch.add_error(
                category=error_category,
                record_id=record_id,
                error_message=error_message,
                column_name=column_name,
                value_preview=value,
            )
    
    def end_batch(self) -> BatchErrorSummary:
        """
        End the current batch and return the summary.
        
        Returns:
            The batch error summary.
        """
        if self._current_batch and self._current_model:
            self._sync_report.add_model_summary(self._current_model, self._current_batch)
        
        self._current_model = None
        batch = self._current_batch
        self._current_batch = None
        return batch
    
    def export(self) -> tuple[str, str]:
        """
        Export all collected errors to CSV and JSON files.
        
        Returns:
            Tuple of (csv_path, json_path) for the exported files.
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        
        # Export CSV
        csv_path = self._export_csv(timestamp)
        
        # Export JSON
        json_path = self._export_json(timestamp)
        
        return csv_path, json_path
    
    def _export_csv(self, timestamp: str) -> str:
        """Export errors to CSV file."""
        if not self._all_errors:
            return ""
        
        csv_path = self.reports_dir / f"error_report_{timestamp}.csv"
        
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["model", "record_id", "error_category", "error_message",
                           "column_name", "value_preview", "timestamp"]
            )
            writer.writeheader()
            for error in self._all_errors:
                writer.writerow(error.to_dict())
        
        return str(csv_path)
    
    def _export_json(self, timestamp: str) -> str:
        """Export summary to JSON file."""
        json_path = self.reports_dir / f"summary_{timestamp}.json"
        
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self._sync_report.to_dict(), f, indent=2)
        
        return str(json_path)
    
    def print_summary(self) -> None:
        """Print final sync health report to console."""
        if not self._sync_report.models:
            print("\nNo sync errors recorded.")
            return
        
        # Print sync health report
        self._print_sync_health_report()
        
        # Print top failure causes
        self._print_top_failure_causes()
    
    def _print_sync_health_report(self) -> None:
        """Print the main sync health report."""
        print("\n" + "=" * 70)
        print("SYNC HEALTH REPORT")
        print("=" * 70)
        print(f"{'Model':<35} {'Success':<12} {'Failed':<12} {'Error Rate':<12}")
        print("-" * 70)
        
        for model_name, summary in self._sync_report.models.items():
            rate = f"{summary.error_rate:.2f}%"
            print(f"{model_name:<35} {summary.success:<12} {summary.failed:<12} {rate:<12}")
        
        # Totals
        total_processed = self._sync_report.get_total_processed()
        total_success = self._sync_report.get_total_success()
        total_failed = self._sync_report.get_total_failed()
        overall_rate = self._sync_report.get_overall_error_rate()
        
        print("-" * 70)
        print(f"{'TOTAL':<35}")
        print(f"{'Processed:':<20} {total_processed}")
        print(f"{'Success:':<20} {total_success}")
        print(f"{'Failed:':<20} {total_failed}")
        print(f"{'Overall Error Rate:':<20} {overall_rate:.2f}%")
        print("=" * 70)
    
    def _print_top_failure_causes(self) -> None:
        """Print top failure causes."""
        top_causes = self._sync_report.get_top_failure_causes()
        
        if not top_causes:
            return
        
        print("\nTop Failure Causes")
        print("-" * 40)
        
        for category, count in top_causes:
            print(f"{category.value:<25} {count} records")
        
        print()
    
    def print_batch_summary(self) -> None:
        """Print summary for the current batch."""
        if not self._current_batch:
            return
        
        summary = self._current_batch
        print("\n" + "-" * 60)
        print(f"BATCH ERROR SUMMARY")
        print(f"Model: {summary.model}")
        print("-" * 60)
        print(f"Records Processed: {summary.processed}")
        print(f"Success: {summary.success}")
        print(f"Failed: {summary.failed}")
        
        if summary.errors_by_category:
            print("\nError Breakdown:")
            for cat, count in sorted(summary.errors_by_category.items(), key=lambda x: x[1], reverse=True):
                # Create visual bar
                bar_len = min(count, 50)
                bar = "█" * bar_len
                print(f"  {cat.value:<20} {bar} {count}")
        
        # Print sample records
        if summary.sample_records:
            print("\nSample Records by Error Category:")
            for cat, samples in summary.sample_records.items():
                if not samples:
                    continue
                print(f"\n  {cat.value}:")
                for sample in samples[:MAX_SAMPLE_RECORDS]:
                    if sample["column"]:
                        print(f"    Column: {sample['column']}")
                    if sample["record_id"]:
                        print(f"    Record ID: {sample['record_id']}")
                    if sample["example_value"]:
                        preview = sample["example_value"]
                        if len(preview) > 60:
                            preview = preview[:60] + "..."
                        print(f"    Example Value: \"{preview}\"")
                    print()
        
        print("-" * 60)
    
    def get_batch_summary(self) -> Optional[BatchErrorSummary]:
        """Get the current batch summary."""
        return self._current_batch
    
    def get_sync_report(self) -> SyncErrorReport:
        """Get the complete sync report."""
        return self._sync_report
    
    def clear(self) -> None:
        """Clear all collected errors and reset state."""
        self._all_errors.clear()
        self._sync_report = SyncErrorReport()
        self._current_model = None
        self._current_batch = None
    
    def has_errors(self) -> bool:
        """Check if any errors have been collected."""
        return len(self._all_errors) > 0
