"""Validate benchmark_v1 counts, hashes, labels, uniqueness and parsability."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "project"
sys.path.insert(0, str(PROJECT))

from ingestion.parsers import MultiFormatParser  # noqa: E402


DEFAULT_ROOT = ROOT / "evaluation" / "benchmark_v1"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_unique(rows: list[dict], field: str, label: str) -> None:
    values = [row[field] for row in rows]
    duplicates = [value for value, count in Counter(values).items() if count > 1]
    if duplicates:
        raise ValueError(f"{label} has duplicate {field}: {duplicates[:5]}")


def validate_dataset(
    rows: list[dict],
    label: str,
    facts_by_id: dict[str, dict],
    require_linked: bool,
) -> None:
    require_unique(rows, "id", label)
    require_unique(rows, "question", label)
    for row in rows:
        if row["answerable"]:
            if not row["relevant_fact_ids"]:
                raise ValueError(f"{row['id']} has no relevant facts")
            for fact_id in row["relevant_fact_ids"]:
                fact = facts_by_id.get(fact_id)
                if not fact:
                    raise ValueError(f"{row['id']} references missing fact {fact_id}")
                if row["relevant_source"] != fact["source"]:
                    raise ValueError(f"{row['id']} source does not match fact source")
            if require_linked and (
                not row.get("relevant_child_ids") or not row.get("relevant_parent_ids")
            ):
                raise ValueError(f"{row['id']} is not linked to indexed chunks")
        elif any(
            row.get(field)
            for field in ("relevant_fact_ids", "relevant_child_ids", "relevant_parent_ids")
        ):
            raise ValueError(f"unanswerable row {row['id']} contains relevance labels")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--parse-corpus", action="store_true")
    parser.add_argument("--require-linked", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.root
    manifest = json.loads((root / "corpus_manifest.json").read_text(encoding="utf-8"))
    facts = read_jsonl(root / "facts.jsonl")
    dev = read_jsonl(root / "retrieval_dev.jsonl")
    test = read_jsonl(root / "retrieval_test.jsonl")
    grounding = read_jsonl(root / "grounding_test.jsonl")
    facts_by_id = {fact["fact_id"]: fact for fact in facts}

    require_unique(facts, "fact_id", "facts")
    require_unique(facts, "clause_code", "facts")
    validate_dataset(dev, "retrieval_dev", facts_by_id, args.require_linked)
    validate_dataset(test, "retrieval_test", facts_by_id, args.require_linked)
    validate_dataset(grounding, "grounding_test", facts_by_id, args.require_linked)

    dev_facts = {fact_id for row in dev for fact_id in row["relevant_fact_ids"]}
    test_facts = {fact_id for row in test for fact_id in row["relevant_fact_ids"]}
    if dev_facts & test_facts:
        raise ValueError("development and frozen test sets share facts")

    documents = manifest["documents"]
    require_unique(documents, "source", "manifest")
    sources = {document["source"] for document in documents}
    for document in documents:
        path = root / "corpus" / document["source"]
        if not path.is_file():
            raise FileNotFoundError(path)
        if sha256(path) != document["sha256"]:
            raise ValueError(f"hash mismatch: {path.name}")
    if any(fact["source"] not in sources for fact in facts):
        raise ValueError("facts contain a source absent from the manifest")

    parsed_units = 0
    parsed_chars = 0
    if args.parse_corpus:
        parser = MultiFormatParser()
        facts_by_source: dict[str, list[dict]] = {}
        for fact in facts:
            facts_by_source.setdefault(fact["source"], []).append(fact)
        for number, document in enumerate(documents, start=1):
            parsed = parser.parse(root / "corpus" / document["source"])
            text = "\n".join(unit.text for unit in parsed.units)
            parsed_units += len(parsed.units)
            parsed_chars += len(text)
            missing = [
                fact["clause_code"]
                for fact in facts_by_source[document["source"]]
                if fact["clause_code"] not in text
            ]
            if missing:
                raise ValueError(f"parser lost clause codes in {document['source']}: {missing[:3]}")
            print(f"[{number}/{len(documents)}] {document['source']}: {len(parsed.units)} units")

    summary = {
        "valid": True,
        "linked": args.require_linked,
        "documents": len(documents),
        "formats": dict(Counter(document["format"] for document in documents)),
        "facts": len(facts),
        "retrieval_dev": len(dev),
        "retrieval_test": len(test),
        "grounding_test": len(grounding),
        "grounding_answerable": sum(row["answerable"] for row in grounding),
        "grounding_unanswerable": sum(not row["answerable"] for row in grounding),
        "dev_categories": dict(Counter(row["category"] for row in dev)),
        "test_categories": dict(Counter(row["category"] for row in test)),
        "parsed_units": parsed_units,
        "parsed_characters": parsed_chars,
    }
    (root / "validation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
