"""Freeze benchmark inputs and retrieval parameters before the blind test run."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path

from benchmark_common import BENCHMARK_DIR, COLLECTION_NAME, RESULTS_DIR, build_settings


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev-run", default="dev_v1")
    parser.add_argument("--output", default="frozen_experiment_config.json")
    args = parser.parse_args()

    settings = build_settings()
    input_names = [
        "facts.jsonl",
        "retrieval_dev.jsonl",
        "retrieval_test.jsonl",
        "grounding_test.jsonl",
        "corpus_manifest.json",
    ]
    inputs = {}
    for name in input_names:
        path = BENCHMARK_DIR / name
        inputs[name] = {"sha256": sha256(path), "bytes": path.stat().st_size}

    dev_summary = RESULTS_DIR / args.dev_run / "retrieval_summary.json"
    if not dev_summary.exists():
        raise FileNotFoundError(f"Missing development result: {dev_summary}")

    frozen = {
        "protocol": "benchmark_v1",
        "status": "frozen_before_test",
        "frozen_at": datetime.now().astimezone().isoformat(),
        "collection": COLLECTION_NAME,
        "inputs": inputs,
        "development_result": {
            "path": str(dev_summary.relative_to(BENCHMARK_DIR)),
            "sha256": sha256(dev_summary),
        },
        "retrieval": {
            "evaluated_k": 5,
            "dense_top_k": settings.dense_top_k,
            "sparse_top_k": settings.sparse_top_k,
            "fusion_top_k": settings.fusion_top_k,
            "rerank_top_k": settings.rerank_top_k,
            "embedding_model": settings.embedding_model,
            "rerank_model": settings.rerank_model,
        },
        "chunking": {
            "parent_chunk_size": settings.parent_chunk_size,
            "child_chunk_size": settings.child_chunk_size,
            "child_chunk_overlap": settings.child_chunk_overlap,
        },
        "test_policy": "No parameter, label, corpus, or query changes after this file is written.",
    }

    output = BENCHMARK_DIR / args.output
    output.write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(frozen, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
