"""Link stable fact/clause labels to actual Milvus child and parent IDs."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import json

from benchmark_common import (
    BENCHMARK_DIR,
    COLLECTION_NAME,
    build_retrieval_stack,
    read_jsonl,
    write_jsonl,
)


DATASETS = ("retrieval_dev.jsonl", "retrieval_test.jsonl", "grounding_test.jsonl")


def main() -> None:
    _, store, _, _ = build_retrieval_stack()
    chunks = store.client.query(
        collection_name=COLLECTION_NAME,
        filter='doc_id != ""',
        output_fields=["id", "doc_id", "parent_id", "source", "heading", "locator", "text"],
        limit=16384,
    )
    chunks_by_source: dict[str, list[dict]] = defaultdict(list)
    for chunk in chunks:
        chunks_by_source[str(chunk["source"])].append(chunk)

    facts = read_jsonl(BENCHMARK_DIR / "facts.jsonl")
    mapping: dict[str, dict[str, list[str]]] = {}
    missing: list[str] = []
    for fact in facts:
        matches = [
            chunk
            for chunk in chunks_by_source.get(fact["source"], [])
            if fact["clause_code"] in str(chunk.get("text", ""))
        ]
        child_ids = sorted({str(chunk["id"]) for chunk in matches})
        parent_ids = sorted({str(chunk["parent_id"]) for chunk in matches})
        mapping[fact["fact_id"]] = {
            "child_ids": child_ids,
            "parent_ids": parent_ids,
        }
        fact["relevant_child_ids"] = child_ids
        fact["relevant_parent_ids"] = parent_ids
        if not child_ids or not parent_ids:
            missing.append(fact["fact_id"])

    if missing:
        raise RuntimeError(f"{len(missing)} facts could not be linked: {missing[:10]}")

    write_jsonl(BENCHMARK_DIR / "facts.jsonl", facts)
    for dataset_name in DATASETS:
        rows = read_jsonl(BENCHMARK_DIR / dataset_name)
        for row in rows:
            if not row["answerable"]:
                continue
            child_ids = set()
            parent_ids = set()
            for fact_id in row["relevant_fact_ids"]:
                child_ids.update(mapping[fact_id]["child_ids"])
                parent_ids.update(mapping[fact_id]["parent_ids"])
            row["relevant_child_ids"] = sorted(child_ids)
            row["relevant_parent_ids"] = sorted(parent_ids)
        write_jsonl(BENCHMARK_DIR / dataset_name, rows)

    manifest_path = BENCHMARK_DIR / "corpus_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["label_status"] = "linked_to_milvus_chunks"
    manifest["linked_collection"] = COLLECTION_NAME
    manifest["linked_at"] = datetime.now().astimezone().isoformat()
    manifest["indexed_chunks"] = len(chunks)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    child_counts = [len(value["child_ids"]) for value in mapping.values()]
    parent_counts = [len(value["parent_ids"]) for value in mapping.values()]
    summary = {
        "collection": COLLECTION_NAME,
        "chunks": len(chunks),
        "facts": len(facts),
        "missing_facts": len(missing),
        "mean_relevant_children_per_fact": round(sum(child_counts) / len(child_counts), 4),
        "mean_relevant_parents_per_fact": round(sum(parent_counts) / len(parent_counts), 4),
    }
    (BENCHMARK_DIR / "label_link_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
