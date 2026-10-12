from evaluation.metrics import citation_metrics, evaluate_records, retrieval_metrics
from evaluation.regression import compare_reports


def test_deterministic_retrieval_and_citation_metrics():
    retrieval = retrieval_metrics(["x", "gold", "z"], {"gold"}, k=3)
    citations = citation_metrics(["docs/policy.pdf", "noise.txt"], ["policy.pdf"])

    assert retrieval["recall@3"] == 1.0
    assert retrieval["mrr"] == 0.5
    assert citations == {"citation_precision": 0.5, "citation_recall": 1.0}


def test_evaluation_reports_trajectory_reliability_and_regression():
    records = [
        {
            "case_id": "case-1",
            "query": "问题",
            "expected_rewrite": True,
            "rewritten_query": "改写问题",
            "expected_route": "knowledge",
            "route": "knowledge",
            "relevant_chunk_ids": ["gold"],
            "retrieved_chunk_ids": ["gold"],
            "relevant_sources": ["policy.pdf"],
            "citations": [{"source": "policy.pdf"}],
            "answer_correct": True,
            "grounded": True,
            "latency_ms": 100,
            "tags": ["rewrite"],
        },
        {
            "case_id": "case-1",
            "query": "问题",
            "expected_rewrite": True,
            "rewritten_query": "改写问题",
            "expected_route": "knowledge",
            "route": "knowledge",
            "relevant_chunk_ids": ["gold"],
            "retrieved_chunk_ids": ["gold"],
            "relevant_sources": ["policy.pdf"],
            "citations": [{"source": "policy.pdf"}],
            "answer_correct": True,
            "grounded": True,
            "latency_ms": 110,
            "tags": ["rewrite"],
        },
    ]
    report = evaluate_records(records, k=5)
    assert report["summary"]["success_rate"] == 1.0
    assert report["summary"]["rewrite_correct"] == 1.0
    assert report["reliability"]["cases_with_repeats"] == 1
    assert report["reliability"]["pass_all_rate"] == 1.0

    comparison = compare_reports(
        {"summary": {"success_rate": 0.9, "latency_ms": 100}},
        {"summary": {"success_rate": 0.8, "latency_ms": 130}},
    )
    assert comparison["passed"] is False
    assert comparison["regression_count"] == 2
