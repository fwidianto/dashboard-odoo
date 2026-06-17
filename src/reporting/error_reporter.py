"""Production-grade error reporting and diagnostics for sync operations.

This module provides comprehensive error tracking, classification, aggregation,
and reporting capabilities for Odoo to PostgreSQL synchronization.
"""

import csv
import json
import re
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from src.reporting.error_enums import ErrorCategory

# Configuration constants
MAX_SAMPLE_RECORDS = 10  # Up to 10 samples per error type
VALUE_PREVIEW_LENGTH = 200


@dataclass
class DataProfile:
    """Data profiling information for a column."""
    
    column_name: str
    current_type: str
    max_length_observed: int = 0
    max_value_observed: Optional[float] = None
    total_values: int = 0
    null_count: int = 0
    
    def update_with_value(self, value: Any) -> None:
        """Update profile with a new value."""
        self.total_values += 1
        if value is None:
            self.null_count += 1
            return
        
        if isinstance(value, str):
            self.max_length_observed = max(self.max_length_observed, len(value))
        elif isinstance(value, (int, float)):
            if self.max_value_observed is None:
                self.max_value_observed = float(value)
            else:
                self.max_value_observed = max(self.max_value_observed, float(value))
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "current_type": self.current_type,
            "max_length_observed": self.max_length_observed,
            "max_value_observed": self.max_value_observed,
            "total_values": self.total_values,
            "null_count": self.null_count,
        }


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
    table_name: str = ""
    processed: int = 0
    success: int = 0
    failed: int = 0
    errors_by_category: dict[ErrorCategory, int] = field(default_factory=dict)
    errors_by_column: dict[str, int] = field(default_factory=dict)
    sample_records: dict[ErrorCategory, list[dict]] = field(default_factory=lambda: defaultdict(list))
    data_profiles: dict[str, DataProfile] = field(default_factory=dict)
    
    @property
    def error_rate(self) -> float:
        """Calculate error rate as percentage."""
        if self.processed == 0:
            return 0.0
        return (self.failed / self.processed) * 100
    
    def add_error(
        self,
        category: ErrorCategory,
        record_id: Optional[int] = None,
        error_message: str = "",
        column_name: Optional[str] = None,
        value_preview: Optional[str] = None,
    ) -> None:
        """Add an error to the summary."""
        self.processed += 1
        self.failed += 1
        self.errors_by_category[category] = self.errors_by_category.get(category, 0) + 1
        
        # Track column failures
        if column_name:
            self.errors_by_column[column_name] = self.errors_by_column.get(column_name, 0) + 1
        
        # Store sample record (up to MAX_SAMPLE_RECORDS per error type)
        if len(self.sample_records[category]) < MAX_SAMPLE_RECORDS:
            self.sample_records[category].append({
                "record_id": record_id,
                "column": column_name,
                "value_preview": value_preview[:VALUE_PREVIEW_LENGTH] if value_preview else None,
            })
    
    def record_success(self, count: int = 1) -> None:
        """Record successful operations."""
        self.processed += count
        self.success += count
    
    def update_data_profile(self, column_name: str, column_type: str, value: Any) -> None:
        """Update data profiling for a column."""
        if column_name not in self.data_profiles:
            self.data_profiles[column_name] = DataProfile(
                column_name=column_name,
                current_type=column_type,
            )
        self.data_profiles[column_name].update_with_value(value)
    
    def get_problem_columns(self) -> dict[str, int]:
        """Get columns sorted by failure count."""
        return dict(sorted(self.errors_by_column.items(), key=lambda x: x[1], reverse=True))
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export."""
        return {
            "processed": self.processed,
            "success": self.success,
            "failed": self.failed,
            "error_rate": round(self.error_rate, 2),
            "errors": {cat.value: count for cat, count in self.errors_by_category.items()},
        }
    
    def to_full_dict(self) -> dict:
        """Convert to full dictionary including column analysis and samples."""
        return {
            "model": self.model,
            "table": self.table_name,
            "processed": self.processed,
            "success": self.success,
            "failed": self.failed,
            "error_rate": round(self.error_rate, 2),
            "problem_columns": self.get_problem_columns(),
            "error_types": {cat.value: count for cat, count in self.errors_by_category.items()},
            "sample_failures": {
                cat.value: samples for cat, samples in self.sample_records.items()
            },
            "data_profiles": {
                col: profile.to_dict() for col, profile in self.data_profiles.items()
            },
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
    - Aggregate statistics by category and column
    - Track data profiles
    - Export CSV, JSON, and model health reports
    - Print final summaries
    
    Usage:
        reporter = ErrorReporter()
        reporter.start_batch("product.template", table_name="product_template")
        # ... process records ...
        reporter.record_error(category, record_id, message)
        reporter.end_batch()
        reporter.export_all()
        reporter.print_summary()
    """
    
    def __init__(self, reports_dir: Optional[str] = None):
        """
        Initialize the error reporter.
        
        Args:
            reports_dir: Base directory for export files. Defaults to "reports/".
        """
        if reports_dir is None:
            self.reports_dir = Path("reports")
        else:
            self.reports_dir = Path(reports_dir)
        
        # Subdirectories
        self.errors_dir = self.reports_dir / "errors"
        self.model_health_dir = self.reports_dir / "model_health"
        self.sample_errors_dir = self.reports_dir / "sample_errors"
        self.schema_recommendations_dir = self.reports_dir / "schema_recommendations"
        
        self._current_model: Optional[str] = None
        self._current_table: Optional[str] = None
        self._current_batch: Optional[BatchErrorSummary] = None
        self._all_errors: list[ErrorRecord] = []
        self._sync_report: SyncErrorReport = SyncErrorReport()
        
        # Ensure reports directories exist
        self.errors_dir.mkdir(parents=True, exist_ok=True)
        self.model_health_dir.mkdir(parents=True, exist_ok=True)
        self.sample_errors_dir.mkdir(parents=True, exist_ok=True)
        self.schema_recommendations_dir.mkdir(parents=True, exist_ok=True)
    
    def start_batch(self, model: str, table_name: str = "") -> None:
        """
        Start a new batch for a model.
        
        Args:
            model: Model name (e.g., "product.template").
            table_name: PostgreSQL table name (e.g., "product_template").
        """
        self._current_model = model
        self._current_table = table_name or model.replace(".", "_")
        self._current_batch = BatchErrorSummary(model=model, table_name=self._current_table)
    
    def record_success(self, count: int = 1) -> None:
        """
        Record successful operations in current batch.
        
        Args:
            count: Number of successful records.
        """
        if self._current_batch:
            self._current_batch.record_success(count)
    
    def profile_data(self, column_name: str, column_type: str, value: Any) -> None:
        """
        Profile data for a column to track observed values.
        
        Args:
            column_name: Name of the column.
            column_type: PostgreSQL type of the column.
            value: The value to profile.
        """
        if self._current_batch:
            self._current_batch.update_data_profile(column_name, column_type, value)
    
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
    
    def export_all(self) -> dict[str, str]:
        """
        Export all reports: errors CSV, summary JSON, model health, and latest run summary.
        
        Returns:
            Dictionary of export paths.
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        paths = {}
        
        # Export errors CSV
        paths["csv"] = self._export_csv(timestamp)
        
        # Export summary JSON
        paths["summary"] = self._export_json(timestamp)
        
        # Export per-model health reports
        paths["model_health"] = self._export_model_health()
        
        # Export sample errors
        paths["sample_errors"] = self._export_sample_errors()
        
        # Export latest run summary
        paths["latest_run"] = self._export_latest_run_summary()
        
        return paths
    
    def _export_csv(self, timestamp: str) -> str:
        """Export errors to CSV file."""
        if not self._all_errors:
            return ""
        
        csv_path = self.errors_dir / f"error_report_{timestamp}.csv"
        
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
        json_path = self.errors_dir / f"summary_{timestamp}.json"
        
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self._sync_report.to_dict(), f, indent=2)
        
        return str(json_path)
    
    def _export_model_health(self) -> str:
        """Export per-model health reports."""
        for model_name, summary in self._sync_report.models.items():
            table_name = summary.table_name or model_name.replace(".", "_")
            filepath = self.model_health_dir / f"{table_name}.json"
            
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(summary.to_full_dict(), f, indent=2)
        
        return str(self.model_health_dir)
    
    def _export_sample_errors(self) -> str:
        """Export sample errors per model."""
        for model_name, summary in self._sync_report.models.items():
            table_name = summary.table_name or model_name.replace(".", "_")
            filepath = self.sample_errors_dir / f"{table_name}.json"
            
            sample_data = {
                cat.value: samples 
                for cat, samples in summary.sample_records.items()
            }
            
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(sample_data, f, indent=2)
        
        return str(self.sample_errors_dir)
    
    def _export_latest_run_summary(self) -> str:
        """Export latest run summary with top issues."""
        filepath = self.reports_dir / "latest_run_summary.json"
        
        # Get top problem models
        top_models = sorted(
            self._sync_report.models.items(),
            key=lambda x: x[1].failed,
            reverse=True,
        )[:10]
        
        # Get top problem columns
        all_column_failures = []
        for model_name, summary in self._sync_report.models.items():
            for col, count in summary.errors_by_column.items():
                all_column_failures.append({
                    "model": model_name,
                    "table": summary.table_name or model_name.replace(".", "_"),
                    "column": col,
                    "failures": count,
                })
        
        top_columns = sorted(all_column_failures, key=lambda x: x["failures"], reverse=True)[:20]
        
        summary_data = {
            "run_timestamp": self._sync_report.run_timestamp.isoformat(),
            "total_processed": self._sync_report.get_total_processed(),
            "total_success": self._sync_report.get_total_success(),
            "total_failed": self._sync_report.get_total_failed(),
            "overall_success_rate": round(100 - self._sync_report.get_overall_error_rate(), 2),
            "top_problem_models": [
                {
                    "model": name,
                    "table": s.table_name or name.replace(".", "_"),
                    "failures": s.failed,
                    "error_rate": round(s.error_rate, 2),
                }
                for name, s in top_models
            ],
            "top_problem_columns": top_columns,
        }
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, indent=2)
        
        return str(filepath)
    
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
                    if sample["value_preview"]:
                        preview = sample["value_preview"]
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
