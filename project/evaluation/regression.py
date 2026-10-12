from __future__ import annotations

from typing import Any


LOWER_IS_BETTER = {
    "latency_ms",
    "retrieval_latency_ms",
    "reranker_latency_ms",
    "llm_latency_ms",
    "error_rate",
    "timeout_rate",
    "retry_count",
    "prompt_tokens",
    "completion_tokens",
    "estimated_cost",
}


def _flatten_numeric(value: Any, prefix: str = "") -> dict[str, float]:
    flattened = {}
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(_flatten_numeric(child, path))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        flattened[prefix] = float(value)
    return flattened


def compare_reports(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    quality_tolerance: float = 0.01,
    latency_tolerance: float = 0.10,
) -> dict[str, Any]:
    base = _flatten_numeric(baseline.get("summary", baseline))
    current = _flatten_numeric(candidate.get("summary", candidate))
    comparisons = []
    regressions = []
    for path in sorted(base.keys() & current.keys()):
        old = base[path]
        new = current[path]
        name = path.rsplit(".", 1)[-1]
        lower_is_better = name in LOWER_IS_BETTER
        tolerance = latency_tolerance if lower_is_better else quality_tolerance
        if lower_is_better:
            regressed = old > 0 and new > old * (1 + tolerance)
        else:
            regressed = new < old - tolerance
        row = {
            "metric": path,
            "baseline": old,
            "candidate": new,
            "delta": round(new - old, 6),
            "direction": "lower_is_better" if lower_is_better else "higher_is_better",
            "regressed": regressed,
        }
        comparisons.append(row)
        if regressed:
            regressions.append(row)
    baseline_cases = {
        str(item.get("case_id")): bool(item.get("success"))
        for item in baseline.get("details", [])
        if item.get("case_id")
    }
    candidate_cases = {
        str(item.get("case_id")): bool(item.get("success"))
        for item in candidate.get("details", [])
        if item.get("case_id")
    }
    regression_cases = [
        case_id
        for case_id in sorted(baseline_cases.keys() & candidate_cases.keys())
        if baseline_cases[case_id] and not candidate_cases[case_id]
    ]
    failure_cases = [
        case_id for case_id, passed in sorted(candidate_cases.items()) if not passed
    ]
    return {
        "passed": not regressions and not regression_cases,
        "regression_count": len(regressions),
        "regression_case_count": len(regression_cases),
        "regressions": regressions,
        "regression_cases": regression_cases,
        "failure_cases": failure_cases,
        "comparisons": comparisons,
    }
