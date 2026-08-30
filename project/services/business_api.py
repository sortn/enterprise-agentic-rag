"""Mock business API adapter used to demonstrate tool calls without private data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from config import Settings, get_settings


DEFAULT_BUSINESS_DATA = {
    "inventory": {
        "NX-MEET-S": {"available": 42, "warehouse": "华东仓", "updated_at": "demo"},
        "NX-MEET-PRO": {"available": 18, "warehouse": "华南仓", "updated_at": "demo"},
        "NX-CAM-4K": {"available": 67, "warehouse": "华东仓", "updated_at": "demo"},
    },
    "service_status": {
        "meeting-cloud": {"status": "operational", "updated_at": "demo"},
        "device-console": {"status": "operational", "updated_at": "demo"},
    },
}


class MockBusinessService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.path = Path(self.settings.business_data_path)
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(DEFAULT_BUSINESS_DATA, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def lookup(
        self,
        resource: Literal["inventory", "service_status"],
        identifier: str,
    ) -> dict[str, Any]:
        if not self.path.exists():
            raise RuntimeError(f"模拟业务数据不存在：{self.path}")
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        normalized = identifier.strip().upper() if resource == "inventory" else identifier.strip().lower()
        result = payload.get(resource, {}).get(normalized)
        if result is None:
            return {"found": False, "resource": resource, "identifier": normalized}
        return {"found": True, "resource": resource, "identifier": normalized, **result}
