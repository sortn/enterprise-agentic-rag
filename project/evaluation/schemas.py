from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="allow")

    case_id: str
    query: str = Field(min_length=1)
    reference_answer: str = ""
    relevant_document_ids: list[str] = Field(default_factory=list)
    relevant_chunk_ids: list[str] = Field(default_factory=list)
    relevant_sources: list[str] = Field(default_factory=list)
    should_refuse: bool = False
    expected_rewrite: bool | None = None
    expected_route: str | None = None
    expected_tools: list[str] = Field(default_factory=list)
    expected_tool_args: dict[str, Any] | None = None
    difficulty: str = "unknown"
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def accept_existing_benchmark_names(cls, value: Any):
        if not isinstance(value, dict):
            return value
        data = dict(value)
        data.setdefault("case_id", data.get("id", "unknown"))
        data.setdefault("query", data.get("question", ""))
        data.setdefault("relevant_chunk_ids", data.get("relevant_child_ids", []))
        source = data.get("relevant_source")
        if source and not data.get("relevant_sources"):
            data["relevant_sources"] = [source]
        if "should_refuse" not in data and "answerable" in data:
            data["should_refuse"] = not bool(data["answerable"])
        return data


class AgentTrace(EvaluationCase):
    run_id: str = ""
    route: str = ""
    rewritten_query: str = ""
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    pre_rerank_chunk_ids: list[str] = Field(default_factory=list)
    reranked_chunk_ids: list[str] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    answer: str = ""
    answer_correct: bool = False
    grounded: bool = False
    refused: bool = False
    actual_tools: list[str] = Field(default_factory=list)
    actual_tool_args: dict[str, Any] | None = None
    loop_count: int = 0
    max_loops: int = 2
    latency_ms: float = 0.0
    retrieval_latency_ms: float = 0.0
    reranker_latency_ms: float = 0.0
    llm_latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    retry_count: int = 0
    final_status: Literal["success", "refused", "failed", "timeout"] = "success"
    error: str | bool = ""
    timeout: bool = False
