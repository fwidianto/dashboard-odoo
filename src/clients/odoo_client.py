"""Odoo XML-RPC/JSON-RPC client for data synchronization with strict read-only mode.

This client enforces a strict allowlist of Odoo API methods to ensure
the platform never writes to Odoo. All data flows only from Odoo to PostgreSQL.

READ-ONLY MODE: This client will ONLY execute read operations against Odoo.
Write operations (create, write, unlink, etc.) are explicitly blocked.

Compatible with:
- Odoo 17
- Odoo 18
- Odoo Online (SaaS)
"""

import time
from datetime import datetime
from typing import Any, Optional
import xmlrpc.client as xmlrpc_lib
from urllib.parse import urljoin

from src.utils.logging import get_logger
from src.utils.settings import get_settings


# =============================================================================
# ALLOWED METHODS (Read-Only Operations Only)
# =============================================================================
ALLOWED_METHODS = frozenset([
    "search",          # Search for record IDs
    "read",            # Read specific records by ID
    "search_read",     # Combined search and read
    "search_count",    # Count matching records
    "fields_get",      # Get field definitions
])

# Methods that are FORBIDDEN (would modify Odoo data)
FORBIDDEN_METHODS = frozenset([
    "create",          # Create new records
    "write",           # Update existing records
    "unlink",          # Delete records
    "copy",            # Copy records
    "name_create",     # Create with name
    "default_get",     # Get default values
    "create_multi",    # Batch create
    "write_multi",     # Batch update
    "unlink_multi",    # Batch delete
    "action_archive",  # Archive records
    "action_unarchive",# Unarchive records
    "toggle_active",   # Toggle active state
])


class ReadOnlyViolation(Exception):
    """Exception raised when a forbidden method is attempted against Odoo."""

    def __init__(self, method: str, model: str, message: Optional[str] = None):
        self.method = method
        self.model = model
        self.full_message = message or (
            f"SECURITY VIOLATION: Forbidden method '{method}' attempted on model '{model}'. "
            f"The Odoo sync platform operates in READ-ONLY mode and cannot modify Odoo data."
        )
        super().__init__(self.full_message)


class OdooAuthenticationError(Exception):
    """Custom exception for Odoo authentication errors."""
    pass


class OdooClientError(Exception):
    """Custom exception for Odoo client errors."""
    pass


