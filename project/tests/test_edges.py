from rag_agent.edges import route_after_analysis, route_after_fact_check, route_after_retrieval


class EdgeSettings:
    relevance_threshold = 0.2
    max_retrieval_attempts = 2


def test_routes_enterprise_tools():
    assert route_after_analysis({"intent": "structured_data", "plan": {}}) == "run_tool"
    assert route_after_analysis({"intent": "business_api", "plan": {}}) == "run_tool"


def test_low_confidence_retries_then_refuses():
    state = {"documents": [{"rerank_score": 0.1}], "retrieval_attempts": 1}
    assert route_after_retrieval(state, EdgeSettings()) == "rewrite_search"
    state["retrieval_attempts"] = 2
    assert route_after_retrieval(state, EdgeSettings()) == "refuse"


def test_fact_check_route():
    assert route_after_fact_check({"grounded": True}) == "finish"
    assert route_after_fact_check(
        {"grounded": False, "retrieval_attempts": 1}, EdgeSettings()
    ) == "rewrite_search"
    assert route_after_fact_check(
        {"grounded": False, "retrieval_attempts": 2}, EdgeSettings()
    ) == "refuse"


def test_relevant_retrieval_builds_parent_context():
    state = {"documents": [{"rerank_score": 0.9}], "retrieval_attempts": 1}
    assert route_after_retrieval(state, EdgeSettings()) == "build_context"
