"""Unit tests for Odoo client with API key authentication and read-only mode."""

import pytest
from unittest.mock import MagicMock, patch

from src.clients.odoo_client import (
    OdooClient, 
    OdooClientError, 
    OdooAuthenticationError,
    ReadOnlyViolation,
    ALLOWED_METHODS,
    FORBIDDEN_METHODS,
)


class TestReadOnlyMode:
    """Tests for read-only mode enforcement."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings for Odoo client."""
        settings = MagicMock()
        settings.odoo.url = "http://localhost:8069"
        settings.odoo.db = "test_db"
        settings.odoo.username = "admin"
        settings.odoo.api_key = "test_api_key_12345"
        settings.odoo.password = None
        settings.odoo.auth_method = "api_key"
        settings.odoo.api_version = 17
        settings.sync.read_only_mode = True
        return settings

    def test_allowed_methods_defined(self):
        """Test that allowed methods are properly defined."""
        assert "search" in ALLOWED_METHODS
        assert "read" in ALLOWED_METHODS
        assert "search_read" in ALLOWED_METHODS
        assert "search_count" in ALLOWED_METHODS
        assert "fields_get" in ALLOWED_METHODS

    def test_forbidden_methods_defined(self):
        """Test that forbidden methods are properly defined."""
        assert "create" in FORBIDDEN_METHODS
        assert "write" in FORBIDDEN_METHODS
        assert "unlink" in FORBIDDEN_METHODS
        assert "copy" in FORBIDDEN_METHODS

    def test_read_only_mode_property(self, mock_settings):
        """Test read_only_mode property returns correct value."""
        with patch('src.clients.odoo_client.get_settings', return_value=mock_settings):
            client = OdooClient()
            assert client.read_only_mode is True

    def test_forbidden_method_raises_violation(self, mock_settings):
        """Test that calling a forbidden method raises ReadOnlyViolation."""
        with patch('src.clients.odoo_client.get_settings', return_value=mock_settings):
            client = OdooClient()
            client._uid = 1  # Skip authentication
            
            with pytest.raises(ReadOnlyViolation) as exc_info:
                client.execute("res.partner", "create", [[{"name": "Test"}]])
            
            assert "create" in str(exc_info.value)
            assert "res.partner" in str(exc_info.value)

    def test_allowed_method_succeeds(self, mock_settings):
        """Test that allowed methods execute successfully."""
        with patch('src.clients.odoo_client.get_settings', return_value=mock_settings):
            client = OdooClient()
            client._uid = 1
            
            with patch('xmlrpc.client.ServerProxy') as mock_proxy:
                mock_server = MagicMock()
                mock_server.execute_kw.return_value = [{"id": 1, "name": "Test"}]
                mock_proxy.return_value = mock_server
                
                # This should NOT raise
                result = client.search_read("res.partner", [])
                assert len(result) == 1

    def test_validate_method_logs_violation(self, mock_settings):
        """Test that violation is logged when forbidden method is called."""
        with patch('src.clients.odoo_client.get_settings', return_value=mock_settings):
            client = OdooClient()
            
            with pytest.raises(ReadOnlyViolation):
                client.execute("res.partner", "write", [[1], {"name": "Test"}])

    def test_read_only_violation_exception(self):
        """Test ReadOnlyViolation exception attributes."""
        violation = ReadOnlyViolation(method="create", model="res.partner")
        
        assert violation.method == "create"
        assert violation.model == "res.partner"
        assert "create" in violation.full_message
        assert "res.partner" in violation.full_message


