"""Measure citation coverage, false refusal and unsupported-answer rate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import uuid


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "project"
sys.path.insert(0, str(PROJECT))

from core.rag_system import RAGSystem  # noqa: E402


REFUSAL_MARKERS = ("没有足够依据", "没有找到足够", "暂时无法回答", "证据不足")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=ROOT / "evaluation" / "answer_qa.json")
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation" / "results" / "answer_summary.json")
    parser.add_argument("--ingest-samples", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    samples = json.loads(args.dataset.read_text(encoding="utf-8"))
    system = RAGSystem().initialize()
    if args.ingest_samples:
        for path in sorted((ROOT / "sample_data" / "generated").glob("*")):
            if path.is_file() and path.suffix.lower() in system.settings.allowed_extensions:
                system.ingestion.ingest(path)

    details = []
    for item in samples:
        result = system.chat(item["question"], str(uuid.uuid4()))
        refused = any(marker in result["answer"] for marker in REFUSAL_MARKERS)
        citations = result.get("citations", [])
        expected_source = item.get("expected_source", "")
        source_matched = not expected_source or any(
            citation.get("source") == expected_source for citation in citations
        )
        details.append(
            {
                "id": item["id"],
                "answerable": item["answerable"],
                "refused": refused,
                "grounded": result.get("grounded", False),
                "source_matched": source_matched,
                "answer": result["answer"],
                "citations": citations,
            }
        )
        print(f"[{len(details)}/{len(samples)}] {item['id']}")

    answerable = [row for row in details if row["answerable"]]
    unanswerable = [row for row in details if not row["answerable"]]
    summary = {
        "samples": len(details),
        "answerable_citation_recall": round(
            sum(not row["refused"] and row["source_matched"] for row in answerable)
            / max(1, len(answerable)),
            4,
        ),
        "false_refusal_rate": round(
            sum(row["refused"] for row in answerable) / max(1, len(answerable)),
            4,
        ),
        "unsupported_answer_rate": round(
            sum(not row["refused"] for row in unanswerable) / max(1, len(unanswerable)),
            4,
        ),
        "grounded_rate": round(
            sum(row["grounded"] for row in details) / max(1, len(details)),
            4,
        ),
        "details": details,
        "metric_note": "unsupported_answer_rate 仅统计不可回答样本是否被安全拒答，不替代人工事实审查。",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "details"}, ensure_ascii=False, indent=2))
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
