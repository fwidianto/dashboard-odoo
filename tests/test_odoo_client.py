"""Unit tests for Odoo client."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime

from src.clients.odoo_client import OdooClient, OdooClientError


class TestOdooClient:
    """Tests for OdooClient."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings for Odoo client."""
        settings = MagicMock()
        settings.odoo.url = "http://localhost:8069"
        settings.odoo.db = "test_db"
        settings.odoo.username = "admin"
        settings.odoo.password = "admin"
        settings.odoo.api_version = 17
        return settings

    def test_client_initialization(self, mock_settings):
        """Test Odoo client initializes with correct endpoints."""
        with patch('src.clients.odoo_client.get_settings', return_value=mock_settings):
            client = OdooClient()
            
            assert client.url == "http://localhost:8069"
            assert client.db == "test_db"
            assert client.username == "admin"
            assert "xmlrpc/2/common" in client.common_endpoint
            assert "xmlrpc/2/object" in client.object_endpoint

    def test_client_custom_parameters(self, mock_settings):
        """Test Odoo client with custom parameters."""
        with patch('src.clients.odoo_client.get_settings', return_value=mock_settings):
            client = OdooClient(
                url="http://custom:8069",
                db="custom_db",
                username="custom",
                password="custom_pass",
            )
            
            assert client.url == "http://custom:8069"
            assert client.db == "custom_db"
            assert client.username == "custom"

    def test_authenticate_success(self, mock_settings):
        """Test successful authentication."""
        with patch('src.clients.odoo_client.get_settings', return_value=mock_settings):
            client = OdooClient()
            
            with patch('xmlrpc.client.ServerProxy') as mock_proxy:
                mock_server = MagicMock()
                mock_server.execute_kw.return_value = (True, 1, [])
                mock_proxy.return_value = mock_server
                
                uid = client.authenticate()
                
                assert uid == 1
                assert client._uid == 1

    def test_authenticate_failure(self, mock_settings):
        """Test authentication failure."""
        with patch('src.clients.odoo_client.get_settings', return_value=mock_settings):
            client = OdooClient()
            
            with patch('xmlrpc.client.ServerProxy') as mock_proxy:
                mock_server = MagicMock()
                mock_server.execute_kw.return_value = (False, None, [])
                mock_proxy.return_value = mock_server
                
                with pytest.raises(OdooClientError):
                    client.authenticate()

    def test_execute_method(self, mock_settings):
        """Test executing a method on a model."""
        with patch('src.clients.odoo_client.get_settings', return_value=mock_settings):
            client = OdooClient()
            client._uid = 1  # Skip authentication
            
            with patch('xmlrpc.client.ServerProxy') as mock_proxy:
                mock_server = MagicMock()
                mock_server.execute_kw.return_value = [{"id": 1, "name": "Test"}]
                mock_proxy.return_value = mock_server
                
                result = client.execute("res.partner", "read", [[1]])
                
                assert len(result) == 1
                assert result[0]["name"] == "Test"

    def test_search_read(self, mock_settings):
        """Test search_read method."""
        with patch('src.clients.odoo_client.get_settings', return_value=mock_settings):
            client = OdooClient()
            client._uid = 1
            
            with patch.object(client, 'execute') as mock_execute:
                mock_execute.return_value = [
                    {"id": 1, "name": "Partner 1"},
                    {"id": 2, "name": "Partner 2"},
                ]
                
                result = client.search_read(
                    "res.partner",
                    [["active", "=", True]],
                    fields=["id", "name"],
                    limit=10,
                )
                
                assert len(result) == 2
                mock_execute.assert_called_once()

    def test_count(self, mock_settings):
        """Test count method."""
        with patch('src.clients.odoo_client.get_settings', return_value=mock_settings):
            client = OdooClient()
            client._uid = 1
            
            with patch.object(client, 'execute') as mock_execute:
                mock_execute.return_value = 42
                
                result = client.count("res.partner", [])
                
                assert result == 42

    def test_read_batched(self, mock_settings):
        """Test batched reading."""
        with patch('src.clients.odoo_client.get_settings', return_value=mock_settings):
            client = OdooClient()
            client._uid = 1
            
            # Mock search_read to return batches
            with patch.object(client, 'search_read') as mock_search_read:
                mock_search_read.side_effect = [
                    [{"id": 1}, {"id": 2}],
                    [{"id": 3}, {"id": 4}],
                    [],
                ]
                with patch.object(client, 'count', return_value=4):
                    batches = list(client.read_batched(
                        "res.partner",
                        [],
                        batch_size=2,
                    ))
                    
                    assert len(batches) == 2
                    assert len(batches[0]) == 2

    def test_test_connection_success(self, mock_settings):
        """Test connection test success."""
        with patch('src.clients.odoo_client.get_settings', return_value=mock_settings):
            client = OdooClient()
            
            with patch('xmlrpc.client.ServerProxy') as mock_proxy:
                mock_server = MagicMock()
                mock_server.version.return_value = {"server_version": "17.0"}
                mock_proxy.return_value = mock_server
                
                result = client.test_connection()
                
                assert result is True

    def test_test_connection_failure(self, mock_settings):
        """Test connection test failure."""
        with patch('src.clients.odoo_client.get_settings', return_value=mock_settings):
            client = OdooClient()
            
            with patch('xmlrpc.client.ServerProxy') as mock_proxy:
                mock_server = MagicMock()
                mock_server.version.side_effect = Exception("Connection refused")
                mock_proxy.return_value = mock_server
                
                result = client.test_connection()
                
                assert result is False

    def test_close(self, mock_settings):
        """Test client close method."""
        with patch('src.clients.odoo_client.get_settings', return_value=mock_settings):
            client = OdooClient()
            client._uid = 1
            
            client.close()
            
            assert client._uid is None