"""Production-grade error reporting and diagnostics for sync operations."""

import csv
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from src.reporting.error_enums import ErrorCategory


MAX_SAMPLE_RECORDS = 10
VALUE_PREVIEW_LENGTH = 200


@dataclass
class RootCauseError:
    model: str
    table_name: str
    record_id: Optional[int]
    error_category: ErrorCategory
    error_message: str
    column_name: Optional[str] = None
    value_preview: Optional[str] = None
    payload: Optional[dict] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "table": self.table_name,
            "record_id": self.record_id,
            "error_category": self.error_category.value,
            "column": self.column_name,
            "error_message": self.error_message,
            "value_preview": self.value_preview,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ModelErrorStats:
    """Model error statistics with proper attribute access."""
    model: str
    table_name: str = ""
    processed: int = 0
    success: int = 0
    failed: int = 0
    cascade_failures: int = 0
    root_causes: dict = field(default_factory=lambda: defaultdict(int))
    first_root_cause: Optional[RootCauseError] = None
    
    @property
    def error_rate(self) -> float:
        if self.processed == 0:
            return 0.0
        return (self.failed / self.processed) * 100
    
    @property
    def errors_by_category(self) -> dict:
        """Return dict of errors by category (for SchemaRecommender compatibility)."""
        return dict(self.root_causes)
    
    @property
    def failure_categories(self) -> dict:
        """Alias for errors_by_category."""
        return self.errors_by_category
    
    def add_success(self, count: int = 1):
        self.processed += count
        self.success += count
    
    def add_error(self, category: ErrorCategory, record_id: Optional[int] = None,
                  error_message: str = "", column_name: Optional[str] = None,
                  value_preview: Optional[str] = None, payload: Optional[dict] = None,
                  is_cascade: bool = False):
        self.processed += 1
        
        if is_cascade:
            self.cascade_failures += 1
            return
        
        self.failed += 1
        category_str = category.value
        self.root_causes[category_str] = self.root_causes.get(category_str, 0) + 1
        
        if self.first_root_cause is None:
            self.first_root_cause = RootCauseError(
                model=self.model,
                table_name=self.table_name,
                record_id=record_id,
                error_category=category,
                error_message=error_message,
                column_name=column_name,
                value_preview=value_preview,
                payload=payload,
            )


class BatchSummary:
    """Batch summary object for compatibility with SchemaRecommender."""
    def __init__(self, model: str, table_name: str, stats: ModelErrorStats):
        self.model = model
        self.table_name = table_name
        self.stats = stats
    
    @property
    def errors_by_category(self) -> dict:
        return self.stats.errors_by_category
    
    @property
    def failure_categories(self) -> dict:
        return self.stats.failure_categories
    
    @property
    def processed(self) -> int:
        return self.stats.processed
    
    @property
    def success(self) -> int:
        return self.stats.success
    
    @property
    def failed(self) -> int:
        return self.stats.failed
    
    @property
    def cascade_failures(self) -> int:
        return self.stats.cascade_failures
    
    @property
    def error_rate(self) -> float:
        return self.stats.error_rate


class SyncReport:
    """Sync report object for compatibility."""
    def __init__(self, models: dict):
        self.models = models


