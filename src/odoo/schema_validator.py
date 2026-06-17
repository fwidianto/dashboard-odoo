"""Schema Validation Pipeline Module.

This module orchestrates the complete schema validation workflow:
1. Schema Discovery - Discover Odoo model metadata
2. Schema Validation - Validate discovered schema
3. Schema Migration - Apply necessary migrations
4. Index Validation - Ensure indexes are correct
5. Metadata Snapshot - Record schema state

This is the "Phase 10" component that runs at startup before sync begins.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any, TYPE_CHECKING

from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.clients.odoo_client import OdooClient
    from src.clients.postgres_client import PostgresClient
    from src.odoo.metadata_discovery import OdooModelMetadata, OdooMetadataDiscovery


@dataclass
class ValidationResult:
    """Result of a validation check."""
    
    phase: str
    passed: bool
    message: str
    details: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class SchemaValidationReport:
    """Complete report of schema validation."""
    
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    results: list[ValidationResult] = field(default_factory=list)
    models_discovered: int = 0
    models_validated: int = 0
    tables_created: int = 0
    columns_added: int = 0
    columns_migrated: int = 0
    indexes_created: int = 0
    snapshots_recorded: int = 0
    
    @property
    def is_valid(self) -> bool:
        """Check if all validations passed."""
        return all(r.passed for r in self.results)
    
    def get_summary(self) -> dict:
        """Get summary dictionary."""
        return {
            "valid": self.is_valid,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "models_discovered": self.models_discovered,
            "models_validated": self.models_validated,
            "tables_created": self.tables_created,
            "columns_added": self.columns_added,
            "columns_migrated": self.columns_migrated,
            "indexes_created": self.indexes_created,
            "snapshots_recorded": self.snapshots_recorded,
            "phase_results": [
                {
                    "phase": r.phase,
                    "passed": r.passed,
                    "message": r.message,
                    "errors": r.errors,
                    "warnings": r.warnings,
                }
                for r in self.results
            ],
        }


class SchemaValidationPipeline:
    """
    Orchestrates the complete schema validation workflow.
    
    This pipeline runs at startup and ensures:
    1. Odoo metadata is discovered
    2. PostgreSQL schema matches Odoo schema
    3. All necessary migrations are applied
    4. Indexes are created/updated
    5. Schema snapshots are recorded
    
    Usage:
        pipeline = SchemaValidationPipeline(odoo_client, postgres_client)
        report = pipeline.run(["product.template", "sale.order"])
        
        if not report.is_valid:
            print("Schema validation failed!")
            for result in report.results:
                if not result.passed:
                    print(f"  {result.phase}: {result.errors}")
        
        if report.is_valid:
            print("Starting sync...")
    """
    
    def __init__(
        self,
        odoo_client: "OdooClient",
        postgres_client: "PostgresClient",
    ):
        """
        Initialize the validation pipeline.
        
        Args:
            odoo_client: Authenticated OdooClient.
            postgres_client: Connected PostgresClient.
        """
        self._odoo = odoo_client
        self._postgres = postgres_client
        self._logger = get_logger("schema_validation_pipeline")
    
    def run(
        self,
        models: list[str],
        skip_migrations: bool = False,
    ) -> SchemaValidationReport:
        """
        Run the complete validation pipeline.
        
        Args:
            models: List of Odoo model names to validate.
            skip_migrations: If True, only validate without applying migrations.
            
        Returns:
            SchemaValidationReport with results of all checks.
        """
        from src.odoo.metadata_discovery import OdooMetadataDiscovery
        
        report = SchemaValidationReport()
        
        # Phase 1: Schema Discovery
        self._logger.info("Phase 1: Schema Discovery starting", models=len(models))
        discovery_result = self._run_discovery_phase(models)
        report.results.append(discovery_result)
        report.models_discovered = len(models)
        
        if not discovery_result.passed:
            self._logger.error("Schema discovery failed, aborting pipeline")
            report.completed_at = datetime.utcnow()
            return report
        
        # Phase 2: Schema Validation
        self._logger.info("Phase 2: Schema Validation starting")
        validation_result = self._run_validation_phase(discovery_result.details["metadata"])
        report.results.append(validation_result)
        report.models_validated = len([
            m for m in report.results if m.phase == "SchemaValidation" and m.passed
        ])
        
        # Phase 3: Schema Migration
        if not skip_migrations:
            self._logger.info("Phase 3: Schema Migration starting")
            migration_result = self._run_migration_phase(validation_result.details.get("config_models", {}))
            report.results.append(migration_result)
            report.tables_created = migration_result.details.get("tables_created", 0)
            report.columns_added = migration_result.details.get("columns_added", 0)
            report.columns_migrated = migration_result.details.get("columns_migrated", 0)
            report.indexes_created = migration_result.details.get("indexes_created", 0)
        
        # Phase 4: Index Validation
        self._logger.info("Phase 4: Index Validation starting")
        index_result = self._run_index_phase(validation_result.details.get("config_models", {}))
        report.results.append(index_result)
        
        # Phase 5: Metadata Snapshot
        self._logger.info("Phase 5: Metadata Snapshot starting")
        snapshot_result = self._run_snapshot_phase(discovery_result.details["metadata"])
        report.results.append(snapshot_result)
        report.snapshots_recorded = snapshot_result.details.get("snapshots_recorded", 0)
        
        report.completed_at = datetime.utcnow()
        
        # Log summary
        self._logger.info(
            "Schema validation pipeline complete",
            valid=report.is_valid,
            models_discovered=report.models_discovered,
            tables_created=report.tables_created,
            columns_added=report.columns_added,
            columns_migrated=report.columns_migrated,
        )
        
        return report
    
    def _run_discovery_phase(self, models: list[str]) -> ValidationResult:
        """Phase 1: Discover Odoo metadata."""
        from src.odoo.metadata_discovery import OdooMetadataDiscovery
        
        result = ValidationResult(
            phase="SchemaDiscovery",
            passed=False,
            message="",
        )
        
        try:
            discovery = OdooMetadataDiscovery(self._odoo)
            metadata = discovery.discover_models(models)
            
            if len(metadata) != len(models):
                missing = set(models) - set(metadata.keys())
                result.errors.append(f"Failed to discover models: {missing}")
                return result
            
            result.passed = True
            result.message = f"Successfully discovered {len(metadata)} models"
            result.details["metadata"] = metadata
            
        except Exception as e:
            result.errors.append(str(e))
            result.message = "Schema discovery failed"
        
        return result
    
    def _run_validation_phase(
        self,
        metadata: dict[str, "OdooModelMetadata"],
    ) -> ValidationResult:
        """Phase 2: Validate discovered schema."""
        from src.odoo.metadata_discovery import generate_field_configs
        from src.models.config import ModelConfig, FieldConfig
        
        result = ValidationResult(
            phase="SchemaValidation",
            passed=False,
            message="",
        )
        
        config_models = {}
        
        try:
            for model_name, model_metadata in metadata.items():
                # Generate field configs from discovered metadata
                field_configs = generate_field_configs(model_metadata)
                
                if not field_configs:
                    result.warnings.append(f"Model {model_name} has no syncable fields")
                    continue
                
                # Build ModelConfig
                model_config = ModelConfig(
                    odoo_model=model_name,
                    postgres_table=model_metadata.table,
                    fields=[
                        FieldConfig(**fc) for fc in field_configs
                    ],
                )
                
                config_models[model_name] = model_config
            
            result.passed = True
            result.message = f"Validated {len(config_models)} models"
            result.details["config_models"] = config_models
            
        except Exception as e:
            result.errors.append(str(e))
            result.message = "Schema validation failed"
        
        return result
    
    def _run_migration_phase(
        self,
        config_models: dict[str, "ModelConfig"],
    ) -> ValidationResult:
        """Phase 3: Apply schema migrations."""
        from src.models.config import ModelConfig
        
        result = ValidationResult(
            phase="SchemaMigration",
            passed=True,  # Migrations are best-effort
            message="",
            details={},
        )
        
        tables_created = 0
        columns_added = 0
        columns_migrated = 0
        indexes_created = 0
        
        try:
            for model_name, model_config in config_models.items():
                migration_report = self._postgres.ensure_table_schema(model_config)
                
                tables_created += 1 if migration_report.get("table_created", False) else 0
                columns_added += len(migration_report.get("added_columns", []))
                columns_migrated += len(migration_report.get("migrated_columns", []))
            
            result.message = f"Migration complete: {tables_created} tables, {columns_added} cols added, {columns_migrated} migrated"
            result.details = {
                "tables_created": tables_created,
                "columns_added": columns_added,
                "columns_migrated": columns_migrated,
                "indexes_created": indexes_created,
            }
            
        except Exception as e:
            result.passed = False
            result.errors.append(str(e))
            result.message = "Schema migration failed"
        
        return result
    
    def _run_index_phase(
        self,
        config_models: dict[str, "ModelConfig"],
    ) -> ValidationResult:
        """Phase 4: Validate and create indexes."""
        from src.models.config import ModelConfig
        
        result = ValidationResult(
            phase="IndexValidation",
            passed=True,
            message="",
        )
        
        indexes_created = 0
        
        try:
            for model_name, model_config in config_models.items():
                # Ensure indexes exist
                created = self._postgres.create_indexes_for_model(model_config)
                indexes_created += len(created)
            
            result.message = f"Index validation complete: {indexes_created} indexes created"
            result.details = {"indexes_created": indexes_created}
            
        except Exception as e:
            result.warnings.append(str(e))
            result.message = "Index validation completed with warnings"
        
        return result
    
    def _run_snapshot_phase(
        self,
        metadata: dict[str, "OdooModelMetadata"],
    ) -> ValidationResult:
        """Phase 5: Record metadata snapshot."""
        from src.odoo.metadata_discovery import OdooModelMetadata
        
        result = ValidationResult(
            phase="MetadataSnapshot",
            passed=True,
            message="",
        )
        
        snapshots_recorded = 0
        
        try:
            for model_name, model_metadata in metadata.items():
                self._record_snapshot(model_metadata)
                snapshots_recorded += 1
            
            result.message = f"Recorded {snapshots_recorded} metadata snapshots"
            result.details = {"snapshots_recorded": snapshots_recorded}
            
        except Exception as e:
            result.warnings.append(str(e))
            result.message = "Snapshot recording completed with warnings"
        
        return result
    
    def _record_snapshot(self, metadata: "OdooModelMetadata") -> None:
        """Record a metadata snapshot to the database."""
        from sqlalchemy import text
        
        # Create snapshot table if not exists
        create_table_sql = text("""
            CREATE TABLE IF NOT EXISTS sync_schema_snapshot (
                id SERIAL PRIMARY KEY,
                model VARCHAR(128) NOT NULL,
                field_name VARCHAR(128) NOT NULL,
                field_type VARCHAR(64),
                relation VARCHAR(128),
                required BOOLEAN DEFAULT FALSE,
                indexed BOOLEAN DEFAULT FALSE,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(model, field_name)
            )
        """)
        
        with self._postgres.engine.connect() as conn:
            conn.execute(create_table_sql)
            conn.commit()
        
        # Insert/update snapshot records
        for field_name, field_def in metadata.fields.items():
            if not field_def.store:
                continue
            
            upsert_sql = text("""
                INSERT INTO sync_schema_snapshot 
                (model, field_name, field_type, relation, required, indexed, last_seen)
                VALUES (:model, :field_name, :field_type, :relation, :required, :indexed, CURRENT_TIMESTAMP)
                ON CONFLICT (model, field_name)
                DO UPDATE SET
                    field_type = EXCLUDED.field_type,
                    relation = EXCLUDED.relation,
                    required = EXCLUDED.required,
                    indexed = EXCLUDED.indexed,
                    last_seen = CURRENT_TIMESTAMP
            """)
            
            with self._postgres.engine.connect() as conn:
                conn.execute(upsert_sql, {
                    "model": metadata.model,
                    "field_name": field_name,
                    "field_type": field_def.field_type,
                    "relation": field_def.relation,
                    "required": field_def.required,
                    "indexed": field_def.index,
                })
                conn.commit()


class SyncHealthReporter:
    """
    Generates sync health reports.
    
    Creates reports in:
    - reports/sync_health_report_TIMESTAMP.txt
    - reports/error_samples_TIMESTAMP.json
    """
    
    def __init__(self, reports_dir: str = "reports"):
        """
        Initialize the health reporter.
        
        Args:
            reports_dir: Directory to write reports to.
        """
        self._reports_dir = reports_dir
        self._logger = get_logger("sync_health_reporter")
    
    def generate_report(
        self,
        model_results: list[dict],
        error_samples: list[dict],
    ) -> dict[str, str]:
        """
        Generate sync health reports.
        
        Args:
            model_results: List of dicts with model sync results.
            error_samples: List of error sample records.
            
        Returns:
            Dict with paths to generated reports.
        """
        import os
        from datetime import datetime
        
        os.makedirs(self._reports_dir, exist_ok=True)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        paths = {}
        
        # Generate text report
        txt_path = os.path.join(self._reports_dir, f"sync_health_report_{timestamp}.txt")
        self._generate_text_report(txt_path, model_results)
        paths["health_report"] = txt_path
        
        # Generate error samples
        if error_samples:
            json_path = os.path.join(self._reports_dir, f"error_samples_{timestamp}.json")
            self._generate_error_samples(json_path, error_samples)
            paths["error_samples"] = json_path
        
        return paths
    
    def _generate_text_report(self, path: str, model_results: list[dict]) -> None:
        """Generate the text health report."""
        import os
        
        lines = [
            "=" * 70,
            "SYNC HEALTH REPORT",
            "=" * 70,
            "",
        ]
        
        # Model table
        lines.append(f"{'Model':<35} {'Success':>10} {'Failed':>10} {'Error Rate':>12}")
        lines.append("-" * 70)
        
        total_processed = 0
        total_success = 0
        total_failed = 0
        
        for result in model_results:
            model = result.get("model", "unknown")
            processed = result.get("processed", 0)
            success = result.get("success", 0)
            failed = result.get("failed", 0)
            
            total_processed += processed
            total_success += success
            total_failed += failed
            
            error_rate = (failed / processed * 100) if processed > 0 else 0
            lines.append(f"{model:<35} {success:>10} {failed:>10} {error_rate:>11.2f}%")
        
        lines.append("-" * 70)
        lines.append("")
        lines.append("TOTAL")
        lines.append(f"Processed:           {total_processed}")
        lines.append(f"Success:             {total_success}")
        lines.append(f"Failed:              {total_failed}")
        lines.append(f"Overall Error Rate:  {(total_failed / total_processed * 100):.2f}%" if total_processed > 0 else "N/A")
        lines.append("")
        
        # Top failure causes
        lines.append("=" * 70)
        lines.append("TOP FAILURE CAUSES")
        lines.append("-" * 70)
        
        # Aggregate errors by category
        error_counts = {}
        for result in model_results:
            for cat, count in result.get("errors_by_category", {}).items():
                error_counts[cat] = error_counts.get(cat, 0) + count
        
        # Sort by count
        sorted_errors = sorted(error_counts.items(), key=lambda x: x[1], reverse=True)
        for cat, count in sorted_errors:
            lines.append(f"{cat:<30} {count:>10} records")
        
        lines.append("")
        
        with open(path, "w") as f:
            f.write("\n".join(lines))
        
        self._logger.info("Generated health report", path=path)
    
    def _generate_error_samples(self, path: str, samples: list[dict]) -> None:
        """Generate the error samples JSON file."""
        import json
        
        # Limit to 100 samples per category
        by_category = {}
        for sample in samples:
            cat = sample.get("error_category", "UNKNOWN")
            if cat not in by_category:
                by_category[cat] = []
            if len(by_category[cat]) < 100:
                by_category[cat].append(sample)
        
        output = {
            "generated_at": datetime.utcnow().isoformat(),
            "total_samples": len(samples),
            "samples_by_category": by_category,
        }
        
        with open(path, "w") as f:
            json.dump(output, f, indent=2, default=str)
        
        self._logger.info("Generated error samples", path=path, samples=len(samples))
