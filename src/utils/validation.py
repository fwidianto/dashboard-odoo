"""Validation module for configuration and connections.

This module provides comprehensive validation for:
- Environment variables
- Odoo connection
- PostgreSQL connection
- models.yaml configuration

All validation errors are user-friendly without stack traces.
"""

from dataclasses import dataclass
from typing import Optional
import xmlrpc.client as xmlrpc_lib

from src.utils.settings import get_settings, Settings
from src.utils.config_loader import get_config, ConfigLoader
from src.utils.logging import get_logger, setup_logging


@dataclass
class ValidationError:
    """Represents a validation error."""
    category: str  # 'env', 'odoo', 'postgres', 'config'
    message: str
    hint: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of validation checks."""
    is_valid: bool
    errors: list[ValidationError]
    warnings: list[str]

    def __str__(self) -> str:
        """Format validation result for display."""
        if self.is_valid:
            return "✓ All validation checks passed"
        
        lines = ["✗ Validation failed:\n"]
        for error in self.errors:
            lines.append(f"  [{error.category.upper()}] {error.message}")
            if error.hint:
                lines.append(f"    → {error.hint}")
        
        if self.warnings:
            lines.append("\nWarnings:")
            for warning in self.warnings:
                lines.append(f"  ⚠ {warning}")
        
        return "\n".join(lines)


class Validator:
    """
    Comprehensive validator for the Odoo-PostgreSQL sync platform.
    
    Provides user-friendly validation without exposing technical stack traces.
    """

    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize validator.
        
        Args:
            settings: Optional settings instance. If None, loads from environment.
        """
        self._logger = get_logger("validator")
        self._settings = settings or get_settings()

    def validate_all(self) -> ValidationResult:
        """
        Run all validation checks.
        
        Returns:
            ValidationResult with all errors and warnings.
        """
        errors = []
        warnings = []
        
        # Validate environment variables
        env_errors, env_warnings = self.validate_environment()
        errors.extend(env_errors)
        warnings.extend(env_warnings)
        
        # Validate Odoo connection
        odoo_errors, odoo_warnings = self.validate_odoo_connection()
        errors.extend(odoo_errors)
        warnings.extend(odoo_warnings)
        
        # Validate PostgreSQL connection
        pg_errors, pg_warnings = self.validate_postgres_connection()
        errors.extend(pg_errors)
        warnings.extend(pg_warnings)
        
        # Validate models.yaml
        config_errors, config_warnings = self.validate_configuration()
        errors.extend(config_errors)
        warnings.extend(config_warnings)
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def validate_environment(self) -> tuple[list[ValidationError], list[str]]:
        """
        Validate environment variables.
        
        Returns:
            Tuple of (errors, warnings).
        """
        errors = []
        warnings = []
        
        odoo = self._settings.odoo
        pg = self._settings.postgres
        
        # Check Odoo credentials
        if not odoo.has_credentials():
            errors.append(ValidationError(
                category="env",
                message="Odoo authentication not configured",
                hint="Set ODOO_API_KEY (recommended) or ODOO_PASSWORD in your .env file"
            ))
        elif odoo.password and not odoo.api_key:
            warnings.append(
                "Using password authentication to Odoo. "
                "Consider migrating to API key for better security."
            )
        
        # Check Odoo URL
        if not odoo.url or odoo.url == "http://localhost:8069":
            if not odoo.has_credentials():
                errors.append(ValidationError(
                    category="env",
                    message="Odoo URL appears to be using default value",
                    hint="Set ODOO_URL to your Odoo server address (e.g., http://your-odoo:8069)"
                ))
        
        # Check PostgreSQL connection
        if not pg.has_credentials():
            errors.append(ValidationError(
                category="env",
                message="PostgreSQL connection not configured",
                hint="Set POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, and POSTGRES_PASSWORD in your .env file"
            ))
        
        return errors, warnings

    def validate_odoo_connection(self) -> tuple[list[ValidationError], list[str]]:
        """
        Validate Odoo server connection.
        
        Returns:
            Tuple of (errors, warnings).
        """
        errors = []
        warnings = []
        
        odoo = self._settings.odoo
        
        if not odoo.has_credentials():
            # Can't test connection without credentials
            return errors, warnings
        
        try:
            # Test server connectivity
            common_endpoint = f"{odoo.url.rstrip('/')}/xmlrpc/2/common"
            server = xmlrpc_lib.ServerProxy(common_endpoint, allow_none=True)
            version = server.version()
            
            self._logger.info("Odoo server version", version=version)
            
            # Test authentication
            if odoo.api_key:
                # API key auth - test via common endpoint
                uid = server.authenticate(
                    odoo.db,
                    odoo.username,
                    odoo.api_key,
                    {}
                )
                if not uid:
                    errors.append(ValidationError(
                        category="odoo",
                        message="Odoo API key authentication failed",
                        hint="Verify your ODOO_API_KEY is valid and associated with the specified user"
                    ))
            elif odoo.password:
                # Password auth - test via common endpoint
                uid = server.authenticate(
                    odoo.db,
                    odoo.username,
                    odoo.password,
                    {}
                )
                if not uid:
                    errors.append(ValidationError(
                        category="odoo",
                        message="Odoo password authentication failed",
                        hint="Verify your ODOO_USERNAME and ODOO_PASSWORD are correct"
                    ))
                else:
                    warnings.append(
                        "Using password authentication. This is deprecated. "
                        "Please migrate to API key authentication."
                    )
            
        except xmlrpc_lib.ProtocolError as e:
            errors.append(ValidationError(
                category="odoo",
                message=f"Odoo server connection failed: Protocol error",
                hint=f"Check that ODOO_URL is correct ({odoo.url}) and the server is accessible"
            ))
        except xmlrpc_lib.Fault as e:
            if "Authentication failed" in str(e):
                errors.append(ValidationError(
                    category="odoo",
                    message="Odoo authentication failed",
                    hint="Verify your credentials (API key or password) are correct"
                ))
            else:
                errors.append(ValidationError(
                    category="odoo",
                    message=f"Odoo server error: {e.faultString}",
                    hint="Check your Odoo server logs for more details"
                ))
        except ConnectionRefusedError:
            errors.append(ValidationError(
                category="odoo",
                message="Odoo server connection refused",
                hint="Check that the Odoo server is running and ODOO_URL is correct"
            ))
        except Exception as e:
            errors.append(ValidationError(
                category="odoo",
                message=f"Could not connect to Odoo server: {e}",
                hint="Verify ODOO_URL is correct and the server is accessible"
            ))
        
        return errors, warnings

    def validate_postgres_connection(self) -> tuple[list[ValidationError], list[str]]:
        """
        Validate PostgreSQL connection.
        
        Returns:
            Tuple of (errors, warnings).
        """
        errors = []
        warnings = []
        
        pg = self._settings.postgres
        
        if not pg.has_credentials():
            # Can't test connection without credentials
            return errors, warnings
        
        try:
            from sqlalchemy import create_engine, text
            
            engine = create_engine(
                pg.connection_url,
                pool_pre_ping=True,
                connect_args={"connect_timeout": 10}
            )
            
            with engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                result.scalar()
            
            engine.dispose()
            
        except ImportError:
            errors.append(ValidationError(
                category="postgres",
                message="PostgreSQL driver not available",
                hint="Install psycopg2: pip install psycopg2-binary"
            ))
        except Exception as e:
            error_msg = str(e).lower()
            
            if "could not connect to server" in error_msg:
                errors.append(ValidationError(
                    category="postgres",
                    message="PostgreSQL server not reachable",
                    hint=f"Check that POSTGRES_HOST ({pg.host}) is correct and the server is running"
                ))
            elif "authentication failed" in error_msg:
                errors.append(ValidationError(
                    category="postgres",
                    message="PostgreSQL authentication failed",
                    hint="Verify POSTGRES_USER and POSTGRES_PASSWORD are correct"
                ))
            elif "does not exist" in error_msg:
                errors.append(ValidationError(
                    category="postgres",
                    message=f"PostgreSQL database '{pg.db}' does not exist",
                    hint="Create the database first or check POSTGRES_DB is correct"
                ))
            elif "permission denied" in error_msg:
                errors.append(ValidationError(
                    category="postgres",
                    message="PostgreSQL permission denied",
                    hint=f"User '{pg.user}' does not have access to database '{pg.db}'"
                ))
            else:
                errors.append(ValidationError(
                    category="postgres",
                    message=f"PostgreSQL connection failed: {e}",
                    hint="Check your PostgreSQL connection settings"
                ))
        
        return errors, warnings

    def validate_configuration(self) -> tuple[list[ValidationError], list[str]]:
        """
        Validate models.yaml configuration.
        
        Returns:
            Tuple of (errors, warnings).
        """
        errors = []
        warnings = []
        
        try:
            # Try to load the configuration
            loader = ConfigLoader()
            config = loader.load()
            
            if not config.models:
                errors.append(ValidationError(
                    category="config",
                    message="No models configured in models.yaml",
                    hint="Add at least one model definition to config/models.yaml"
                ))
                return errors, warnings
            
            # Validate each model
            for model in config.models:
                # Check for primary key
                pk_count = sum(1 for f in model.fields if f.primary_key)
                if pk_count == 0:
                    errors.append(ValidationError(
                        category="config",
                        message=f"Model '{model.odoo_model}' has no primary key defined",
                        hint=f"Add 'primary_key: true' to the 'id' field in {model.odoo_model}"
                    ))
                elif pk_count > 1:
                    errors.append(ValidationError(
                        category="config",
                        message=f"Model '{model.odoo_model}' has multiple primary keys",
                        hint="Only one field should have 'primary_key: true'"
                    ))
                
                # Check for sync date field
                sync_date_fields = [f for f in model.fields if f.is_sync_date]
                if not sync_date_fields:
                    warnings.append(
                        f"Model '{model.odoo_model}' has no sync date field. "
                        "Incremental sync won't be available."
                    )
                
                # Check for duplicate columns
                columns = [f.postgres_column for f in model.fields]
                if len(columns) != len(set(columns)):
                    errors.append(ValidationError(
                        category="config",
                        message=f"Model '{model.odoo_model}' has duplicate column names",
                        hint="Each field must have a unique postgres_column value"
                    ))
                
                # Check for fields without type
                for field in model.fields:
                    if field.field_type in ("one2many", "many2many"):
                        warnings.append(
                            f"Model '{model.odoo_model}': Field '{field.odoo_field}' "
                            f"is {field.field_type} and will be skipped during sync"
                        )
        
        except FileNotFoundError as e:
            errors.append(ValidationError(
                category="config",
                message="Configuration file not found",
                hint=f"Create config/models.yaml or specify --config path"
            ))
        except Exception as e:
            errors.append(ValidationError(
                category="config",
                message=f"Configuration validation failed: {e}",
                hint="Check config/models.yaml for syntax errors"
            ))
        
        return errors, warnings


def validate() -> ValidationResult:
    """
    Run all validation checks and return results.
    
    Returns:
        ValidationResult with validation status and any errors/warnings.
    """
    validator = Validator()
    return validator.validate_all()


def print_validation_result(result: ValidationResult) -> None:
    """
    Print validation result in a user-friendly format.
    
    Args:
        result: ValidationResult to print.
    """
    print("\n" + "=" * 60)
    print("CONFIGURATION VALIDATION")
    print("=" * 60)
    
    if result.is_valid:
        print("\n✓ All validation checks passed!\n")
        if result.warnings:
            print("Warnings:")
            for warning in result.warnings:
                print(f"  ⚠ {warning}")
    else:
        print("\n✗ Validation failed:\n")
        for error in result.errors:
            print(f"  [{error.category.upper()}] {error.message}")
            if error.hint:
                print(f"    → {error.hint}")
        
        if result.warnings:
            print("\nWarnings:")
            for warning in result.warnings:
                print(f"  ⚠ {warning}")
    
    print("=" * 60)