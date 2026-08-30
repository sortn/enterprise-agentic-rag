"""Evaluate answer support and refusal behavior on the frozen benchmark.

The comparison is deliberately operational and reproducible:

* ``dense_rag``: dense top-5 child retrieval followed by one direct generation.
* ``agentic_rag``: the complete application graph (planning, hybrid retrieval,
  BGE reranking, parent expansion, fact checking, retry, and refusal).

No LLM-as-judge is used. Answerable questions are checked with frozen answer
keywords and source labels. An unsupported answer is an attempted answer to a
frozen unanswerable question instead of an explicit refusal.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
import math
from pathlib import Path
import random
import re
import statistics
import sys
import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from benchmark_common import BENCHMARK_DIR, RESULTS_DIR, build_settings, read_jsonl


PROJECT = Path(__file__).resolve().parents[1] / "project"
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from core.rag_system import RAGSystem  # noqa: E402
from services.model_clients import build_chat_model  # noqa: E402


BASELINE_PROMPT = """你是一个传统的企业知识库 RAG 助手。请只根据给出的检索片段回答问题。
如果片段没有包含答案，请明确说“检索片段没有足够依据”，不要用常识补充。
回答保持简洁；使用数字时保留单位。"""

REFUSAL_PATTERNS = (
    "没有足够依据",
    "没有相关规定",
    "没有找到",
    "未找到",
    "无法回答",
    "无法确定",
    "不能确定",
    "不知道",
    "不确定",
    "缺少相关",
    "没有包含答案",
    "没有提及",
    "未提供",
)


def normalize(text: str) -> str:
    return re.sub(r"[\s,，。；;：:]", "", str(text).lower())


def is_refusal(answer: str) -> bool:
    compact = normalize(answer)
    return any(normalize(pattern) in compact for pattern in REFUSAL_PATTERNS)


def has_keywords(answer: str, keywords: list[str]) -> bool:
    compact = normalize(answer)
    return bool(keywords) and all(normalize(keyword) in compact for keyword in keywords)


def source_matches(citations: list[dict[str, Any]], relevant_source: str) -> bool:
    if not relevant_source:
        return False
    target = Path(relevant_source).name.lower()
    for citation in citations:
        source = str(citation.get("source", "")).replace("\\", "/")
        if Path(source).name.lower() == target or target in source.lower():
            return True
    return False


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(quantile * len(ordered)) - 1))
    return ordered[index]


def bootstrap_ci(values: list[float], seed: int, samples: int = 2000) -> list[float]:
    if not values:
        return [0.0, 0.0]
    rng = random.Random(seed)
    means = []
    for _ in range(samples):
        means.append(statistics.fmean(rng.choice(values) for _ in values))
    means.sort()
    return [round(means[int(samples * 0.025)], 4), round(means[int(samples * 0.975)], 4)]


def score_answer(row: dict[str, Any], answer: str, citations: list[dict[str, Any]]) -> dict[str, Any]:
    refused = is_refusal(answer)
    answerable = bool(row["answerable"])
    keyword_correct = answerable and (not refused) and has_keywords(answer, row["answer_keywords"])
    citation_correct = answerable and source_matches(citations, row["relevant_source"])
    unsupported = (not answerable) and (not refused)
    false_refusal = answerable and refused
    successful = (answerable and keyword_correct) or ((not answerable) and refused)
    return {
        "refused": refused,
        "keyword_correct": keyword_correct,
        "citation_correct": citation_correct,
        "unsupported_answer": unsupported,
        "false_refusal": false_refusal,
        "successful": successful,
    }


def dense_baseline(system: RAGSystem, llm, row: dict[str, Any]) -> dict[str, Any]:
    start = time.perf_counter()
    hits = system.retriever.retrieve(row["question"], mode="dense", top_k=5)
    blocks = []
    citations = []
    for index, hit in enumerate(hits, start=1):
        blocks.append(f"[片段 {index}｜来源：{hit.source}]\n{hit.text}")
        citations.append({"source": hit.source, "locator": hit.locator})
    evidence = "\n\n".join(blocks) if blocks else "（没有检索结果）"
    response = llm.invoke(
        [
            SystemMessage(content=BASELINE_PROMPT),
            HumanMessage(content=f"问题：\n{row['question']}\n\n检索片段：\n{evidence}"),
        ]
    )
    answer = str(response.content).strip()
    latency = (time.perf_counter() - start) * 1000
    return {
        "answer": answer,
        "citations": citations,
        "latency_ms": round(latency, 3),
        "retrieved_ids": [hit.id for hit in hits],
        "retrieved_parent_ids": [hit.parent_id for hit in hits],
        "retrieved_source_match": source_matches(citations, row["relevant_source"]),
        **score_answer(row, answer, citations),
    }


def agentic(system: RAGSystem, row: dict[str, Any]) -> dict[str, Any]:
    start = time.perf_counter()
    result = system.chat(row["question"], thread_id=f"grounding-{row['id']}")
    latency = (time.perf_counter() - start) * 1000
    answer = str(result.get("answer", ""))
    citations = list(result.get("citations", []))
    return {
        "answer": answer,
        "citations": citations,
        "latency_ms": round(latency, 3),
        "intent": result.get("intent", ""),
        "rewritten_query": result.get("rewritten_query", ""),
        "reported_grounded": bool(result.get("grounded", False)),
        "retrieval_attempts": int(result.get("retrieval_attempts", 0)),
        **score_answer(row, answer, citations),
    }


def evaluate_one(
    system: RAGSystem,
    llm,
    row: dict[str, Any],
    reused_dense: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    record = {
        "id": row["id"],
        "question": row["question"],
        "answerable": row["answerable"],
        "category": row["category"],
        "domain_code": row["domain_code"],
        "reference_answer": row["reference_answer"],
        "answer_keywords": row["answer_keywords"],
        "relevant_source": row["relevant_source"],
    }
    try:
        record["dense_rag"] = reused_dense.get(row["id"]) or dense_baseline(system, llm, row)
        record["agentic_rag"] = agentic(system, row)
        record["error"] = ""
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    return record


def method_summary(records: list[dict[str, Any]], method: str, seed: int) -> dict[str, Any]:
    valid = [record for record in records if not record.get("error") and method in record]
    answerable = [record for record in valid if record["answerable"]]
    unanswerable = [record for record in valid if not record["answerable"]]

    def flags(rows: list[dict[str, Any]], field: str) -> list[float]:
        return [float(bool(row[method][field])) for row in rows]

    unsupported_all = flags(valid, "unsupported_answer")
    unsupported_unanswerable = flags(unanswerable, "unsupported_answer")
    correct = flags(answerable, "keyword_correct")
    successful = flags(valid, "successful")
    citation_correct = flags(answerable, "citation_correct")
    latencies = [float(row[method]["latency_ms"]) for row in valid]
    return {
        "questions": len(valid),
        "errors": len(records) - len(valid),
        "answerable_questions": len(answerable),
        "unanswerable_questions": len(unanswerable),
        "answerable_keyword_accuracy": round(statistics.fmean(correct), 4),
        "answerable_keyword_accuracy_95ci": bootstrap_ci(correct, seed + 1),
        "answerable_source_recall": round(statistics.fmean(citation_correct), 4),
        "unanswerable_refusal_rate": round(1 - statistics.fmean(unsupported_unanswerable), 4),
        "unanswerable_refusal_rate_95ci": [
            round(1 - value, 4) for value in reversed(bootstrap_ci(unsupported_unanswerable, seed + 2))
        ],
        "unsupported_answer_rate_overall": round(statistics.fmean(unsupported_all), 4),
        "unsupported_answer_rate_overall_95ci": bootstrap_ci(unsupported_all, seed + 3),
        "task_success_rate": round(statistics.fmean(successful), 4),
        "task_success_rate_95ci": bootstrap_ci(successful, seed + 4),
        "mean_latency_ms": round(statistics.fmean(latencies), 3),
        "p95_latency_ms": round(percentile(latencies, 0.95), 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="grounding_test.jsonl")
    parser.add_argument("--run-name", default="grounding_v1")
    parser.add_argument("--max-workers", type=int, default=3)
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--reuse-dense-from",
        default="",
        help="Reuse dense_rag records from another run while re-evaluating the agent.",
    )
    parser.add_argument(
        "--retry-tail",
        type=int,
        default=0,
        help="Re-run the last N completed records (useful after a transient rate-limit window).",
    )
    parser.add_argument("--restart", action="store_true")
    args = parser.parse_args()

    rows = read_jsonl(BENCHMARK_DIR / args.dataset)
    if args.limit:
        rows = rows[: args.limit]
    result_dir = RESULTS_DIR / args.run_name
    result_dir.mkdir(parents=True, exist_ok=True)
    detail_path = result_dir / "grounding_details.jsonl"
    if args.restart:
        detail_path.unlink(missing_ok=True)

    completed = {}
    if detail_path.exists():
        for record in read_jsonl(detail_path):
            # Failed records never count as complete. Later successful duplicate
            # records replace earlier attempts when a run is resumed.
            if record.get("error"):
                completed.pop(record["id"], None)
            else:
                completed[record["id"]] = record
    if args.retry_tail:
        retry_ids = list(completed)[-args.retry_tail :]
        for record_id in retry_ids:
            completed.pop(record_id, None)
    pending = [row for row in rows if row["id"] not in completed]

    reused_dense: dict[str, dict[str, Any]] = {}
    if args.reuse_dense_from:
        reuse_path = RESULTS_DIR / args.reuse_dense_from / "grounding_details.jsonl"
        for record in read_jsonl(reuse_path):
            if not record.get("error") and record.get("dense_rag"):
                reused_dense[record["id"]] = record["dense_rag"]

    settings = build_settings()
    system = RAGSystem(settings).initialize()
    llm = build_chat_model(settings)
    started = time.perf_counter()
    errors = sum(bool(record.get("error")) for record in completed.values())
    with detail_path.open("a", encoding="utf-8") as output:
        with ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as executor:
            futures = {
                executor.submit(evaluate_one, system, llm, row, reused_dense): row
                for row in pending
            }
            for index, future in enumerate(as_completed(futures), start=1):
                record = future.result()
                completed[record["id"]] = record
                errors += bool(record.get("error"))
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
                output.flush()
                if index % 5 == 0 or index == len(pending):
                    print(
                        f"[{len(completed)}/{len(rows)}] completed={len(completed)} "
                        f"errors={errors} elapsed={time.perf_counter() - started:.1f}s",
                        flush=True,
                    )

    ordered = [completed[row["id"]] for row in rows if row["id"] in completed]
    summary = {
        "run_name": args.run_name,
        "dataset": args.dataset,
        "questions": len(rows),
        "answerable_questions": sum(bool(row["answerable"]) for row in rows),
        "unanswerable_questions": sum(not bool(row["answerable"]) for row in rows),
        "completed_at": datetime.now().astimezone().isoformat(),
        "metric_definition": {
            "unsupported_answer": "The system attempted an answer to a frozen unanswerable question.",
            "unsupported_answer_rate_overall": "Unsupported answers divided by all evaluated questions.",
            "answerable_keyword_accuracy": "All frozen answer keywords occur in a non-refusal answer.",
            "task_success": "Correct-keyword answer when answerable, or refusal when unanswerable.",
            "judge": "deterministic labels and string rules; no LLM judge",
        },
        "methods": {
            "dense_rag": method_summary(ordered, "dense_rag", 20260827),
            "agentic_rag": method_summary(ordered, "agentic_rag", 20260837),
        },
    }
    summary_path = result_dir / "grounding_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
