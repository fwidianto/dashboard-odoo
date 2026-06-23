"""Application settings using Pydantic settings management."""

import os
import sys
from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class OdooSettings(BaseSettings):
    """Odoo connection settings."""

    # Use flat env var names: ODOO_URL, ODOO_DB, etc.
    url: str = Field(default="http://localhost:8069", description="Odoo server URL")
    db: str = Field(default="odoo_db", description="Odoo database name")
    username: str = Field(default="admin", description="Odoo username")
    
    # API Key authentication (preferred)
    api_key: Optional[str] = Field(default=None, description="Odoo API key for authentication")
    
    # Password authentication (deprecated, fallback only)
    password: Optional[str] = Field(default=None, description="Odoo password (deprecated, use API key)")
    
    api_version: int = Field(default=17, description="Odoo API version")

    # Environment variable mapping for flat naming
    model_config = SettingsConfigDict(
        env_nested_delimiter=None,  # Use flat names
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode='after')
    def validate_auth_method(self):
        """Validate authentication method and warn about password usage."""
        if self.api_key and self.password:
            # Both provided - prefer API key
            import warnings
            warnings.warn(
                "Both API_KEY and PASSWORD provided. Using API_KEY authentication. "
                "Consider removing PASSWORD for security.",
                DeprecationWarning,
                stacklevel=2
            )
        # Don't require auth for basic validation - only require during connection test
        return self
    
    @property
    def auth_method(self) -> Literal["api_key", "password"]:
        """Return the authentication method being used."""
        if self.api_key:
            return "api_key"
        return "password"
    
    def has_credentials(self) -> bool:
        """Check if credentials are configured."""
        return bool(self.api_key or self.password)


class PostgresSettings(BaseSettings):
    """PostgreSQL connection settings."""

    host: str = Field(default="localhost", description="PostgreSQL host")
    port: int = Field(default=5432, description="PostgreSQL port")
    db: str = Field(default="sync_db", description="PostgreSQL database name")
    user: str = Field(default="sync_user", description="PostgreSQL user")
    password: str = Field(default="", description="PostgreSQL password")

    model_config = SettingsConfigDict(
        env_nested_delimiter=None,  # Use flat names
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def connection_url(self) -> str:
        """Generate SQLAlchemy connection URL."""
        return (
            f"postgresql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.db}"
        )

    @property
    def async_connection_url(self) -> str:
        """Generate async SQLAlchemy connection URL."""
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.db}"
        )
    
    def has_credentials(self) -> bool:
        """Check if connection is configured."""
        return bool(self.host and self.db and self.user)


class SyncSettings(BaseSettings):
    """Synchronization settings."""

    model_config = SettingsConfigDict(
        env_nested_delimiter=None,  # Use flat names
        case_sensitive=False,
        extra="ignore",
    )

    batch_size: int = Field(default=1000, description="Records per batch")
    mode: Literal["full", "incremental"] = Field(
        default="incremental", description="Sync mode"
    )
    schedule_interval_minutes: int = Field(
        default=15, description="Schedule interval in minutes"
    )
    
    # READ-ONLY MODE - Critical security setting
    # When True: Platform ONLY reads from Odoo, never writes
    # When False: Raises error unless ALLOW_UNSAFE_ODOO_WRITES is set
    read_only_mode: bool = Field(
        default=True,
        description="STRICT READ-ONLY MODE: Platform never modifies Odoo data"
    )


