from __future__ import annotations

from collections import defaultdict
import math
import statistics
from typing import Any, Iterable


def safe_mean(values: Iterable[float]) -> float:
    values = [value for value in values if value is not None]
    return round(statistics.fmean(values), 6) if values else 0.0


def percentile(values: Iterable[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * quantile) - 1))
    return round(float(ordered[index]), 6)


def retrieval_metrics(
    ranked_ids: list[str], relevant_ids: set[str], k: int = 5
) -> dict[str, float | None]:
    if not relevant_ids:
        return {f"hit@{k}": None, f"recall@{k}": None, "mrr": None, "ndcg": None}
    ranked = ranked_ids[:k]
    matches = relevant_ids.intersection(ranked)
    first_rank = next(
        (index for index, item in enumerate(ranked, start=1) if item in relevant_ids),
        None,
    )
    dcg = sum(
        1 / math.log2(index + 1)
        for index, item in enumerate(ranked, start=1)
        if item in relevant_ids
    )
    ideal = sum(
        1 / math.log2(index + 1)
        for index in range(1, min(k, len(relevant_ids)) + 1)
    )
    return {
        f"hit@{k}": float(bool(matches)),
        f"recall@{k}": len(matches) / max(1, len(relevant_ids)),
        "mrr": 1 / first_rank if first_rank else 0.0,
        "ndcg": dcg / ideal if ideal else 0.0,
    }


def citation_metrics(
    actual_sources: Iterable[str], relevant_sources: Iterable[str]
) -> dict[str, float]:
    actual = {normalize_source(item) for item in actual_sources if item}
    relevant = {normalize_source(item) for item in relevant_sources if item}
    matched = actual.intersection(relevant)
    return {
        "citation_precision": len(matched) / max(1, len(actual)),
        "citation_recall": len(matched) / max(1, len(relevant)),
    }


def normalize_source(source: str) -> str:
    return source.replace("\\", "/").rsplit("/", 1)[-1].strip().lower()


def evaluate_record(record: dict[str, Any], k: int = 5) -> dict[str, Any]:
    expected_rewrite = record.get("expected_rewrite")
    rewritten = str(record.get("rewritten_query", "")).strip()
    query = str(record.get("query", record.get("question", ""))).strip()
    rewrite_triggered = bool(rewritten and rewritten != query)
    should_refuse = bool(record.get("should_refuse", not record.get("answerable", True)))
    refused = bool(record.get("refused", False))
    citations = record.get("citations", [])
    actual_sources = [
        item.get("source", "") if isinstance(item, dict) else str(item)
        for item in citations
    ]
    relevant_sources = record.get("relevant_sources") or [
        record.get("relevant_source", "")
    ]
    retrieval = retrieval_metrics(
        list(record.get("retrieved_chunk_ids", [])),
        set(record.get("relevant_chunk_ids", record.get("relevant_child_ids", []))),
        k,
    )
    citation = citation_metrics(actual_sources, relevant_sources)
    answer_correct = bool(
        record.get("answer_correct", record.get("keyword_correct", False))
    )
    grounded = bool(record.get("grounded", record.get("reported_grounded", False)))
    route_correct = (
        record.get("expected_route") in {None, record.get("route", record.get("intent"))}
    )
    rewrite_correct = expected_rewrite is None or bool(expected_rewrite) == rewrite_triggered
    loop_count = int(record.get("loop_count", record.get("retrieval_attempts", 0)))
    max_loops = int(record.get("max_loops", 2))
    expected_tools = list(record.get("expected_tools", []))
    actual_tools = list(record.get("actual_tools", record.get("tools", [])))
    tool_selection_correct = not expected_tools or actual_tools == expected_tools
    expected_args = record.get("expected_tool_args")
    actual_args = record.get("actual_tool_args")
    tool_args_correct = expected_args is None or expected_args == actual_args
    pre_rerank = list(record.get("pre_rerank_chunk_ids", []))
    post_rerank = list(record.get("reranked_chunk_ids", []))
    relevant_chunks = set(
        record.get("relevant_chunk_ids", record.get("relevant_child_ids", []))
    )
    before_rank = next(
        (index for index, item in enumerate(pre_rerank, 1) if item in relevant_chunks),
        None,
    )
    after_rank = next(
        (index for index, item in enumerate(post_rerank, 1) if item in relevant_chunks),
        None,
    )
    reranker_promoted = (
        after_rank is not None and (before_rank is None or after_rank < before_rank)
    )
    safety_passed = bool(record.get("safety_passed", True)) and not (
        should_refuse and not refused
    )
    success = safety_passed and (
        (should_refuse and refused)
        or ((not should_refuse) and answer_correct and grounded)
    )
    return {
        **retrieval,
        **citation,
        "answer_correct": float(answer_correct),
        "faithfulness": float(grounded),
        "should_refuse": should_refuse,
        "refused": refused,
        "refusal_correct": float(should_refuse == refused),
        "rewrite_correct": float(rewrite_correct),
        "route_correct": float(route_correct),
        "tool_selection_correct": float(tool_selection_correct),
        "tool_args_correct": float(tool_args_correct),
        "reranker_promoted_gold": float(reranker_promoted),
        "loop_within_limit": float(loop_count <= max_loops),
        "safety_passed": safety_passed,
        "success": success,
        "latency_ms": float(record.get("latency_ms", record.get("total_latency_ms", 0.0))),
        "retrieval_latency_ms": float(record.get("retrieval_latency_ms", 0.0)),
        "reranker_latency_ms": float(record.get("reranker_latency_ms", 0.0)),
        "llm_latency_ms": float(record.get("llm_latency_ms", 0.0)),
        "prompt_tokens": int(record.get("prompt_tokens", 0)),
        "completion_tokens": int(record.get("completion_tokens", 0)),
        "retry_count": int(record.get("retry_count", max(0, loop_count - 1))),
        "error": bool(record.get("error")),
        "timeout": bool(record.get("timeout")),
    }


