"""Test fixtures for Odoo-PostgreSQL sync tests."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime

from src.models.config import ModelConfig, FieldConfig, SyncConfig


@pytest.fixture
def sample_field_configs():
    """Sample field configurations for testing."""
    return [
        FieldConfig(
            odoo_field="id",
            postgres_column="id",
            postgres_type="INTEGER",
            primary_key=True,
            nullable=False,
        ),
        FieldConfig(
            odoo_field="name",
            postgres_column="name",
            postgres_type="VARCHAR(255)",
            nullable=True,
        ),
        FieldConfig(
            odoo_field="email",
            postgres_column="email",
            postgres_type="VARCHAR(255)",
            nullable=True,
        ),
        FieldConfig(
            odoo_field="write_date",
            postgres_column="write_date",
            postgres_type="TIMESTAMP",
            nullable=True,
            is_sync_date=True,
        ),
    ]


@pytest.fixture
def sample_model_config(sample_field_configs):
    """Sample model configuration for testing."""
    return ModelConfig(
        odoo_model="res.partner",
        postgres_table="res_partner",
        description="Test partner model",
        fields=sample_field_configs,
    )


@pytest.fixture
def sample_sync_config(sample_model_config):
    """Sample sync configuration for testing."""
    return SyncConfig(
        models=[sample_model_config],
    )


@pytest.fixture
def mock_odoo_client():
    """Mock Odoo client for testing."""
    client = MagicMock()
    client.uid = 1
    client.test_connection.return_value = True
    client.authenticate.return_value = 1
    client.count.return_value = 100
    client.search_read.return_value = [
        {"id": 1, "name": "Partner 1", "email": "p1@example.com", "write_date": "2024-01-01T00:00:00"},
        {"id": 2, "name": "Partner 2", "email": "p2@example.com", "write_date": "2024-01-02T00:00:00"},
    ]
    client.read_batched.return_value = iter([
        [{"id": 1, "name": "Partner 1", "email": "p1@example.com", "write_date": "2024-01-01T00:00:00"}],
        [{"id": 2, "name": "Partner 2", "email": "p2@example.com", "write_date": "2024-01-02T00:00:00"}],
    ])
    client.get_model_fields.return_value = {
        "id": {"type": "integer"},
        "name": {"type": "char"},
        "email": {"type": "char"},
        "write_date": {"type": "datetime"},
    }
    return client


@pytest.fixture
def mock_postgres_client():
    """Mock PostgreSQL client for testing."""
    client = MagicMock()
    client.test_connection.return_value = True
    client.get_sync_state.return_value = None
    client.table_exists.return_value = True
    return client


@pytest.fixture
def sample_odoo_records():
    """Sample Odoo records for testing."""
    return [
        {"id": 1, "name": "Partner 1", "email": "p1@example.com", "write_date": "2024-01-01T10:00:00"},
        {"id": 2, "name": "Partner 2", "email": "p2@example.com", "write_date": "2024-01-02T10:00:00"},
        {"id": 3, "name": "Partner 3", "email": "p3@example.com", "write_date": "2024-01-03T10:00:00"},
    ]


@pytest.fixture
def sample_transformed_records():
    """Sample transformed records for PostgreSQL."""
    return [
        {"id": 1, "name": "Partner 1", "email": "p1@example.com", "write_date": datetime(2024, 1, 1, 10, 0, 0)},
        {"id": 2, "name": "Partner 2", "email": "p2@example.com", "write_date": datetime(2024, 1, 2, 10, 0, 0)},
        {"id": 3, "name": "Partner 3", "email": "p3@example.com", "write_date": datetime(2024, 1, 3, 10, 0, 0)},
    ]