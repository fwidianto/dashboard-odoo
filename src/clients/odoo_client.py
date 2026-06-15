"""Odoo XML-RPC/JSON-RPC client for data synchronization with retry logic and API key auth."""

import time
import warnings
from datetime import datetime
from typing import Any, Optional
import xmlrpc.client as xmlrpc_lib
from urllib.parse import urljoin

from src.utils.logging import get_logger
from src.utils.settings import get_settings


class OdooAuthenticationError(Exception):
    """Custom exception for Odoo authentication errors."""
    pass


class OdooClientError(Exception):
    """Custom exception for Odoo client errors."""
    pass


class OdooClient:
    """
    Client for interacting with Odoo via XML-RPC API.

    Supports both API Key and password authentication:
    - API Key (preferred): More secure, no password exposure
    - Password (deprecated): Legacy authentication method
    
    API key authentication uses Odoo's /web/session/authenticate endpoint
    with the api_key parameter instead of password.
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
    ):
        """
        Initialize the Odoo client.

        Args:
            url: Odoo server URL (defaults to settings).
            db: Database name (defaults to settings).
            username: Username (defaults to settings).
            api_key: API key for authentication (preferred).
            password: Password for authentication (deprecated, fallback).
            max_retries: Maximum retry attempts for API failures.
            retry_delay: Delay between retry attempts in seconds.
        """
        settings = get_settings()
        
        self.url = url or settings.odoo.url
        self.db = db or settings.odoo.db
        self.username = username or settings.odoo.username
        self.api_version = settings.odoo.api_version
        
        # Authentication credentials
        # Prefer API key if provided, otherwise use password
        if api_key:
            self.api_key = api_key
            self.password = None
            self._auth_method = "api_key"
        elif password:
            self.api_key = None
            self.password = password
            self._auth_method = "password"
        else:
            # Fall back to settings
            self.api_key = settings.odoo.api_key
            self.password = settings.odoo.password
            self._auth_method = settings.odoo.auth_method
        
        # Retry configuration
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # XML-RPC endpoints
        self.common_endpoint = urljoin(self.url, "/xmlrpc/2/common")
        self.object_endpoint = urljoin(self.url, "/xmlrpc/2/object")

        self._uid: Optional[int] = None
        self._logger = get_logger("odoo_client")
        
        # Log authentication method at startup
        if self._auth_method == "password":
            warnings.warn(
                "Using password authentication to Odoo. This is deprecated. "
                "Please migrate to API key authentication. "
                "See: https://www.odoo.com/documentation/17.0/developer/reference/external_api.html",
                DeprecationWarning,
                stacklevel=2
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

    def _with_retry(self, func, *args, **kwargs):
        """
        Execute a function with retry logic.
        
        Args:
            func: Function to execute.
            *args: Positional arguments.
            **kwargs: Keyword arguments.
            
        Returns:
            Result of the function.
        """
        last_exception = None
        current_delay = self.retry_delay
        
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except (xmlrpc_lib.Fault, ConnectionError, TimeoutError) as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    self._logger.warning(
                        f"Attempt {attempt + 1}/{self.max_retries} failed: {e}. "
                        f"Retrying in {current_delay}s...",
                    )
                    time.sleep(current_delay)
                    current_delay *= 2  # Exponential backoff
                else:
                    self._logger.error(
                        f"All {self.max_retries} attempts failed",
                        error=str(e),
                    )
        
        raise last_exception

    def authenticate(self) -> int:
        """
        Authenticate with Odoo and get user ID.
        
        Uses API key authentication if available, falls back to password.
        
        Returns:
            Authenticated user ID.
            
        Raises:
            OdooAuthenticationError: If authentication fails.
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
        Authenticate using API key.
        
        Odoo's API key authentication uses the /web/session/authenticate endpoint
        with the api_key parameter instead of password.
        
        Returns:
            Authenticated user ID.
        """
        self._logger.info("Authenticating with API key", url=self.url, db=self.db)

        def _do_auth():
            return xmlrpc_lib.ServerProxy(self.common_endpoint).execute_kw(
                self.db,
                self.username,
                self.api_key,  # Use API key as password parameter
                "res.users",
                "authenticate",
                [self.db, self.username, self.api_key],
            )

        try:
            result = self._with_retry(_do_auth)
            
            # result can be: integer UID, or False on failure
            if isinstance(result, int):
                self._uid = result
            elif result:
                # Some versions return dict with uid
                self._uid = result.get('uid', result) if isinstance(result, dict) else result
            else:
                raise OdooAuthenticationError(
                    f"API key authentication failed for user '{self.username}'. "
                    f"Please verify the API key is valid and associated with this user."
                )

            self._logger.info("API key authentication successful", uid=self._uid)
            return self._uid

        except xmlrpc_lib.Fault as e:
            self._logger.error("XML-RPC API key authentication failed", error=str(e))
            raise OdooAuthenticationError(
                f"API key authentication failed: {e}. "
                f"Please verify the API key is valid."
            )
        except Exception as e:
            self._logger.error("API key authentication failed", error=str(e))
            raise OdooAuthenticationError(f"Authentication failed: {e}")

    def _authenticate_with_password(self) -> int:
        """
        Authenticate using password (deprecated).
        
        Returns:
            Authenticated user ID.
        """
        self._logger.info("Authenticating with password (deprecated)", url=self.url, db=self.db)

        def _do_auth():
            return xmlrpc_lib.ServerProxy(self.common_endpoint).execute_kw(
                self.db,
                self.username,
                self.password,
                "res.users",
                "authenticate",
                [self.db, self.username, self.password],
            )

        try:
            success, uid, _ = self._with_retry(_do_auth)

            if not success:
                raise OdooAuthenticationError(
                    f"Password authentication failed for user '{self.username}'."
                )

            self._uid = uid
            self._logger.info("Password authentication successful (deprecated)", uid=uid)
            return uid

        except xmlrpc_lib.Fault as e:
            self._logger.error("XML-RPC password authentication failed", error=str(e))
            raise OdooAuthenticationError(f"Password authentication failed: {e}")
        except Exception as e:
            self._logger.error("Password authentication failed", error=str(e))
            raise OdooAuthenticationError(f"Authentication failed: {e}")

    def execute(
        self,
        model: str,
        method: str,
        args: list,
        kwargs: Optional[dict] = None,
    ) -> Any:
        """Execute a method on an Odoo model with retry logic."""
        if kwargs is None:
            kwargs = {}

        self._logger.debug(
            "Executing Odoo method",
            model=model,
            method=method,
        )

        def _do_execute():
            return xmlrpc_lib.ServerProxy(self.object_endpoint).execute_kw(
                self.db,
                self.uid,
                self._get_auth_param(),  # Use appropriate auth param
                model,
                method,
                args,
                kwargs,
            )

        try:
            return self._with_retry(_do_execute)
        except xmlrpc_lib.Fault as e:
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

    def search_read(
        self,
        model: str,
        domain: list,
        fields: Optional[list[str]] = None,
        offset: int = 0,
        limit: Optional[int] = None,
        order: Optional[str] = None,
    ) -> list[dict]:
        """Search and read records from a model."""
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

    def search(
        self,
        model: str,
        domain: list,
        offset: int = 0,
        limit: Optional[int] = None,
        order: Optional[str] = None,
    ) -> list[int]:
        """Search for record IDs."""
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
        """Read specific records by ID."""
        kwargs: dict[str, Any] = {}
        if fields:
            kwargs["fields"] = fields

        return self.execute(model, "read", [ids], kwargs)

    def count(self, model: str, domain: list) -> int:
        """Count records matching a domain."""
        return self.execute(model, "search_count", [domain])

    def get_model_fields(self, model: str) -> dict[str, dict]:
        """Get field definitions for a model."""
        self._logger.debug("Getting model fields", model=model)
        return self.execute(model, "fields_get", [], {})

    def get_model_info(self, model: str) -> dict:
        """Get model information."""
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
        Read records in batches for efficient large dataset handling.

        Yields:
            Batches of record dictionaries.
        """
        total = self.count(model, domain)
        self._logger.info(
            "Starting batched read",
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
                "Batch read progress",
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
        """Read records modified since a given date."""
        date_str = since_date.strftime("%Y-%m-%d %H:%M:%S")
        domain = [("write_date", ">=", date_str)]

        self._logger.info(
            "Reading records since",
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

    def get_deleted_record_ids(
        self,
        model: str,
        since_date: datetime,
    ) -> list[int]:
        """Get IDs of records deleted since a given date."""
        self._logger.debug(
            "Checking for deleted records",
            model=model,
            since_date=since_date,
        )
        return []

    def test_connection(self) -> bool:
        """Test connection to Odoo server."""
        try:
            version = xmlrpc_lib.ServerProxy(self.common_endpoint).version()
            self._logger.info("Odoo server version", version=version)
            
            # Also test authentication
            try:
                self.authenticate()
                self._logger.info(
                    "Authentication test successful",
                    auth_method=self._auth_method,
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