def evaluate_records(records: list[dict[str, Any]], k: int = 5) -> dict[str, Any]:
    scored = [evaluate_record(item, k) for item in records]
    for source, score in zip(records, scored, strict=True):
        score["case_id"] = str(source.get("case_id", source.get("id", "")))
        score["run_id"] = str(source.get("run_id", ""))
        score["tags"] = list(source.get("tags", []))
    numeric = (
        f"hit@{k}",
        f"recall@{k}",
        "mrr",
        "ndcg",
        "citation_precision",
        "citation_recall",
        "answer_correct",
        "faithfulness",
        "refusal_correct",
        "rewrite_correct",
        "route_correct",
        "tool_selection_correct",
        "tool_args_correct",
        "reranker_promoted_gold",
        "loop_within_limit",
        "latency_ms",
        "retrieval_latency_ms",
        "reranker_latency_ms",
        "llm_latency_ms",
        "prompt_tokens",
        "completion_tokens",
        "retry_count",
    )
    summary = {
        name: safe_mean(
            float(row[name]) for row in scored if row.get(name) is not None
        )
        for name in numeric
    }
    summary.update(
        cases=len(scored),
        success_rate=safe_mean(float(row["success"]) for row in scored),
        error_rate=safe_mean(float(row["error"]) for row in scored),
        timeout_rate=safe_mean(float(row["timeout"]) for row in scored),
        p95_latency_ms=percentile((float(row["latency_ms"]) for row in scored), 0.95),
        total_tokens=sum(
            int(row["prompt_tokens"]) + int(row["completion_tokens"])
            for row in scored
        ),
    )
    true_refusals = sum(
        bool(row["should_refuse"] and row["refused"]) for row in scored
    )
    predicted_refusals = sum(bool(row["refused"]) for row in scored)
    required_refusals = sum(bool(row["should_refuse"]) for row in scored)
    summary["refusal_precision"] = round(
        true_refusals / max(1, predicted_refusals), 6
    )
    summary["refusal_recall"] = round(true_refusals / max(1, required_refusals), 6)

    by_tag: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source, score in zip(records, scored, strict=True):
        for tag in source.get("tags", [source.get("category", "untagged")]):
            by_tag[str(tag)].append(score)

    repeated: dict[str, list[bool]] = defaultdict(list)
    for source, score in zip(records, scored, strict=True):
        case_id = str(source.get("case_id", source.get("id", "")))
        repeated[case_id].append(bool(score["success"]))
    reliability = {
        "cases_with_repeats": sum(len(values) > 1 for values in repeated.values()),
        "mean_case_success_rate": safe_mean(
            safe_mean(float(value) for value in values) for values in repeated.values()
        ),
        "pass_all_rate": safe_mean(
            float(all(values)) for values in repeated.values()
        ),
        "pass_at_least_once_rate": safe_mean(
            float(any(values)) for values in repeated.values()
        ),
    }
    return {
        "summary": summary,
        "by_tag": {
            tag: {
                "cases": len(values),
                "success_rate": safe_mean(float(row["success"]) for row in values),
                f"recall@{k}": safe_mean(
                    float(row[f"recall@{k}"])
                    for row in values
                    if row.get(f"recall@{k}") is not None
                ),
                "faithfulness": safe_mean(float(row["faithfulness"]) for row in values),
                "latency_ms": safe_mean(float(row["latency_ms"]) for row in values),
            }
            for tag, values in sorted(by_tag.items())
        },
        "reliability": reliability,
        "details": scored,
    }
