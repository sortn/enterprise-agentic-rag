from __future__ import annotations

import argparse
import csv
from datetime import UTC, datetime
import json
from pathlib import Path

from .metrics import evaluate_records
from .schemas import AgentTrace


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate deterministic Agent evaluation traces")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("evaluation/results"))
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()
    records = [
        AgentTrace.model_validate(item).model_dump(mode="json")
        for item in read_jsonl(args.dataset)
    ]
    report = {
        "experiment": args.experiment,
        "dataset": str(args.dataset),
        "created_at": datetime.now(UTC).isoformat(),
        **evaluate_records(records, args.k),
    }
    target = args.output_dir / args.experiment
    target.mkdir(parents=True, exist_ok=True)
    path = target / "evaluation_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    detail_rows = []
    for source, score in zip(records, report["details"], strict=True):
        detail_rows.append(
            {
                "case_id": source.get("case_id", source.get("id", "")),
                "run_id": source.get("run_id", ""),
                "tags": json.dumps(source.get("tags", []), ensure_ascii=False),
                **score,
            }
        )
    if detail_rows:
        with (target / "evaluation_report.csv").open(
            "w", newline="", encoding="utf-8-sig"
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=list(detail_rows[0]))
            writer.writeheader()
            writer.writerows(detail_rows)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
