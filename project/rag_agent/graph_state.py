from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class State(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    question: str
    intent: str
    rewritten_query: str
    plan: dict[str, Any]
    retrieval_attempts: int
    retrieve_chunks: list[dict[str, Any]]
    documents: list[dict[str, Any]]
    context_docs: list[dict[str, Any]]
    tool_result: str
    evidence: str
    answer: str
    citations: list[dict[str, str]]
    grounded: bool
    refused: bool
    unsupported_claims: list[str]
    last_error: str


# Kept as an alias so imports from the upstream tutorial fail gracefully while
# the new graph uses a single explicit state object.
AgentState = State
