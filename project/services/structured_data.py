"""Allow-listed structured database queries over deterministic mock data."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Literal

from config import Settings, get_settings


PRODUCTS = [
    ("NX-MEET-S", "星云会议终端标准版", 3999.0, 2),
    ("NX-MEET-PRO", "星云会议终端专业版", 6999.0, 3),
    ("NX-CAM-4K", "星云 4K 智能摄像头", 1299.0, 2),
]

DEPARTMENTS = [
    ("HR", "人力资源部", "周老师", "400-800-1001"),
    ("FIN", "财务部", "李老师", "400-800-1002"),
    ("IT", "信息技术部", "陈工", "400-800-1003"),
]


class StructuredDataService:
    """Uses parameterized SQL only; arbitrary model-generated SQL is rejected."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.path = Path(self.settings.structured_db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS products (
                    sku TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    list_price REAL NOT NULL,
                    warranty_years INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS departments (
                    code TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    contact TEXT NOT NULL,
                    hotline TEXT NOT NULL
                );
                """
            )
            connection.executemany(
                "INSERT OR IGNORE INTO products VALUES (?, ?, ?, ?)",
                PRODUCTS,
            )
            connection.executemany(
                "INSERT OR IGNORE INTO departments VALUES (?, ?, ?, ?)",
                DEPARTMENTS,
            )

    def query(
        self,
        query_type: Literal["product", "department"],
        identifier: str,
    ) -> dict[str, Any]:
        identifier = identifier.strip().upper()
        statements = {
            "product": (
                "SELECT sku, name, list_price, warranty_years FROM products WHERE sku = ?",
                "sku",
            ),
            "department": (
                "SELECT code, name, contact, hotline FROM departments WHERE code = ?",
                "code",
            ),
        }
        sql, _ = statements[query_type]
        with self._connect() as connection:
            row = connection.execute(sql, (identifier,)).fetchone()
        if row is None:
            return {"found": False, "query_type": query_type, "identifier": identifier}
        return {"found": True, "query_type": query_type, **dict(row)}
