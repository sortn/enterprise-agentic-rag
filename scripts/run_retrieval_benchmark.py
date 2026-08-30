"""Run Dense, Hybrid, and Hybrid+Reranker on a linked benchmark split."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
import json
import math
from pathlib import Path
import random
import statistics
import time

import numpy as np

from benchmark_common import BENCHMARK_DIR, RESULTS_DIR, build_retrieval_stack, read_jsonl


MODES = ("dense", "hybrid", "hybrid_rerank")
METRICS = ("hit_rate", "recall", "mrr", "ndcg", "parent_hit_rate", "parent_recall")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="retrieval_dev.jsonl")
    parser.add_argument("--run-name", default="dev_v1")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--bootstrap-samples", type=int, default=1000)
    return parser.parse_args()


def metrics_for(hits, relevant_children: set[str], relevant_parents: set[str], k: int) -> dict:
    top = hits[:k]
    child_ids = [hit.id for hit in top]
    parent_ids = [hit.parent_id for hit in top]
    child_matches = relevant_children.intersection(child_ids)
    parent_matches = relevant_parents.intersection(parent_ids)
    first_rank = next(
        (rank for rank, child_id in enumerate(child_ids, start=1) if child_id in relevant_children),
        None,
    )
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, child_id in enumerate(child_ids, start=1)
        if child_id in relevant_children
    )
    ideal_count = min(k, len(relevant_children))
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
    return {
        "hit_rate": float(bool(child_matches)),
        "recall": len(child_matches) / max(1, len(relevant_children)),
        "mrr": 1.0 / first_rank if first_rank else 0.0,
        "ndcg": dcg / idcg if idcg else 0.0,
        "parent_hit_rate": float(bool(parent_matches)),
        "parent_recall": len(parent_matches) / max(1, len(relevant_parents)),
    }


def serialize_hits(hits, k: int) -> list[dict]:
    return [
        {
            "rank": rank,
            "id": hit.id,
            "parent_id": hit.parent_id,
            "source": hit.source,
            "heading": hit.heading,
            "locator": hit.locator,
            "score": round(float(hit.score), 8),
            "rerank_score": None if hit.rerank_score is None else round(float(hit.rerank_score), 8),
            "retrieval_method": hit.retrieval_method,
        }
        for rank, hit in enumerate(hits[:k], start=1)
    ]


def bootstrap_ci(values: list[float], samples: int, seed: int) -> list[float]:
    if not values:
        return [0.0, 0.0]
    rng = random.Random(seed)
    estimates = [
        statistics.mean(rng.choice(values) for _ in range(len(values)))
        for _ in range(samples)
    ]
    estimates.sort()
    lower = estimates[max(0, int(samples * 0.025) - 1)]
    upper = estimates[min(samples - 1, int(samples * 0.975))]
    return [round(lower, 4), round(upper, 4)]


def load_or_embed(rows: list[dict], run_dir: Path, retriever) -> tuple[np.ndarray, float]:
    vector_path = run_dir / "query_embeddings.npz"
    ids_path = run_dir / "query_embedding_ids.json"
    ids = [row["id"] for row in rows]
    if vector_path.is_file() and ids_path.is_file():
        cached_ids = json.loads(ids_path.read_text(encoding="utf-8"))
        if cached_ids == ids:
            vectors = np.load(vector_path)["vectors"]
            return vectors, 0.0

    started = time.perf_counter()
    vectors = np.asarray(
        retriever.embeddings.embed_documents([row["question"] for row in rows]),
        dtype=np.float32,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    np.savez_compressed(vector_path, vectors=vectors)
    ids_path.write_text(json.dumps(ids, ensure_ascii=False, indent=2), encoding="utf-8")
    return vectors, elapsed_ms


def evaluate_question(row: dict, vector: list[float], store, retriever, settings, k: int) -> dict:
    relevant_children = set(row["relevant_child_ids"])
    relevant_parents = set(row["relevant_parent_ids"])
    result = {
        "question_id": row["id"],
        "question": row["question"],
        "category": row["category"],
        "domain_code": row["domain_code"],
        "relevant_fact_ids": row["relevant_fact_ids"],
        "relevant_child_ids": row["relevant_child_ids"],
        "relevant_parent_ids": row["relevant_parent_ids"],
        "modes": {},
    }

    dense_started = time.perf_counter()
    try:
        dense_hits = store.search_dense(vector, limit=k)
        dense_error = ""
    except Exception as exc:
        dense_hits = []
        dense_error = f"{type(exc).__name__}: {exc}"
    dense_ms = (time.perf_counter() - dense_started) * 1000
    result["modes"]["dense"] = {
        **metrics_for(dense_hits, relevant_children, relevant_parents, k),
        "latency_ms": round(dense_ms, 3),
        "error": dense_error,
        "hits": serialize_hits(dense_hits, k),
    }

    hybrid_started = time.perf_counter()
    try:
        candidates = store.search_hybrid(row["question"], vector, limit=settings.fusion_top_k)
        hybrid_error = ""
    except Exception as exc:
        candidates = []
        hybrid_error = f"{type(exc).__name__}: {exc}"
    hybrid_ms = (time.perf_counter() - hybrid_started) * 1000
    result["modes"]["hybrid"] = {
        **metrics_for(candidates, relevant_children, relevant_parents, k),
        "latency_ms": round(hybrid_ms, 3),
        "error": hybrid_error,
        "hits": serialize_hits(candidates, k),
    }

    rerank_started = time.perf_counter()
    reranked = []
    rerank_error = hybrid_error
    if candidates and not hybrid_error:
        try:
            rankings = retriever.reranker.rerank(
                row["question"],
                [hit.text for hit in candidates],
                top_n=k,
            )
            for ranking in rankings:
                hit = candidates[ranking.index]
                hit.rerank_score = ranking.score
                hit.retrieval_method = "hybrid_rrf_bge_rerank"
                reranked.append(hit)
            rerank_error = ""
        except Exception as exc:
            rerank_error = f"{type(exc).__name__}: {exc}"
    rerank_ms = (time.perf_counter() - rerank_started) * 1000
    result["modes"]["hybrid_rerank"] = {
        **metrics_for(reranked, relevant_children, relevant_parents, k),
        "latency_ms": round(hybrid_ms + rerank_ms, 3),
        "rerank_only_ms": round(rerank_ms, 3),
        "error": rerank_error,
        "hits": serialize_hits(reranked, k),
    }
    return result


def summarize(details: list[dict], embedding_ms_per_query: float, bootstrap_samples: int) -> dict:
    summary: dict[str, dict] = {}
    for mode_index, mode in enumerate(MODES):
        entries = [row["modes"][mode] for row in details]
        mode_summary = {
            "questions": len(entries),
            "errors": sum(bool(entry["error"]) for entry in entries),
            "mean_embedding_latency_ms": round(embedding_ms_per_query, 3),
            "mean_retrieval_latency_ms": round(statistics.mean(entry["latency_ms"] for entry in entries), 3),
            "p95_retrieval_latency_ms": round(
                sorted(entry["latency_ms"] for entry in entries)[max(0, int(len(entries) * 0.95) - 1)],
                3,
            ),
        }
        for metric_index, metric in enumerate(METRICS):
            values = [entry[metric] for entry in entries]
            mode_summary[metric] = round(statistics.mean(values), 4)
            mode_summary[f"{metric}_95ci"] = bootstrap_ci(
                values,
                bootstrap_samples,
                seed=20260827 + mode_index * 100 + metric_index,
            )

        categories = defaultdict(list)
        for row in details:
            categories[row["category"]].append(row["modes"][mode])
        mode_summary["by_category"] = {
            category: {
                "questions": len(values),
                **{
                    metric: round(statistics.mean(item[metric] for item in values), 4)
                    for metric in METRICS
                },
            }
            for category, values in sorted(categories.items())
        }
        summary[mode] = mode_summary
    return summary


def write_csv(path: Path, details: list[dict]) -> None:
    rows = []
    for detail in details:
        for mode in MODES:
            values = detail["modes"][mode]
            rows.append(
                {
                    "question_id": detail["question_id"],
                    "question": detail["question"],
                    "category": detail["category"],
                    "domain_code": detail["domain_code"],
                    "mode": mode,
                    **{metric: values[metric] for metric in METRICS},
                    "latency_ms": values["latency_ms"],
                    "error": values["error"],
                    "top_child_ids": json.dumps([hit["id"] for hit in values["hits"]]),
                    "top_parent_ids": json.dumps([hit["parent_id"] for hit in values["hits"]]),
                    "top_sources": json.dumps([hit["source"] for hit in values["hits"]], ensure_ascii=False),
                }
            )
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    if args.k < 1:
        raise ValueError("--k must be positive")
    dataset_path = BENCHMARK_DIR / args.dataset
    rows = read_jsonl(dataset_path)
    if any(not row.get("relevant_child_ids") for row in rows):
        raise RuntimeError("dataset is not linked; run link_ground_truth.py first")

    run_dir = RESULTS_DIR / args.run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    details_path = run_dir / "retrieval_details.jsonl"
    if args.restart and details_path.exists():
        details_path.unlink()

    settings, store, _, retriever = build_retrieval_stack()
    vectors, embedding_total_ms = load_or_embed(rows, run_dir, retriever)
    embedding_ms_per_query = embedding_total_ms / max(1, len(rows))

    completed: dict[str, dict] = {}
    if details_path.is_file():
        for detail in read_jsonl(details_path):
            completed[detail["question_id"]] = detail
    started = time.perf_counter()
    with details_path.open("a", encoding="utf-8") as handle:
        for number, (row, vector) in enumerate(zip(rows, vectors, strict=True), start=1):
            if row["id"] in completed:
                continue
            detail = evaluate_question(row, vector.tolist(), store, retriever, settings, args.k)
            completed[row["id"]] = detail
            handle.write(json.dumps(detail, ensure_ascii=False) + "\n")
            handle.flush()
            if number % 10 == 0 or number == len(rows):
                errors = sum(
                    any(value["error"] for value in item["modes"].values())
                    for item in completed.values()
                )
                print(
                    f"[{number}/{len(rows)}] completed={len(completed)} errors={errors} "
                    f"elapsed={time.perf_counter() - started:.1f}s",
                    flush=True,
                )

    details = [completed[row["id"]] for row in rows]
    summary = summarize(details, embedding_ms_per_query, args.bootstrap_samples)
    report = {
        "run_name": args.run_name,
        "dataset": args.dataset,
        "dataset_questions": len(rows),
        "dataset_categories": dict(Counter(row["category"] for row in rows)),
        "collection": settings.milvus_collection,
        "k": args.k,
        "candidate_k": settings.fusion_top_k,
        "models": {
            "embedding": settings.embedding_model,
            "reranker": settings.rerank_model,
        },
        "embedding_total_ms_this_run": round(embedding_total_ms, 3),
        "completed_at": datetime.now().astimezone().isoformat(),
        "results": summary,
    }
    (run_dir / "retrieval_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_csv(run_dir / "retrieval_details.csv", details)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
