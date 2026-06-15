"""Application settings using Pydantic settings management."""

import os
from functools import lru_cache
from typing import Literal, Optional
import warnings

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class OdooSettings(BaseSettings):
    """Odoo connection settings."""

    url: str = Field(default="http://localhost:8069", description="Odoo server URL")
    db: str = Field(default="odoo_db", description="Odoo database name")
    username: str = Field(default="admin", description="Odoo username")
    
    # API Key authentication (preferred)
    api_key: Optional[str] = Field(default=None, description="Odoo API key for authentication")
    
    # Password authentication (deprecated, fallback only)
    password: Optional[str] = Field(default=None, description="Odoo password (deprecated, use API key)")
    
    api_version: int = Field(default=17, description="Odoo API version")

    @model_validator(mode='after')
    def validate_auth_method(self):
        """Validate authentication method and warn about password usage."""
        if self.api_key and self.password:
            # Both provided - prefer API key
            warnings.warn(
                "Both API_KEY and PASSWORD provided. Using API_KEY authentication. "
                "Consider removing PASSWORD for security.",
                DeprecationWarning,
                stacklevel=2
            )
        elif not self.api_key and not self.password:
            raise ValueError(
                "Either ODOO_API_KEY or ODOO_PASSWORD must be provided. "
                "API key is recommended for better security."
            )
        elif self.password:
            warnings.warn(
                "Using password authentication. This is deprecated and less secure. "
                "Please migrate to API key authentication using ODOO_API_KEY. "
                "See: https://www.odoo.com/documentation/17.0/developer/reference/external_api.html",
                DeprecationWarning,
                stacklevel=2
            )
        return self
    
    @property
    def auth_method(self) -> Literal["api_key", "password"]:
        """Return the authentication method being used."""
        if self.api_key:
            return "api_key"
        return "password"


class PostgresSettings(BaseSettings):
    """PostgreSQL connection settings."""

    host: str = Field(default="localhost", description="PostgreSQL host")
    port: int = Field(default=5432, description="PostgreSQL port")
    db: str = Field(default="sync_db", description="PostgreSQL database name")
    user: str = Field(default="sync_user", description="PostgreSQL user")
    password: str = Field(default="", description="PostgreSQL password")

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


class SyncSettings(BaseSettings):
    """Synchronization settings."""

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

    level: str = Field(default="INFO", description="Log level")
    file: str = Field(default="sync.log", description="Log file path")


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
    )

    odoo: OdooSettings = Field(default_factory=OdooSettings)
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    sync: SyncSettings = Field(default_factory=SyncSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)


@lru_cache
def get_settings() -> Settings:
    """
    Get application settings singleton.

    Returns:
        Settings: Application settings instance.
    """
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