"""Schema recommendation engine for sync health diagnostics.

This module analyzes observed failures and data profiles to generate
migration suggestions and schema recommendations.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.reporting.error_enums import ErrorCategory


@dataclass
class ColumnRecommendation:
    """Recommendation for a specific column."""
    
    column_name: str
    current_type: str
    recommended_type: str
    reason: str
    estimated_impact: int = 0  # Number of records affected


@dataclass
class ModelRecommendation:
    """Schema recommendations for a model."""
    
    model_name: str
    table_name: str
    column_recommendations: list[ColumnRecommendation] = field(default_factory=list)
    raw_recommendations: dict[str, dict] = field(default_factory=dict)


class SchemaRecommender:
    """
    Schema recommendation engine.
    
    Analyzes observed failures and data profiles to generate
    actionable migration suggestions.
    
    Usage:
        recommender = SchemaRecommender()
        recommender.add_batch_summary(batch_summary)
        recommendations = recommender.generate_recommendations()
        sql = recommender.generate_migration_sql()
        recommender.export()
    """
    
    def __init__(self, reports_dir: Optional[str] = None):
        """
        Initialize the schema recommender.
        
        Args:
            reports_dir: Directory for export files.
        """
        if reports_dir is None:
            self.reports_dir = Path("reports/schema_recommendations")
        else:
            self.reports_dir = Path(reports_dir) / "schema_recommendations"
        
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        
        self._recommendations: dict[str, ModelRecommendation] = {}
    
    def add_batch_summary(self, summary) -> None:
        """
        Add a batch summary to analyze.
        
        Args:
            summary: BatchErrorSummary object with errors and data profiles.
        """
        model_rec = ModelRecommendation(
            model_name=summary.model,
            table_name=summary.table_name or summary.model.replace(".", "_"),
        )
        
        # Analyze errors and generate recommendations
        for cat, count in summary.errors_by_category.items():
            if cat == ErrorCategory.DATA_TOO_LONG:
                self._analyze_data_too_long(summary, model_rec)
            elif cat == ErrorCategory.NUMERIC_OVERFLOW:
                self._analyze_numeric_overflow(summary, model_rec)
            elif cat == ErrorCategory.NULL_CONSTRAINT:
                self._analyze_null_constraint(summary, model_rec)
            elif cat == ErrorCategory.SCHEMA_ERROR:
                self._analyze_schema_mismatch(summary, model_rec)
            elif cat == ErrorCategory.INVALID_TYPE:
                self._analyze_invalid_type(summary, model_rec)
        
        # Analyze data profiles for type recommendations
        self._analyze_data_profiles(summary, model_rec)
        
        self._recommendations[summary.model] = model_rec
    
    def _analyze_data_too_long(
        self, 
        summary, 
        model_rec: ModelRecommendation
    ) -> None:
        """Analyze DATA_TOO_LONG errors and suggest TEXT type."""
        for col, failures in summary.errors_by_column.items():
            if failures > 0:
                # Get current type from data profile
                current_type = "VARCHAR(255)"
                if col in summary.data_profiles:
                    current_type = summary.data_profiles[col].current_type
                
                # Generate recommendation
                model_rec.column_recommendations.append(ColumnRecommendation(
                    column_name=col,
                    current_type=current_type,
                    recommended_type="TEXT",
                    reason=f"{failures} DATA_TOO_LONG failures",
                    estimated_impact=failures,
                ))
                
                # Add to raw recommendations
                model_rec.raw_recommendations[col] = {
                    "current_type": current_type,
                    "recommended_type": "TEXT",
                    "reason": f"{failures} DATA_TOO_LONG failures",
                }
    
    def _analyze_numeric_overflow(
        self, 
        summary, 
        model_rec: ModelRecommendation
    ) -> None:
        """Analyze NUMERIC_OVERFLOW errors and suggest larger numeric type."""
        for col, failures in summary.errors_by_column.items():
            if failures > 0:
                # Get current type from data profile
                current_type = "NUMERIC(12,2)"
                max_value = None
                
                if col in summary.data_profiles:
                    profile = summary.data_profiles[col]
                    current_type = profile.current_type
                    max_value = profile.max_value_observed
                
                # Suggest larger numeric type
                recommended_type = self._suggest_numeric_type(max_value)
                
                model_rec.column_recommendations.append(ColumnRecommendation(
                    column_name=col,
                    current_type=current_type,
                    recommended_type=recommended_type,
                    reason=f"{failures} NUMERIC_OVERFLOW failures",
                    estimated_impact=failures,
                ))
                
                model_rec.raw_recommendations[col] = {
                    "current_type": current_type,
                    "recommended_type": recommended_type,
                    "max_value_observed": max_value,
                    "reason": f"{failures} NUMERIC_OVERFLOW failures",
                }
    
    def _analyze_null_constraint(
        self, 
        summary, 
        model_rec: ModelRecommendation
    ) -> None:
        """Analyze NULL_CONSTRAINT errors."""
        for col, failures in summary.errors_by_column.items():
            if failures > 0:
                current_type = "UNKNOWN"
                if col in summary.data_profiles:
                    current_type = summary.data_profiles[col].current_type
                
                model_rec.column_recommendations.append(ColumnRecommendation(
                    column_name=col,
                    current_type=current_type,
                    recommended_type=" nullable=True",
                    reason=f"{failures} NULL_CONSTRAINT failures - column should allow NULL",
                    estimated_impact=failures,
                ))
    
    def _analyze_schema_mismatch(
        self, 
        summary, 
        model_rec: ModelRecommendation
    ) -> None:
        """Analyze SCHEMA_ERROR errors."""
        for col, failures in summary.errors_by_column.items():
            if failures > 0:
                model_rec.column_recommendations.append(ColumnRecommendation(
                    column_name=col,
                    current_type="UNKNOWN",
                    recommended_type="Verify column exists in source",
                    reason=f"{failures} SCHEMA_ERROR failures",
                    estimated_impact=failures,
                ))
    
    def _analyze_invalid_type(
        self, 
        summary, 
        model_rec: ModelRecommendation
    ) -> None:
        """Analyze INVALID_TYPE errors."""
        for col, failures in summary.errors_by_column.items():
            if failures > 0:
                model_rec.column_recommendations.append(ColumnRecommendation(
                    column_name=col,
                    current_type="UNKNOWN",
                    recommended_type="Verify type compatibility",
                    reason=f"{failures} INVALID_TYPE failures",
                    estimated_impact=failures,
                ))
    
    def _analyze_data_profiles(
        self, 
        summary, 
        model_rec: ModelRecommendation
    ) -> None:
        """Analyze data profiles for proactive recommendations."""
        for col, profile in summary.data_profiles.items():
            # Skip if already has a recommendation
            existing = [r for r in model_rec.column_recommendations if r.column_name == col]
            if existing:
                continue
            
            # Check for long strings that haven't failed yet
            if profile.max_length_observed > 1000:
                model_rec.column_recommendations.append(ColumnRecommendation(
                    column_name=col,
                    current_type=profile.current_type,
                    recommended_type="TEXT",
                    reason=f"Max observed length {profile.max_length_observed} exceeds typical VARCHAR limits",
                    estimated_impact=0,
                ))
            
            # Check for large numeric values
            if profile.max_value_observed and abs(profile.max_value_observed) > 1e12:
                recommended = self._suggest_numeric_type(profile.max_value_observed)
                if recommended != profile.current_type:
                    model_rec.column_recommendations.append(ColumnRecommendation(
                        column_name=col,
                        current_type=profile.current_type,
                        recommended_type=recommended,
                        reason=f"Max observed value {profile.max_value_observed} may exceed type limits",
                        estimated_impact=0,
                    ))
    
    def _suggest_numeric_type(self, max_value: Optional[float]) -> str:
        """Suggest appropriate NUMERIC type based on value magnitude."""
        if max_value is None:
            return "NUMERIC(20,4)"
        
        abs_value = abs(max_value)
        
        if abs_value > 1e18:
            return "NUMERIC(30,6)"
        elif abs_value > 1e12:
            return "NUMERIC(25,6)"
        elif abs_value > 1e9:
            return "NUMERIC(20,6)"
        elif abs_value > 1e6:
            return "NUMERIC(15,4)"
        else:
            return "NUMERIC(14,4)"
    
    def generate_recommendations(self) -> dict:
        """
        Generate recommendations dictionary.
        
        Returns:
            Dictionary of recommendations by model.
        """
        result = {}
        for model, rec in self._recommendations.items():
            result[model] = {
                "table": rec.table_name,
                "columns": rec.raw_recommendations,
            }
        return result
    
    def generate_migration_sql(self) -> str:
        """
        Generate SQL migration script.
        
        Returns:
            SQL script with ALTER TABLE statements.
        """
        sql_parts = ["-- Auto-generated schema migration script"]
        sql_parts.append(f"-- Generated: {datetime.utcnow().isoformat()}")
        sql_parts.append("")
        sql_parts.append("BEGIN;")
        sql_parts.append("")
        
        for model, rec in self._recommendations.items():
            if not rec.column_recommendations:
                continue
            
            sql_parts.append(f"-- Recommendations for {rec.table_name} ({model})")
            sql_parts.append(f"ALTER TABLE {rec.table_name}")
            
            alterations = []
            for col_rec in rec.column_recommendations:
                if col_rec.recommended_type == "TEXT":
                    alterations.append(f'  ALTER COLUMN {col_rec.column_name} TYPE TEXT')
                elif col_rec.recommended_type.startswith("NUMERIC"):
                    alterations.append(f'  ALTER COLUMN {col_rec.column_name} TYPE {col_rec.recommended_type}')
                elif "nullable" in col_rec.recommended_type.lower():
                    alterations.append(f'  ALTER COLUMN {col_rec.column_name} DROP NOT NULL')
                elif "verify" in col_rec.recommended_type.lower():
                    alterations.append(f"  -- {col_rec.column_name}: {col_rec.reason}")
            
            if alterations:
                sql_parts.append(",".join(alterations[:3]))  # Limit to 3 per statement
                sql_parts.append(";")
                sql_parts.append("")
        
        sql_parts.append("COMMIT;")
        sql_parts.append("")
        sql_parts.append("-- Run VACUUM ANALYZE after migrations")
        sql_parts.append("-- VACUUM ANALYZE;")
        
        return "\n".join(sql_parts)
    
    def export(self) -> dict[str, str]:
        """
        Export recommendations to files.
        
        Returns:
            Dictionary of exported file paths.
        """
        paths = {}
        
        # Export JSON recommendations
        json_path = self.reports_dir / "recommendations.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self.generate_recommendations(), f, indent=2)
        paths["recommendations"] = str(json_path)
        
        # Export SQL migration script
        sql_path = self.reports_dir / "migration_suggestions.sql"
        with open(sql_path, "w", encoding="utf-8") as f:
            f.write(self.generate_migration_sql())
        paths["migration_sql"] = str(sql_path)
        
        return paths
    
    def print_recommendations(self) -> None:
        """Print recommendations to console."""
        if not self._recommendations:
            print("\nNo schema recommendations.")
            return
        
        print("\n" + "=" * 70)
        print("SCHEMA RECOMMENDATIONS")
        print("=" * 70)
        
        for model, rec in self._recommendations.items():
            if not rec.column_recommendations:
                continue
            
            print(f"\n{model} ({rec.table_name}):")
            print("-" * 50)
            
            for col_rec in rec.column_recommendations:
                impact = f"[{col_rec.estimated_impact} failures]" if col_rec.estimated_impact > 0 else ""
                print(f"  {col_rec.column_name}:")
                print(f"    Current:  {col_rec.current_type}")
                print(f"    Suggested: {col_rec.recommended_type}")
                print(f"    Reason: {col_rec.reason} {impact}")
        
        print("\n" + "=" * 70)