class LoggingSettings(BaseSettings):
    """Logging settings."""

    model_config = SettingsConfigDict(
        env_nested_delimiter=None,  # Use flat names
        case_sensitive=False,
        extra="ignore",
    )

    level: str = Field(default="INFO", description="Log level")
    file: str = Field(default="sync.log", description="Log file path")


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Uses flat environment variable names for simplicity:
    - ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_API_KEY, ODOO_PASSWORD
    - POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    - SYNC_BATCH_SIZE, SYNC_MODE, SCHEDULE_INTERVAL_MINUTES
    - READ_ONLY_MODE
    - LOG_LEVEL, LOG_FILE
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter=None,  # Use flat names
        case_sensitive=False,
        extra="ignore",
    )

    # Flat Odoo settings
    odoo_url: str = Field(default="http://localhost:8069", description="Odoo server URL")
    odoo_db: str = Field(default="odoo_db", description="Odoo database name")
    odoo_username: str = Field(default="admin", description="Odoo username")
    odoo_api_key: Optional[str] = Field(default=None, description="Odoo API key")
    odoo_password: Optional[str] = Field(default=None, description="Odoo password (deprecated)")
    odoo_api_version: int = Field(default=17, description="Odoo API version")

    # Flat PostgreSQL settings
    postgres_host: str = Field(default="localhost", description="PostgreSQL host")
    postgres_port: int = Field(default=5432, description="PostgreSQL port")
    postgres_db: str = Field(default="sync_db", description="PostgreSQL database name")
    postgres_user: str = Field(default="sync_user", description="PostgreSQL user")
    postgres_password: str = Field(default="", description="PostgreSQL password")

    # Flat Sync settings
    sync_batch_size: int = Field(default=1000, description="Records per batch")
    sync_mode: Literal["full", "incremental"] = Field(
        default="incremental", description="Sync mode"
    )
    schedule_interval_minutes: int = Field(
        default=15, description="Schedule interval in minutes"
    )
    read_only_mode: bool = Field(
        default=True,
        description="STRICT READ-ONLY MODE: Platform never modifies Odoo data"
    )

    # Flat Logging settings
    log_level: str = Field(default="INFO", description="Log level")
    log_file: str = Field(default="sync.log", description="Log file path")

    @property
    def odoo(self) -> OdooSettings:
        """Get Odoo settings as OdooSettings object."""
        return OdooSettings(
            url=self.odoo_url,
            db=self.odoo_db,
            username=self.odoo_username,
            api_key=self.odoo_api_key,
            password=self.odoo_password,
            api_version=self.odoo_api_version,
        )

    @property
    def postgres(self) -> PostgresSettings:
        """Get PostgreSQL settings as PostgresSettings object."""
        return PostgresSettings(
            host=self.postgres_host,
            port=self.postgres_port,
            db=self.postgres_db,
            user=self.postgres_user,
            password=self.postgres_password,
        )

    @property
    def sync(self) -> SyncSettings:
        """Get sync settings as SyncSettings object."""
        return SyncSettings(
            batch_size=self.sync_batch_size,
            mode=self.sync_mode,
            schedule_interval_minutes=self.schedule_interval_minutes,
            read_only_mode=self.read_only_mode,
        )

    @property
    def logging(self) -> LoggingSettings:
        """Get logging settings as LoggingSettings object."""
        return LoggingSettings(
            level=self.log_level,
            file=self.log_file,
        )


@lru_cache
def get_settings() -> Settings:
    """
    Get application settings singleton.

    Returns:
        Settings: Application settings instance.
    """
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
        return Settings(_env_file=None)
    return Settings()


def validate_read_only_mode() -> None:
    """
    Validate that READ_ONLY_MODE is enforced.
    
    This function should be called at application startup to ensure
    the platform operates in strict read-only mode.
    
    Raises:
        RuntimeError: If READ_ONLY_MODE is disabled without explicit override.
    """
    settings = get_settings()
    
    if not settings.sync.read_only_mode:
        # Check for explicit override
        allow_unsafe = os.environ.get("ALLOW_UNSAFE_ODOO_WRITES", "").lower()
        
        if allow_unsafe != "true":
            raise RuntimeError(
                "CRITICAL: READ_ONLY_MODE is disabled! "
                "The Odoo sync platform is designed to operate in READ-ONLY mode. "
                "Setting READ_ONLY_MODE=false is STRONGLY DISCOURAGED. "
                "Odoo should NEVER be modified by this platform. "
                "Data flows: Odoo → PostgreSQL only. "
                "If you MUST disable this (for development only), set ALLOW_UNSAFE_ODOO_WRITES=true "
                "and understand the security implications."
            )
        
        # If explicitly allowed, log critical warning
        import structlog
        logger = structlog.get_logger("security")
        logger.critical(
            "READ_ONLY_MODE DISABLED - SECURITY RISK",
            warning="Odoo write operations are enabled!",
            danger="This should ONLY be used in development environments.",
            advise="Set READ_ONLY_MODE=true and remove ALLOW_UNSAFE_ODOO_WRITES for production.",
        )
