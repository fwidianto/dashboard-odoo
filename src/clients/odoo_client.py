"""Odoo XML-RPC/JSON-RPC client for data synchronization."""

import time
from datetime import datetime
from typing import Any, Optional

import requests
import xmlrpc.client as xmlrpc_lib
from urllib.parse import urljoin

from src.utils.logging import get_logger
from src.utils.settings import get_settings


class OdooClientError(Exception):
    """Custom exception for Odoo client errors."""

    pass


class OdooClient:
    """
    Client for interacting with Odoo via XML-RPC API.

    Supports authentication, model introspection, and data reading.
    """

    def __init__(
        self,
        url: Optional[str] = None,
        db: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """
        Initialize the Odoo client.

        Args:
            url: Odoo server URL (defaults to settings).
            db: Database name (defaults to settings).
            username: Username (defaults to settings).
            password: Password (defaults to settings).
        """
        settings = get_settings()
        
        self.url = url or settings.odoo.url
        self.db = db or settings.odoo.db
        self.username = username or settings.odoo.username
        self.password = password or settings.odoo.password
        self.api_version = settings.odoo.api_version

        # XML-RPC endpoints
        self.common_endpoint = urljoin(self.url, "/xmlrpc/2/common")
        self.object_endpoint = urljoin(self.url, "/xmlrpc/2/object")

        self._uid: Optional[int] = None
        self._logger = get_logger("odoo_client")

    @property
    def uid(self) -> int:
        """
        Get authenticated user ID, authenticating if necessary.

        Returns:
            int: Authenticated user ID.
        """
        if self._uid is None:
            self.authenticate()
        return self._uid

    def authenticate(self) -> int:
        """
        Authenticate with Odoo and get user ID.

        Returns:
            int: Authenticated user ID.

        Raises:
            OdooClientError: If authentication fails.
        """
        self._logger.info("Authenticating with Odoo", url=self.url, db=self.db)

        try:
            # Try XML-RPC authentication
            success, uid, _ = xmlrpc_lib.ServerProxy(self.common_endpoint).execute_kw(
                self.db,  # database
                self.username,  # login
                self.password,  # password
                "res.users",  # model
                "authenticate",  # method
                [self.db, self.username, self.password],  # args
            )

            if not success:
                raise OdooClientError("Authentication failed")

            self._uid = uid
            self._logger.info("Authentication successful", uid=uid)
            return uid

        except xmlrpc_lib.Fault as e:
            self._logger.error("XML-RPC authentication failed", error=str(e))
            raise OdooClientError(f"Authentication failed: {e}")

    def execute(
        self,
        model: str,
        method: str,
        args: list,
        kwargs: Optional[dict] = None,
    ) -> Any:
        """
        Execute a method on an Odoo model.

        Args:
            model: Model technical name (e.g., 'res.partner').
            method: Method name to execute.
            args: Positional arguments.
            kwargs: Keyword arguments.

        Returns:
            Result of the method call.

        Raises:
            OdooClientError: If the call fails.
        """
        if kwargs is None:
            kwargs = {}

        self._logger.debug(
            "Executing Odoo method",
            model=model,
            method=method,
        )

        try:
            result = xmlrpc_lib.ServerProxy(self.object_endpoint).execute_kw(
                self.db,
                self.uid,
                self.password,
                model,
                method,
                args,
                kwargs,
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
        Search and read records from a model.

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
        kwargs: dict[str, Any] = {
            "domain": domain,
        }

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
        """
        Search for record IDs.

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
        Read specific records by ID.

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

    def count(self, model: str, domain: list) -> int:
        """
        Count records matching a domain.

        Args:
            model: Model technical name.
            domain: Odoo domain filter.

        Returns:
            Count of matching records.
        """
        return self.execute(model, "search_count", [domain])

    def get_model_fields(self, model: str) -> dict[str, dict]:
        """
        Get field definitions for a model.

        Args:
            model: Model technical name.

        Returns:
            Dictionary of field definitions.
        """
        self._logger.debug("Getting model fields", model=model)
        return self.execute(model, "fields_get", [], {})

    def get_model_info(self, model: str) -> dict:
        """
        Get model information.

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
        Read records in batches for efficient large dataset handling.

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
        """
        Read records modified since a given date.

        Args:
            model: Model technical name.
            since_date: Datetime to filter modifications.
            fields: Fields to read.
            batch_size: Records per batch.

        Yields:
            Batches of modified records.
        """
        # Format date for Odoo
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

    def test_connection(self) -> bool:
        """
        Test connection to Odoo server.

        Returns:
            bool: True if connection successful.
        """
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