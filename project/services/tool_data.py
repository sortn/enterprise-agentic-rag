"""Allow-listed PostgreSQL queries used by enterprise Agent tools."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Literal

import asyncpg
from sqlalchemy.engine import make_url

from config import Settings, get_settings


class EnterpriseToolDataService:
    """Reads tool data from PostgreSQL without accepting model-generated SQL."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        url = make_url(self.settings.database_url)
        if url.get_backend_name() != "postgresql":
            raise ValueError("Enterprise tools require PostgreSQL")
        self._connection_kwargs: dict[str, Any] = {
            "host": url.host or "127.0.0.1",
            "port": url.port or 5432,
            "user": url.username,
            "password": url.password,
            "database": url.database,
        }
        if self.settings.database_schema:
            self._connection_kwargs["server_settings"] = {
                "search_path": self.settings.database_schema
            }

    def query(
        self,
        query_type: Literal["product", "department"],
        identifier: str,
    ) -> dict[str, Any]:
        statements = {
            "product": (
                "SELECT sku, name, list_price, warranty_years FROM products WHERE sku = $1"
            ),
            "department": (
                "SELECT code, name, contact, hotline FROM departments WHERE code = $1"
            ),
        }
        normalized = identifier.strip().upper()
        row = self._run_fetchrow(statements[query_type], normalized)
        if row is None:
            return {"found": False, "query_type": query_type, "identifier": normalized}
        return {"found": True, "query_type": query_type, **self._serialize_row(row)}

    def lookup(
        self,
        resource: Literal["inventory", "service_status"],
        identifier: str,
    ) -> dict[str, Any]:
        statements = {
            "inventory": (
                "SELECT sku AS identifier, available, reserved, warehouse, updated_at "
                "FROM product_inventory WHERE sku = $1"
            ),
            "service_status": (
                "SELECT service_name AS identifier, status, latency_ms, updated_at "
                "FROM service_statuses WHERE service_name = $1"
            ),
        }
        normalized = (
            identifier.strip().upper()
            if resource == "inventory"
            else identifier.strip().lower()
        )
        row = self._run_fetchrow(statements[resource], normalized)
        if row is None:
            return {"found": False, "resource": resource, "identifier": normalized}
        return {"found": True, "resource": resource, **self._serialize_row(row)}

    def _run_fetchrow(self, statement: str, identifier: str):
        return asyncio.run(self._fetchrow(statement, identifier))

    async def _fetchrow(self, statement: str, identifier: str):
        connection = await asyncpg.connect(**self._connection_kwargs)
        try:
            return await connection.fetchrow(statement, identifier)
        finally:
            await connection.close()

    @staticmethod
    def _serialize_row(row) -> dict[str, Any]:
        result = dict(row)
        for key, value in result.items():
            if isinstance(value, datetime):
                result[key] = value.isoformat()
        return result
