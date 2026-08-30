from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class DocumentUnit:
    text: str
    heading: str = ""
    locator: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedDocument:
    doc_id: str
    source: str
    file_type: str
    units: list[DocumentUnit]

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "source": self.source,
            "file_type": self.file_type,
            "units": [asdict(unit) for unit in self.units],
        }


@dataclass
class ChunkDraft:
    id: str
    doc_id: str
    parent_id: str
    source: str
    heading: str
    locator: str
    text: str


@dataclass
class ParentChunk:
    parent_id: str
    doc_id: str
    source: str
    heading: str
    locator: str
    text: str
