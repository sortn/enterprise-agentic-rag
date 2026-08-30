"""Transactional document parsing, chunking, embedding and indexing."""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from config import Settings, get_settings
from db.parent_store_manager import ParentStoreManager
from retrieval.milvus_store import ChunkRecord, MilvusStore
from services.model_clients import SiliconFlowEmbeddings
from .chunker import HeadingAwareChunker
from .models import DocumentUnit, ParsedDocument
from .parsers import MultiFormatParser


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionResult:
    doc_id: str
    source: str
    chunks: int
    status: str


class IngestionPipeline:
    def __init__(
        self,
        store: MilvusStore,
        embeddings: SiliconFlowEmbeddings,
        settings: Settings | None = None,
        parent_store: ParentStoreManager | None = None,
    ):
        self.settings = settings or get_settings()
        self.store = store
        self.embeddings = embeddings
        self.parent_store = parent_store or ParentStoreManager(self.settings)
        self.parser = MultiFormatParser(self.settings)
        self.chunker = HeadingAwareChunker(self.settings)
        self._lock = threading.Lock()

    def ingest(self, path: str | Path, replace: bool = False) -> IngestionResult:
        with self._lock:
            document = self.parser.parse(path)
            existing_documents = self.store.list_documents()
            existing_ids = {item["doc_id"] for item in existing_documents}
            parents, drafts = self.chunker.split_parent_child(document)
            if document.doc_id in existing_ids and not replace:
                if not self.parent_store.has_document(document.doc_id):
                    self.parent_store.save_document(document.doc_id, parents)
                return IngestionResult(document.doc_id, document.source, 0, "skipped")

            if not drafts:
                raise ValueError(f"{document.source} 未生成有效文本块")
            vectors = self.embeddings.embed_documents([draft.text for draft in drafts])
            records = [
                ChunkRecord(
                    id=draft.id,
                    doc_id=draft.doc_id,
                    parent_id=draft.parent_id,
                    source=draft.source,
                    heading=draft.heading,
                    locator=draft.locator,
                    text=draft.text,
                    dense=vector,
                )
                for draft, vector in zip(drafts, vectors, strict=True)
            ]

            # A changed file keeps its source name but receives a new content
            # hash. Remove older versions only after parsing/embedding succeeds.
            stale_ids = {
                item["doc_id"]
                for item in existing_documents
                if item["source"] == document.source
            }
            if replace and document.doc_id in existing_ids:
                stale_ids.add(document.doc_id)
            for stale_id in stale_ids:
                self.store.delete_document(stale_id)
                if stale_id != document.doc_id:
                    self.parent_store.delete_document(stale_id)
                    (self.settings.parsed_dir / f"{stale_id}.json").unlink(missing_ok=True)
            self.store.insert(records)
            self.parent_store.save_document(document.doc_id, parents)
            parsed_path = self.settings.parsed_dir / f"{document.doc_id}.json"
            parsed_path.write_text(
                json.dumps(document.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return IngestionResult(document.doc_id, document.source, len(records), "indexed")

    def backfill_parent_store(self, document_ids: set[str] | None = None) -> int:
        """Rebuild missing parent files from parser snapshots created by older versions."""
        rebuilt = 0
        for path in sorted(self.settings.parsed_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                doc_id = str(payload.get("doc_id", ""))
                if document_ids is not None and doc_id not in document_ids:
                    continue
                if self.parent_store.has_document(doc_id):
                    continue
                document = ParsedDocument(
                    doc_id=doc_id,
                    source=str(payload["source"]),
                    file_type=str(payload["file_type"]),
                    units=[DocumentUnit(**unit) for unit in payload.get("units", [])],
                )
                parents, _ = self.chunker.split_parent_child(document)
                if parents:
                    self.parent_store.save_document(doc_id, parents)
                    rebuilt += 1
            except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
                logger.warning("Skipping invalid parser snapshot %s: %s", path, exc)
        return rebuilt
