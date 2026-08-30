"""Index benchmark_v1 into its isolated Milvus collection."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import time

from benchmark_common import (
    BENCHMARK_DIR,
    COLLECTION_NAME,
    RESULTS_DIR,
    build_retrieval_stack,
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="drop and recreate only the benchmark collection")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings, store, ingestion, _ = build_retrieval_stack()
    if args.reset:
        store.clear()

    documents = json.loads((BENCHMARK_DIR / "corpus_manifest.json").read_text(encoding="utf-8"))[
        "documents"
    ]
    results = []
    started = time.perf_counter()
    for number, document in enumerate(documents, start=1):
        item_started = time.perf_counter()
        try:
            result = ingestion.ingest(BENCHMARK_DIR / "corpus" / document["source"])
            row = {
                **result.__dict__,
                "elapsed_seconds": round(time.perf_counter() - item_started, 3),
                "error": "",
            }
        except Exception as exc:
            row = {
                "doc_id": "",
                "source": document["source"],
                "chunks": 0,
                "status": "failed",
                "elapsed_seconds": round(time.perf_counter() - item_started, 3),
                "error": f"{type(exc).__name__}: {exc}",
            }
        results.append(row)
        print(
            f"[{number}/{len(documents)}] {row['source']}: {row['status']} / "
            f"{row['chunks']} chunks / {row['elapsed_seconds']}s",
            flush=True,
        )

    failures = [row for row in results if row["status"] == "failed"]
    indexed_documents = store.list_documents()
    report = {
        "collection": COLLECTION_NAME,
        "created_at": datetime.now().astimezone().isoformat(),
        "models": {
            "embedding": settings.embedding_model,
            "reranker": settings.rerank_model,
        },
        "chunking": {
            "parent_chunk_size": settings.parent_chunk_size,
            "child_chunk_size": settings.child_chunk_size,
            "child_chunk_overlap": settings.child_chunk_overlap,
        },
        "requested_documents": len(documents),
        "indexed_documents": len(indexed_documents),
        "indexed_chunks_this_run": sum(row["chunks"] for row in results),
        "failures": len(failures),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "results": results,
    }
    (RESULTS_DIR / "index_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in report.items() if key != "results"}, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(f"{len(failures)} documents failed to index")


if __name__ == "__main__":
    main()
