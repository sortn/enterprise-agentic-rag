from __future__ import annotations

import argparse
import json
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a human-review queue from failed production/evaluation traces"
    )
    parser.add_argument("traces", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    failures = []
    for row in read_jsonl(args.traces):
        failed = bool(row.get("error")) or row.get("final_status") in {
            "failed",
            "timeout",
        }
        unsuccessful = row.get("success") is False
        if not failed and not unsuccessful:
            continue
        failures.append(
            {
                "case_id": row.get("case_id") or f"failure-{row.get('run_id', 'unknown')}",
                "query": row.get("query", row.get("question", "")),
                "reference_answer": row.get("reference_answer", ""),
                "relevant_document_ids": row.get("relevant_document_ids", []),
                "relevant_chunk_ids": row.get("relevant_chunk_ids", []),
                "should_refuse": row.get("should_refuse", False),
                "expected_rewrite": row.get("expected_rewrite"),
                "expected_tools": row.get("expected_tools", []),
                "tags": sorted(set([*row.get("tags", []), "failure_feedback"])),
                "source_run_id": row.get("run_id", ""),
                "review_required": True,
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in failures),
        encoding="utf-8",
    )
    print(f"queued={len(failures)} output={args.output}")


if __name__ == "__main__":
    main()