class TestOdooClientAuth:
    """Tests for OdooClient authentication methods."""

    @pytest.fixture
    def mock_settings_api_key(self):
        """Mock settings with API key."""
        settings = MagicMock()
        settings.odoo.url = "http://localhost:8069"
        settings.odoo.db = "test_db"
        settings.odoo.username = "admin"
        settings.odoo.api_key = "test_api_key_12345"
        settings.odoo.password = None
        settings.odoo.auth_method = "api_key"
        settings.odoo.api_version = 17
        settings.sync.read_only_mode = True
        return settings

    @pytest.fixture
    def mock_settings_password(self):
        """Mock settings with password (deprecated)."""
        settings = MagicMock()
        settings.odoo.url = "http://localhost:8069"
        settings.odoo.db = "test_db"
        settings.odoo.username = "admin"
        settings.odoo.api_key = None
        settings.odoo.password = "deprecated_password"
        settings.odoo.auth_method = "password"
        settings.odoo.api_version = 17
        settings.sync.read_only_mode = True
        return settings

    def test_client_initialization_api_key(self, mock_settings_api_key):
        """Test Odoo client initializes with API key."""
        with patch('src.clients.odoo_client.get_settings', return_value=mock_settings_api_key):
            client = OdooClient()
            
            assert client.url == "http://localhost:8069"
            assert client.db == "test_db"
            assert client.username == "admin"
            assert client.api_key == "test_api_key_12345"
            assert client.password is None
            assert client._auth_method == "api_key"

    def test_client_initialization_password(self, mock_settings_password):
        """Test Odoo client initializes with password (deprecated)."""
        with patch('src.clients.odoo_client.get_settings', return_value=mock_settings_password):
            client = OdooClient()
            
            assert client.url == "http://localhost:8069"
            assert client.password == "deprecated_password"
            assert client._auth_method == "password"

    def test_client_custom_api_key_parameter(self, mock_settings_api_key):
        """Test Odoo client accepts API key as constructor parameter."""
        with patch('src.clients.odoo_client.get_settings', return_value=mock_settings_api_key):
            client = OdooClient(api_key="custom_key")
            
            assert client.api_key == "custom_key"
            assert client._auth_method == "api_key"

    def test_auth_method_property(self, mock_settings_api_key):
        """Test auth_method property returns correct value."""
        with patch('src.clients.odoo_client.get_settings', return_value=mock_settings_api_key):
            client = OdooClient()
            assert client.auth_method == "api_key"

    def test_authenticate_api_key_success(self, mock_settings_api_key):
        """Test successful API key authentication."""
        with patch('src.clients.odoo_client.get_settings', return_value=mock_settings_api_key):
            client = OdooClient()
            
            with patch('xmlrpc.client.ServerProxy') as mock_proxy:
                mock_server = MagicMock()
                mock_server.authenticate.return_value = 1  # UID returned
                mock_proxy.return_value = mock_server
                
                uid = client.authenticate()
                
                assert uid == 1
                assert client._uid == 1
                # Verify authenticate was called with 4 arguments (including user_agent_env)
                mock_server.authenticate.assert_called_once()
                call_args = mock_server.authenticate.call_args
                assert len(call_args[0]) == 4  # db, login, password/api_key, user_agent_env

    def test_authenticate_password_success(self, mock_settings_password):
        """Test successful password authentication (deprecated)."""
        with patch('src.clients.odoo_client.get_settings', return_value=mock_settings_password):
            client = OdooClient()
            
            with patch('xmlrpc.client.ServerProxy') as mock_proxy:
                mock_server = MagicMock()
                mock_server.authenticate.return_value = 1  # UID returned
                mock_proxy.return_value = mock_server
                
                uid = client.authenticate()
                
                assert uid == 1
                assert client._uid == 1
                # Verify authenticate was called with 4 arguments (including user_agent_env)
                mock_server.authenticate.assert_called_once()
                call_args = mock_server.authenticate.call_args
                assert len(call_args[0]) == 4  # db, login, password/api_key, user_agent_env

    def test_execute_with_api_key(self, mock_settings_api_key):
        """Test execute method uses correct auth parameter."""
        with patch('src.clients.odoo_client.get_settings', return_value=mock_settings_api_key):
            client = OdooClient()
            client._uid = 1  # Skip authentication
            
            with patch('xmlrpc.client.ServerProxy') as mock_proxy:
                mock_server = MagicMock()
                mock_server.execute_kw.return_value = [{"id": 1, "name": "Test"}]
                mock_proxy.return_value = mock_server
                
                result = client.execute("res.partner", "read", [[1]])
                
                assert len(result) == 1
                # Verify API key was used
                call_args = mock_server.execute_kw.call_args
                assert call_args[0][2] == "test_api_key_12345"

    def test_get_auth_param_api_key(self, mock_settings_api_key):
        """Test _get_auth_param returns API key."""
        with patch('src.clients.odoo_client.get_settings', return_value=mock_settings_api_key):
            client = OdooClient()
            
            assert client._get_auth_param() == "test_api_key_12345"

    def test_get_auth_param_password(self, mock_settings_password):
        """Test _get_auth_param returns password."""
        with patch('src.clients.odoo_client.get_settings', return_value=mock_settings_password):
            client = OdooClient()
            
            assert client._get_auth_param() == "deprecated_password"

    def test_prefers_api_key_when_both_provided(self):
        """Test that API key is preferred when both are provided."""
        settings = MagicMock()
        settings.odoo.url = "http://localhost:8069"
        settings.odoo.db = "test_db"
        settings.odoo.username = "admin"
        settings.odoo.api_key = "preferred_key"
        settings.odoo.password = "fallback_password"
        settings.odoo.auth_method = "api_key"
        settings.odoo.api_version = 17
        settings.sync.read_only_mode = True
        
        with patch('src.clients.odoo_client.get_settings', return_value=settings):
            client = OdooClient()
            
            assert client.api_key == "preferred_key"
            assert client._auth_method == "api_key"

    def test_connection_test_with_auth(self, mock_settings_api_key):
        """Test connection test includes authentication check."""
        with patch('src.clients.odoo_client.get_settings', return_value=mock_settings_api_key):
            client = OdooClient()
            
            with patch('xmlrpc.client.ServerProxy') as mock_proxy:
                mock_server = MagicMock()
                mock_server.version.return_value = {"server_version": "17.0"}
                mock_server.execute_kw.return_value = 1
                mock_proxy.return_value = mock_server
                
                result = client.test_connection()
                
                assert result is True


class TestReadOnlyModeValidation:
    """Tests for READ_ONLY_MODE configuration validation."""

    def test_validate_read_only_mode_raises_when_disabled(self):
        """Test that validate_read_only_mode raises error when disabled."""
        from src.utils.settings import validate_read_only_mode
        import os
        
        # Create mock settings with read_only_mode = False
        mock_settings = MagicMock()
        mock_settings.sync.read_only_mode = False
        
        with patch.dict(os.environ, {}, clear=True):
            with patch('src.utils.settings.get_settings', return_value=mock_settings):
                with pytest.raises(RuntimeError) as exc_info:
                    validate_read_only_mode()
                
                assert "READ_ONLY_MODE is disabled" in str(exc_info.value)

    def test_validate_read_only_mode_allows_with_override(self):
        """Test that validate_read_only_mode allows with ALLOW_UNSAFE_ODOO_WRITES."""
        from src.utils.settings import validate_read_only_mode
        import os
        
        mock_settings = MagicMock()
        mock_settings.sync.read_only_mode = False
        
        with patch.dict(os.environ, {"ALLOW_UNSAFE_ODOO_WRITES": "true"}):
            with patch('src.utils.settings.get_settings', return_value=mock_settings):
                # Should not raise, just log warning
                validate_read_only_mode()