class OdooClient:
    """
    Read-only client for interacting with Odoo via XML-RPC API.
    
    SECURITY FEATURES:
    - Strict method allowlist: Only read operations are permitted
    - All write operations are blocked and logged
    - API Key authentication (password auth deprecated)
    
    Compatible with Odoo 17, Odoo 18, and Odoo Online (SaaS).
    """

    def __init__(
        self,
        url: Optional[str] = None,
        db: Optional[str] = None,
        username: Optional[str] = None,
        api_key: Optional[str] = None,
        password: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: int = 5,
        read_only_mode: Optional[bool] = None,
    ):
        """
        Initialize the Odoo client in read-only mode.

        Args:
            url: Odoo server URL (defaults to settings).
            db: Database name (defaults to settings).
            username: Username (defaults to settings).
            api_key: API key for authentication (preferred).
            password: Password for authentication (deprecated, fallback).
            max_retries: Maximum retry attempts for API failures (default: 3).
            retry_delay: Delay between retry attempts in seconds (default: 5).
            read_only_mode: Override read-only mode (defaults to settings).
        """
        settings = get_settings()
        
        self.url = url or settings.odoo.url
        self.db = db or settings.odoo.db
        self.username = username or settings.odoo.username
        
        # Authentication credentials
        if api_key:
            self.api_key = api_key
            self.password = None
            self._auth_method = "api_key"
        elif password:
            self.api_key = None
            self.password = password
            self._auth_method = "password"
        else:
            self.api_key = settings.odoo.api_key
            self.password = settings.odoo.password
            self._auth_method = settings.odoo.auth_method
        
        # Retry configuration
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # Read-only mode configuration
        self._read_only_mode = read_only_mode if read_only_mode is not None else settings.sync.read_only_mode
        
        # XML-RPC endpoints
        # /xmlrpc/2/common - Authentication (has authenticate() method)
        # /xmlrpc/2/object - Model operations (has execute_kw() method)
        self.common_endpoint = urljoin(self.url.rstrip('/'), "/xmlrpc/2/common")
        self.object_endpoint = urljoin(self.url.rstrip('/'), "/xmlrpc/2/object")

        self._uid: Optional[int] = None
        self._logger = get_logger("odoo_client")
        
        self._logger.info(
            "Odoo client initialized in READ-ONLY mode",
            url=self.url,
            db=self.db,
            auth_method=self._auth_method,
            read_only_mode=self._read_only_mode,
        )

    @property
    def uid(self) -> int:
        """Get authenticated user ID, authenticating if necessary."""
        if self._uid is None:
            self.authenticate()
        return self._uid

    @property
    def auth_method(self) -> str:
        """Return the current authentication method."""
        return self._auth_method
    
    @property
    def read_only_mode(self) -> bool:
        """Return whether read-only mode is enabled."""
        return self._read_only_mode

    def _validate_method(self, method: str, model: str) -> None:
        """
        Validate that the method is allowed in read-only mode.
        """
        if method not in ALLOWED_METHODS:
            self._logger.error(
                "BLOCKED: Forbidden method attempted",
                security_violation=True,
                method=method,
                model=model,
                user=self.username,
                db=self.db,
            )
            raise ReadOnlyViolation(method, model)

    def authenticate(self) -> int:
        """
        Authenticate with Odoo server.
        
        Returns:
            Authenticated user ID.
        """
        self._logger.info(
            "Authenticating with Odoo",
            url=self.url,
            db=self.db,
            auth_method=self._auth_method,
        )

        if self._auth_method == "api_key":
            return self._authenticate_with_api_key()
        else:
            return self._authenticate_with_password()

    def _authenticate_with_api_key(self) -> int:
        """
        Authenticate using API key via the common endpoint.
        
        Uses: common.authenticate(db, login, api_key)
        
        Returns:
            Authenticated user ID.
        """
        self._logger.info("Authenticating with API key", url=self.url, db=self.db)

        def _do_auth():
            # IMPORTANT: Use common.authenticate() not execute_kw!
            common = xmlrpc_lib.ServerProxy(self.common_endpoint)
            return common.authenticate(
                self.db,
                self.username,
                self.api_key,
            )

        try:
            result = self._with_retry(_do_auth)

            if not result:
                raise OdooAuthenticationError(
                    f"API key authentication failed for user '{self.username}'. "
                    f"Please verify the API key is valid and associated with this user."
                )

            self._uid = result if isinstance(result, int) else result.get('uid', result)
            
            self._logger.info(
                "API key authentication successful",
                uid=self._uid,
                user=self.username,
                db=self.db,
            )
            return self._uid

        except xmlrpc_lib.Fault as e:
            self._logger.error("XML-RPC API key authentication failed", error=str(e))
            raise OdooAuthenticationError(f"API key authentication failed: {e}")
        except Exception as e:
            self._logger.error("API key authentication failed", error=str(e))
            raise OdooAuthenticationError(f"Authentication failed: {e}")

    def _authenticate_with_password(self) -> int:
        """
        Authenticate using password via the common endpoint (DEPRECATED).
        
        Uses: common.authenticate(db, login, password)
        
        Returns:
            Authenticated user ID.
        """
        self._logger.warning(
            "Authenticating with password (DEPRECATED - use API key)",
            url=self.url,
            db=self.db,
        )

        def _do_auth():
            # IMPORTANT: Use common.authenticate() not execute_kw!
            common = xmlrpc_lib.ServerProxy(self.common_endpoint)
            return common.authenticate(
                self.db,
                self.username,
                self.password,
            )

        try:
            result = self._with_retry(_do_auth)

            if not result:
                raise OdooAuthenticationError(
                    f"Password authentication failed for user '{self.username}'."
                )

            self._uid = result if isinstance(result, int) else result.get('uid', result)
            
            self._logger.warning(
                "Password authentication successful (DEPRECATED)",
                uid=self._uid,
                user=self.username,
                db=self.db,
            )
            return self._uid

        except xmlrpc_lib.Fault as e:
            self._logger.error("XML-RPC password authentication failed", error=str(e))
            raise OdooAuthenticationError(f"Password authentication failed: {e}")
        except Exception as e:
            self._logger.error("Password authentication failed", error=str(e))
            raise OdooAuthenticationError(f"Authentication failed: {e}")

    def _with_retry(self, func):
        """
        Execute a function with retry logic.
        
        Args:
            func: Function to execute.
            
        Returns:
            Result of the function call.
        """
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                return func()
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    self._logger.warning(
                        f"Attempt {attempt + 1}/{self.max_retries} failed: {e}. Retrying..."
                    )
                    time.sleep(self.retry_delay)
        
        self._logger.error(
            f"All {self.max_retries} attempts failed",
            error=str(last_exception),
        )
        raise last_exception

    def execute(self, model: str, method: str, args: list, kwargs: Optional[dict] = None) -> Any:
        """
        Execute a READ-ONLY method on an Odoo model using execute_kw.
        
        IMPORTANT: execute_kw must be called on the OBJECT endpoint, not common!
        
        Correct pattern:
            models.execute_kw(db, uid, password_or_api_key, model, method, args, kwargs)
        
        Args:
            model: Model technical name (e.g., 'res.partner').
            method: Method name to execute (MUST be in allowlist).
            args: Positional arguments.
            kwargs: Keyword arguments.

        Returns:
            Result of the method call.

        Raises:
            ReadOnlyViolation: If method is not in the allowed methods list.
            OdooClientError: If the call fails.
        """
        if kwargs is None:
            kwargs = {}

        # CRITICAL: Validate method is allowed in read-only mode
        self._validate_method(method, model)

        self._logger.debug(
            "Executing READ-ONLY Odoo method via execute_kw",
            model=model,
            method=method,
            user=self.username,
            db=self.db,
            endpoint=self.object_endpoint,
        )

        def _do_execute():
            # IMPORTANT: Use object endpoint with execute_kw!
            models = xmlrpc_lib.ServerProxy(self.object_endpoint)
            return models.execute_kw(
                self.db,
                self.uid,
                self._get_auth_param(),
                model,
                method,
                args,
                kwargs,
            )

        try:
            result = self._with_retry(_do_execute)

            # Audit log successful execution
            record_count = self._get_record_count(result)
            self._logger.info(
                "Odoo READ operation completed",
                model=model,
                method=method,
                records_returned=record_count,
            )

            return result
        except xmlrpc_lib.Fault as e:
            self._logger.error(
                "Odoo method execution failed",
                model=model,
                method=method,
                error=str(e),
            )
            raise OdooClientError(f"Execute failed for {model}.{method}: {e}")
        except Exception as e:
            self._logger.error(
                "Odoo method execution failed",
                model=model,
                method=method,
                error=str(e),
            )
            raise OdooClientError(f"Execute failed for {model}.{method}: {e}")

    def _get_auth_param(self) -> str:
        """Get the authentication parameter based on auth method."""
        if self._auth_method == "api_key":
            return self.api_key
        return self.password

    def _get_record_count(self, result: Any) -> int:
        """Get record count from execute_kw result."""
        if isinstance(result, list):
            return len(result)
        return 0

    def search(
        self,
        model: str,
        domain: list,
        offset: int = 0,
        limit: Optional[int] = None,
        order: Optional[str] = None,
    ) -> list[int]:
        """
        Search for record IDs (READ-ONLY operation).
        
        Uses: execute_kw(model, 'search', [domain], kwargs)

        Args:
            model: Model technical name.
            domain: Odoo domain filter.
            offset: Record offset.
            limit: Maximum records to return.
            order: Sort order.

        Returns:
            List of record IDs.
        """
        kwargs: dict[str, Any] = {}
        if offset:
            kwargs["offset"] = offset
        if limit:
            kwargs["limit"] = limit
        if order:
            kwargs["order"] = order

        return self.execute(model, "search", [domain], kwargs)

    def read(
        self,
        model: str,
        ids: list[int],
        fields: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        Read specific records by ID (READ-ONLY operation).
        
        Uses: execute_kw(model, 'read', [ids], kwargs)

        Args:
            model: Model technical name.
            ids: List of record IDs.
            fields: Fields to read.

        Returns:
            List of record dictionaries.
        """
        kwargs: dict[str, Any] = {}
        if fields:
            kwargs["fields"] = fields

        return self.execute(model, "read", [ids], kwargs)

    def search_read(
        self,
        model: str,
        domain: list,
        fields: Optional[list[str]] = None,
        offset: int = 0,
        limit: Optional[int] = None,
        order: Optional[str] = None,
    ) -> list[dict]:
        """
        Search and read records from a model (READ-ONLY operation).
        
        Uses: execute_kw(model, 'search_read', [], kwargs)

        Args:
            model: Model technical name.
            domain: Odoo domain filter.
            fields: Fields to read (None for all).
            offset: Record offset.
            limit: Maximum records to return.
            order: Sort order.

        Returns:
            List of record dictionaries.
        """
        kwargs: dict[str, Any] = {"domain": domain}

        if fields:
            kwargs["fields"] = fields
        if offset:
            kwargs["offset"] = offset
        if limit:
            kwargs["limit"] = limit
        if order:
            kwargs["order"] = order

        return self.execute(model, "search_read", [], kwargs)

    def count(self, model: str, domain: list) -> int:
        """
        Count records matching a domain (READ-ONLY operation).
        
        Uses: execute_kw(model, 'search_count', [domain])

        Args:
            model: Model technical name.
            domain: Odoo domain filter.

        Returns:
            Count of matching records.
        """
        return self.execute(model, "search_count", [domain])

    def get_model_fields(self, model: str) -> dict[str, dict]:
        """
        Get field definitions for a model (READ-ONLY operation).
        
        Uses: execute_kw(model, 'fields_get', [], kwargs)

        Args:
            model: Model technical name.

        Returns:
            Dictionary of field definitions.
        """
        self._logger.debug("Getting model fields (READ-ONLY)", model=model)
        return self.execute(model, "fields_get", [], {})

    def get_model_info(self, model: str) -> dict:
        """
        Get model information (READ-ONLY operation).
        
        Uses: execute_kw('ir.model', 'read', [[id]], kwargs)

        Args:
            model: Model technical name.

        Returns:
            Model information dictionary.
        """
        return self.execute("ir.model", "read", [[model]], {"fields": ["id", "name", "model"]})

    def read_batched(
        self,
        model: str,
        domain: list,
        fields: Optional[list[str]] = None,
        batch_size: int = 1000,
        order: Optional[str] = "id",
    ) -> list[dict]:
        """
        Read records in batches for efficient large dataset handling (READ-ONLY).

        Args:
            model: Model technical name.
            domain: Odoo domain filter.
            fields: Fields to read.
            batch_size: Records per batch.
            order: Sort order for consistent pagination.

        Yields:
            Batches of record dictionaries.
        """
        total = self.count(model, domain)
        self._logger.info(
            "Starting READ-ONLY batched read",
            model=model,
            total_records=total,
            batch_size=batch_size,
        )

        offset = 0
        while offset < total:
            records = self.search_read(
                model,
                domain,
                fields=fields,
                offset=offset,
                limit=batch_size,
                order=order,
            )

            if not records:
                break

            yield records
            offset += len(records)

            self._logger.debug(
                "READ-ONLY batch read progress",
                model=model,
                offset=offset,
                total=total,
            )

    def read_since(
        self,
        model: str,
        since_date: datetime,
        fields: Optional[list[str]] = None,
        batch_size: int = 1000,
    ) -> list[dict]:
        """
        Read records modified since a given date (READ-ONLY).

        Args:
            model: Model technical name.
            since_date: Datetime to filter modifications.
            fields: Fields to read.
            batch_size: Records per batch.

        Yields:
            Batches of modified records.
        """
        date_str = since_date.strftime("%Y-%m-%d %H:%M:%S")
        domain = [("write_date", ">=", date_str)]

        self._logger.info(
            "READ-ONLY reading records since",
            model=model,
            since_date=since_date,
        )

        yield from self.read_batched(
            model=model,
            domain=domain,
            fields=fields,
            batch_size=batch_size,
            order="write_date,id",
        )

    def test_connection(self) -> bool:
        """
        Test connection to Odoo server.
        
        Also validates authentication.

        Returns:
            True if connection and authentication successful.
        """
        try:
            # Test server connectivity
            common = xmlrpc_lib.ServerProxy(self.common_endpoint)
            version = common.version()
            self._logger.info(
                "Odoo server version",
                version=version,
                url=self.url,
            )
            
            # Test authentication
            try:
                self.authenticate()
                self._logger.info(
                    "Connection and authentication successful",
                    auth_method=self._auth_method,
                    read_only_mode=self._read_only_mode,
                    user=self.username,
                    db=self.db,
                )
            except Exception as auth_error:
                self._logger.warning(
                    "Authentication test failed",
                    error=str(auth_error),
                    auth_method=self._auth_method,
                )
                return False
            
            return True
        except Exception as e:
            self._logger.error("Odoo connection test failed", error=str(e))
            return False

    def close(self):
        """Clean up client resources."""
        self._uid = None
        self._logger.debug("Odoo client closed")


# =============================================================================
# METHOD CONSTANTS FOR EXTERNAL USE
# =============================================================================
__all__ = [
    "ALLOWED_METHODS",
    "FORBIDDEN_METHODS",
    "ReadOnlyViolation",
    "OdooAuthenticationError",
    "OdooClientError",
    "OdooClient",
]
