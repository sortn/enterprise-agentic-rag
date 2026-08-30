"""Compare Dense, Hybrid, and Hybrid+Reranker retrieval on one dataset."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "project"
sys.path.insert(0, str(PROJECT))

from core.rag_system import RAGSystem  # noqa: E402


MODES = ("dense", "hybrid", "hybrid_rerank")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=ROOT / "evaluation" / "retrieval_qa.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evaluation" / "results")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--ingest-samples", action="store_true")
    return parser.parse_args()


def reciprocal_rank(hits, item: dict) -> float:
    marker = item.get("relevant_metadata_contains", "")
    for rank, hit in enumerate(hits, start=1):
        metadata = f"{hit.heading} {hit.locator}"
        if hit.source == item["relevant_source"] and (not marker or marker in metadata):
            return 1.0 / rank
    return 0.0


def main() -> None:
    args = parse_args()
    if args.k < 1:
        raise ValueError("--k must be at least 1")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    system = RAGSystem().initialize()

    if args.ingest_samples:
        generated = ROOT / "sample_data" / "generated"
        for path in sorted(generated.glob("*")):
            if path.is_file():
                result = system.ingestion.ingest(path)
                print(f"{result.source}: {result.status}, {result.chunks} chunks")

    rows = []
    for number, item in enumerate(dataset, start=1):
        embedding_started = time.perf_counter()
        try:
            shared_vector = system.retriever.embeddings.embed_query(item["question"])
            embedding_error = ""
        except Exception as exc:
            shared_vector = None
            embedding_error = f"{type(exc).__name__}: {exc}"
        embedding_latency_ms = (time.perf_counter() - embedding_started) * 1000
        for mode in MODES:
            started = time.perf_counter()
            run_error = embedding_error
            hits = []
            if not run_error:
                try:
                    hits = system.retriever.retrieve(
                        item["question"],
                        mode=mode,
                        top_k=args.k,
                        query_vector=shared_vector,
                    )
                except Exception as exc:
                    run_error = f"{type(exc).__name__}: {exc}"
            retrieval_latency_ms = (time.perf_counter() - started) * 1000
            latency_ms = embedding_latency_ms + retrieval_latency_ms
            top_hits = hits[: args.k]
            sources = [hit.source for hit in top_hits]
            rr = reciprocal_rank(top_hits, item)
            rows.append(
                {
                    "mode": mode,
                    "question_id": item["id"],
                    "question": item["question"],
                    "relevant_source": item["relevant_source"],
                    "relevant_metadata_contains": item.get("relevant_metadata_contains", ""),
                    f"recall@{args.k}": int(rr > 0),
                    "reciprocal_rank": round(rr, 6),
                    "latency_ms": round(latency_ms, 2),
                    "embedding_latency_ms": round(embedding_latency_ms, 2),
                    "retrieval_latency_ms": round(retrieval_latency_ms, 2),
                    "retrieved_sources": json.dumps(sources, ensure_ascii=False),
                    "top_chunk_ids": json.dumps([hit.id for hit in hits[: args.k]], ensure_ascii=False),
                    "retrieved_metadata": json.dumps(
                        [f"{hit.heading} | {hit.locator}" for hit in top_hits], ensure_ascii=False
                    ),
                    "run_error": run_error,
                }
            )
        print(f"[{number}/{len(dataset)}] {item['id']}")

    csv_path = args.output_dir / "retrieval_details.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = {}
    for mode in MODES:
        mode_rows = [row for row in rows if row["mode"] == mode]
        summary[mode] = {
            "questions": len(mode_rows),
            "errors": sum(bool(row["run_error"]) for row in mode_rows),
            f"recall@{args.k}": round(statistics.mean(row[f"recall@{args.k}"] for row in mode_rows), 4),
            "mrr": round(statistics.mean(row["reciprocal_rank"] for row in mode_rows), 4),
            "mean_latency_ms": round(statistics.mean(row["latency_ms"] for row in mode_rows), 2),
            "p95_latency_ms": round(sorted(row["latency_ms"] for row in mode_rows)[max(0, int(len(mode_rows) * 0.95) - 1)], 2),
        }
    summary_path = args.output_dir / "retrieval_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Details: {csv_path}")
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()
