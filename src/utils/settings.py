"""Application settings using Pydantic settings management."""

from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OdooSettings(BaseSettings):
    """Odoo connection settings."""

    url: str = Field(default="http://localhost:8069", description="Odoo server URL")
    db: str = Field(default="odoo_db", description="Odoo database name")
    username: str = Field(default="admin", description="Odoo username")
    password: str = Field(default="admin", description="Odoo password")
    api_version: int = Field(default=17, description="Odoo API version")


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