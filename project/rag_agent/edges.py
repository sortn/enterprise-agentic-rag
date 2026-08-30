from __future__ import annotations

from config import Settings, get_settings
from .graph_state import State


def route_after_analysis(state: State) -> str:
    if state.get("plan", {}).get("needs_clarification"):
        return "clarification"
    return {
        "knowledge": "retrieve",
        "structured_data": "run_tool",
        "business_api": "run_tool",
        "chitchat": "chitchat",
    }.get(state.get("intent", "knowledge"), "retrieve")


def route_after_retrieval(state: State, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    documents = state.get("documents", [])
    if documents:
        top_score = documents[0].get("rerank_score")
        if top_score is None or float(top_score) >= settings.relevance_threshold:
            return "build_context"
    if state.get("retrieval_attempts", 0) < settings.max_retrieval_attempts:
        return "rewrite_search"
    return "refuse"


def route_after_tool(state: State) -> str:
    return "generate_answer" if state.get("evidence") else "refuse"


def route_after_fact_check(state: State, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    if state.get("grounded"):
        return "finish"
    if state.get("retrieval_attempts", 0) < settings.max_retrieval_attempts:
        return "rewrite_search"
    return "refuse"
