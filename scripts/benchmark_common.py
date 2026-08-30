"""Shared paths and component construction for benchmark_v1 scripts."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "project"
BENCHMARK_DIR = ROOT / "evaluation" / "benchmark_v1"
RUNTIME_DIR = BENCHMARK_DIR / "runtime"
RESULTS_DIR = BENCHMARK_DIR / "results"
COLLECTION_NAME = "enterprise_benchmark_v1"

if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from config import Settings  # noqa: E402
from ingestion.pipeline import IngestionPipeline  # noqa: E402
from retrieval.hybrid_retriever import HybridRetriever  # noqa: E402
from retrieval.milvus_store import MilvusStore  # noqa: E402
from services.model_clients import SiliconFlowEmbeddings, SiliconFlowReranker  # noqa: E402


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def build_settings() -> Settings:
    settings = Settings(
        milvus_collection=COLLECTION_NAME,
        data_dir=RUNTIME_DIR,
        upload_dir=RUNTIME_DIR / "uploads",
        parsed_dir=RUNTIME_DIR / "parsed",
        parent_store_dir=RUNTIME_DIR / "parents",
        evaluation_dir=RESULTS_DIR,
        structured_db_path=RUNTIME_DIR / "enterprise.db",
        business_data_path=ROOT / "data" / "business_api.json",
        dense_top_k=24,
        sparse_top_k=24,
        fusion_top_k=24,
        rerank_top_k=5,
    )
    settings.ensure_directories()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    return settings


def build_retrieval_stack():
    settings = build_settings()
    embeddings = SiliconFlowEmbeddings(settings)
    reranker = SiliconFlowReranker(settings)
    store = MilvusStore(settings)
    store.ensure_collection()
    ingestion = IngestionPipeline(store, embeddings, settings)
    retriever = HybridRetriever(store, embeddings, reranker, settings)
    return settings, store, ingestion, retriever
