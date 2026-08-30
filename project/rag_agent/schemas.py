from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class QueryPlan(BaseModel):
    intent: Literal["knowledge", "structured_data", "business_api", "chitchat"]
    rewritten_query: str = Field(min_length=1, max_length=500)
    needs_clarification: bool = False
    clarification_question: str = ""
    tool_name: Literal["none", "product", "department", "inventory", "service_status"] = "none"
    identifier: str = Field(default="", max_length=100)


class SearchRewrite(BaseModel):
    query: str = Field(min_length=1, max_length=500)


class FaithfulnessCheck(BaseModel):
    grounded: bool
    unsupported_claims: list[str] = Field(default_factory=list)


class StructuredQueryInput(BaseModel):
    query_type: Literal["product", "department"]
    identifier: str = Field(min_length=1, max_length=100)


class BusinessQueryInput(BaseModel):
    resource: Literal["inventory", "service_status"]
    identifier: str = Field(min_length=1, max_length=100)
