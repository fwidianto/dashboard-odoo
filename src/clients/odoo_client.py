"""Odoo XML-RPC/JSON-RPC client for data synchronization with retry logic."""

import time
from datetime import datetime
from typing import Any, Optional

import requests
import xmlrpc.client as xmlrpc_lib
from urllib.parse import urljoin
from functools import wraps

from src.utils.logging import get_logger
from src.utils.settings import get_settings


def with_retry(max_retries: int = 3, delay_seconds: int = 5, backoff: float = 2.0):
    """
    Decorator to add retry logic to Odoo client methods.
    
    Args:
        max_retries: Maximum number of retry attempts.
        delay_seconds: Initial delay between retries.
        backoff: Backoff multiplier for exponential delay.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay_seconds
            
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (xmlrpc_lib.Fault, requests.RequestException) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger = get_logger("odoo_client")
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries} failed: {e}. "
                            f"Retrying in {current_delay}s...",
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger = get_logger("odoo_client")
                        logger.error(
                            f"All {max_retries} attempts failed for {func.__name__}",
                            error=str(e),
                        )
            
            raise last_exception
        return wrapper
    return decorator


class OdooClientError(Exception):
    """Custom exception for Odoo client errors."""

    pass


class OdooClient:
    """
    Client for interacting with Odoo via XML-RPC API.

    Supports authentication, model introspection, and data reading with retry logic.
    """

    def __init__(
        self,
        url: Optional[str] = None,
        db: Optional[str] = None,
        username: Optional[str] = None,
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
            password: Password (defaults to settings).
            max_retries: Maximum retry attempts for API failures.
            retry_delay: Delay between retry attempts in seconds.
        """
        settings = get_settings()
        
        self.url = url or settings.odoo.url
        self.db = db or settings.odoo.db
        self.username = username or settings.odoo.username
        self.password = password or settings.odoo.password
        self.api_version = settings.odoo.api_version
        
        # Retry configuration
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # XML-RPC endpoints
        self.common_endpoint = urljoin(self.url, "/xmlrpc/2/common")
        self.object_endpoint = urljoin(self.url, "/xmlrpc/2/object")

        self._uid: Optional[int] = None
        self._logger = get_logger("odoo_client")

    @property
    def uid(self) -> int:
        """Get authenticated user ID, authenticating if necessary."""
        if self._uid is None:
            self.authenticate()
        return self._uid

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
            except (xmlrpc_lib.Fault, requests.RequestException) as e:
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
        """Authenticate with Odoo and get user ID."""
        self._logger.info("Authenticating with Odoo", url=self.url, db=self.db)

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
                raise OdooClientError("Authentication failed")

            self._uid = uid
            self._logger.info("Authentication successful", uid=uid)
            return uid

        except Exception as e:
            self._logger.error("XML-RPC authentication failed", error=str(e))
            raise OdooClientError(f"Authentication failed: {e}")

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
                self.password,
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
        """
        Get IDs of records deleted since a given date.
        
        Note: This requires the 'ir.model.attachment' model or audit logging
        to track deletions. Without such tracking, this returns an empty list.
        
        Args:
            model: Model technical name.
            since_date: Datetime to check deletions from.
            
        Returns:
            List of deleted record IDs.
        """
        # Odoo doesn't natively track deletions in a queryable way
        # This would require audit logging or unlink logging
        # For now, return empty list - implement based on specific Odoo setup
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
            return True
        except Exception as e:
            self._logger.error("Odoo connection test failed", error=str(e))
            return False

    def close(self):
        """Clean up client resources."""
        self._uid = None
        self._logger.debug("Odoo client closed")