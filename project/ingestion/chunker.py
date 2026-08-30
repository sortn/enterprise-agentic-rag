"""Heading-aware semantic grouping followed by overlapping child windows."""

from __future__ import annotations

import hashlib

from config import Settings, get_settings
from .models import ChunkDraft, ParentChunk, ParsedDocument


class HeadingAwareChunker:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def split(self, document: ParsedDocument) -> list[ChunkDraft]:
        """Return retrieval children for callers that use the legacy API."""
        _, children = self.split_parent_child(document)
        return children

    def split_parent_child(
        self,
        document: ParsedDocument,
    ) -> tuple[list[ParentChunk], list[ChunkDraft]]:
        """Create complete parent passages and overlapping retrieval children."""
        parents: list[ParentChunk] = []
        chunks: list[ChunkDraft] = []
        parent_number = 0
        for unit in document.units:
            for parent_text in self._windows(unit.text, self.settings.parent_chunk_size, 0):
                parent_id = f"{document.doc_id}-p{parent_number}"
                parent_number += 1
                parents.append(
                    ParentChunk(
                        parent_id=parent_id,
                        doc_id=document.doc_id,
                        source=document.source,
                        heading=unit.heading[:1000],
                        locator=unit.locator[:250],
                        text=parent_text,
                    )
                )
                for child_number, child_text in enumerate(
                    self._windows(
                        parent_text,
                        self.settings.child_chunk_size,
                        self.settings.child_chunk_overlap,
                    )
                ):
                    raw_id = f"{parent_id}:{child_number}:{child_text}".encode("utf-8")
                    chunk_id = hashlib.sha1(raw_id).hexdigest()[:32]
                    chunks.append(
                        ChunkDraft(
                            id=chunk_id,
                            doc_id=document.doc_id,
                            parent_id=parent_id,
                            source=document.source,
                            heading=unit.heading[:1000],
                            locator=unit.locator[:250],
                            text=child_text,
                        )
                    )
        return parents, chunks

    @staticmethod
    def _windows(text: str, size: int, overlap: int) -> list[str]:
        if len(text) <= size:
            return [text.strip()] if text.strip() else []
        result: list[str] = []
        start = 0
        while start < len(text):
            hard_end = min(start + size, len(text))
            end = hard_end
            if hard_end < len(text):
                boundary = max(
                    text.rfind("\n", start + size // 2, hard_end),
                    text.rfind("。", start + size // 2, hard_end),
                    text.rfind("；", start + size // 2, hard_end),
                )
                if boundary > start:
                    end = boundary + 1
            value = text[start:end].strip()
            if value:
                result.append(value)
            if end >= len(text):
                break
            next_start = end - overlap
            start = next_start if next_start > start else end
        return result