class ErrorReporter:
    """Error reporter matching SyncEngine API."""
    
    def __init__(self, output_dir: str = "reports/errors", debug_mode: bool = False):
        self.output_dir = Path(output_dir)
        self.debug_mode = debug_mode
        self.debug_dir = Path("logs/debug")
        self.model_stats: dict = {}
        self.root_causes: list = []
        self.debug_samples: dict = defaultdict(list)
        self._current_model: Optional[str] = None
        self._current_table: Optional[str] = None
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if self.debug_mode:
            self.debug_dir.mkdir(parents=True, exist_ok=True)
    
    def start_batch(self, model: str, table_name: str = ""):
        self._current_model = model
        self._current_table = table_name
        if model not in self.model_stats:
            self.model_stats[model] = ModelErrorStats(model=model, table_name=table_name)
    
    def end_batch(self):
        self._current_model = None
        self._current_table = None
    
    def record_success(self, count: int = 1, model: Optional[str] = None):
        model = model or self._current_model
        if model:
            stats = self.get_or_create_stats(model, self._current_table)
            stats.add_success(count)
    
    def record_failure(self, category: ErrorCategory, record_id: Optional[int] = None,
                       error_message: str = "", column_name: Optional[str] = None,
                       value: Any = None, model: Optional[str] = None):
        model = model or self._current_model
        if model:
            self.record_error(
                model=model, table_name=self._current_table or "",
                category=category, record_id=record_id, error_message=error_message,
                column_name=column_name, value=value,
            )
    
    def record_error(self, model: str, table_name: str, category: ErrorCategory,
                     record_id: Optional[int] = None, error_message: str = "",
                     column_name: Optional[str] = None, value: Any = None,
                     payload: Optional[dict] = None):
        stats = self.get_or_create_stats(model, table_name)
        value_preview = str(value)[:VALUE_PREVIEW_LENGTH] if value is not None else None
        is_cascade = category == ErrorCategory.TRANSACTION_ABORTED
        is_first_error = not is_cascade and stats.first_root_cause is None
        
        stats.add_error(category=category, record_id=record_id, error_message=error_message,
                        column_name=column_name, value_preview=value_preview,
                        payload=payload, is_cascade=is_cascade)
        
        if is_first_error:
            root_cause = RootCauseError(model=model, table_name=table_name, record_id=record_id,
                                        error_category=category, error_message=error_message,
                                        column_name=column_name, value_preview=value_preview, payload=payload)
            self.root_causes.append(root_cause)
        
        if self.debug_mode and len(self.debug_samples[model]) < 50:
            self.debug_samples[model].append({"record_id": record_id, "category": category.value,
                                              "error_message": error_message, "column": column_name,
                                              "value_preview": value_preview, "is_cascade": is_cascade})
    
    def get_batch_summary(self) -> Optional[BatchSummary]:
        if self._current_model and self._current_model in self.model_stats:
            return BatchSummary(model=self._current_model, table_name=self._current_table or "",
                              stats=self.model_stats[self._current_model])
        return None
    
    def generate_report(self) -> dict:
        return self.get_summary()
    
    def save_report(self, filename: Optional[str] = None) -> str:
        return self.export_json(filename)
    
    def print_batch_summary(self):
        self.print_summary()
    
    def profile_data(self, column_name: str, column_type: str, value: Any) -> None:
        pass
    
    def has_errors(self) -> bool:
        return any(stats.failed > 0 for stats in self.model_stats.values())
    
    def export_all(self) -> None:
        self.export_json()
        self.export_csv()
        self.export_root_causes()
        if self.debug_mode:
            self.export_debug_samples()
    
    def get_sync_report(self) -> SyncReport:
        return SyncReport(models=self.model_stats)
    
    def get_or_create_stats(self, model: str, table_name: str = "") -> ModelErrorStats:
        if model not in self.model_stats:
            self.model_stats[model] = ModelErrorStats(model=model, table_name=table_name)
        return self.model_stats[model]
    
    def get_summary(self) -> dict:
        total_processed = sum(s.processed for s in self.model_stats.values())
        total_success = sum(s.success for s in self.model_stats.values())
        total_failed = sum(s.failed for s in self.model_stats.values())
        return {
            "models": {model: {"processed": stats.processed, "success": stats.success,
                               "failed": stats.failed, "cascade_failures": stats.cascade_failures,
                               "error_rate": stats.error_rate, "errors_by_category": stats.errors_by_category}
                      for model, stats in self.model_stats.items()},
            "total": {"processed": total_processed, "success": total_success, "failed": total_failed,
                      "error_rate": (total_failed / total_processed * 100) if total_processed > 0 else 0}
        }
    
    def print_summary(self):
        print("\n" + "=" * 70)
        print("SYNC HEALTH REPORT")
        print("=" * 70)
        print(f'{"Model":<35} {"Success":>10} {"Failed":>10} {"Rate":>10}')
        print("-" * 70)
        
        total_processed = total_success = total_failed = 0
        for model, stats in self.model_stats.items():
            print(f"{model:<35} {stats.success:>10} {stats.failed:>10} {stats.error_rate:>9.2f}%")
            total_processed += stats.processed
            total_success += stats.success
            total_failed += stats.failed
        
        total_rate = (total_failed / total_processed * 100) if total_processed > 0 else 0
        print("-" * 70)
        print(f"{'TOTAL':<35} {total_success:>10} {total_failed:>10} {total_rate:>9.2f}%")
        print()
        
        if self.root_causes:
            print("=" * 70)
            print("ROOT CAUSE ANALYSIS")
            print("=" * 70)
            for model, stats in self.model_stats.items():
                if stats.first_root_cause:
                    rc = stats.first_root_cause
                    print(f"Model: {model}")
                    print(f"  Primary Failure: {rc.error_category.value}")
                    print(f"  Column: {rc.column_name or 'N/A'}")
                    print(f"  Record ID: {rc.record_id}")
                    print(f"  Cascade Failures: {stats.cascade_failures}")
                    print()
            print()
        
        all_errors = defaultdict(int)
        for rc in self.root_causes:
            all_errors[rc.error_category.value] += 1
        if all_errors:
            print("=" * 70)
            print("ERROR BREAKDOWN BY TYPE")
            print("=" * 70)
            for cat, count in sorted(all_errors.items(), key=lambda x: -x[1]):
                print(f"  {cat:<25} {count:>5} records")
            print()
    
    def export_json(self, filename: Optional[str] = None) -> str:
        if filename is None:
            filename = f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.output_dir / filename
        with open(filepath, "w") as f:
            json.dump(self.get_summary(), f, indent=2)
        return str(filepath)
    
    def export_csv(self, filename: Optional[str] = None) -> str:
        if filename is None:
            filename = f"error_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = self.output_dir / filename
        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["model", "record_id", "error_category", "column_name", "error_message", "value_preview", "timestamp"])
            for rc in self.root_causes:
                writer.writerow([rc.model, rc.record_id, rc.error_category.value, rc.column_name,
                               rc.error_message[:500], rc.value_preview, rc.timestamp.isoformat()])
        return str(filepath)
    
    def export_root_causes(self, filename: str = "logs/root_causes.json") -> str:
        filepath = Path(filename)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        data = {"exported_at": datetime.now().isoformat(), "total_root_causes": len(self.root_causes),
                "root_causes": [rc.to_dict() for rc in self.root_causes]}
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        return str(filepath)
    
    def export_debug_samples(self) -> dict:
        result = {}
        for model, samples in self.debug_samples.items():
            filepath = self.debug_dir / f"{model.replace('.', '_')}.json"
            with open(filepath, "w") as f:
                json.dump({"model": model, "sample_count": len(samples), "samples": samples}, f, indent=2)
            result[model] = str(filepath)
        return result
