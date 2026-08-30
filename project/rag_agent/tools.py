"""Pydantic-validated enterprise tools exposed to the LangGraph workflow."""

from __future__ import annotations

import json

from langchain_core.tools import StructuredTool

from services.business_api import MockBusinessService
from services.structured_data import StructuredDataService
from .schemas import BusinessQueryInput, StructuredQueryInput


def create_enterprise_tools(
    structured_service: StructuredDataService,
    business_service: MockBusinessService,
) -> dict[str, StructuredTool]:
    def query_structured_data(query_type: str, identifier: str) -> str:
        result = structured_service.query(query_type=query_type, identifier=identifier)
        return json.dumps(result, ensure_ascii=False)

    def call_business_api(resource: str, identifier: str) -> str:
        result = business_service.lookup(resource=resource, identifier=identifier)
        return json.dumps(result, ensure_ascii=False)

    return {
        "structured_data": StructuredTool.from_function(
            func=query_structured_data,
            name="query_structured_database",
            description="查询产品价格/质保期或企业部门联系方式。禁止执行任意 SQL。",
            args_schema=StructuredQueryInput,
        ),
        "business_api": StructuredTool.from_function(
            func=call_business_api,
            name="call_business_api",
            description="查询产品实时库存或在线服务运行状态。",
            args_schema=BusinessQueryInput,
        ),
    }
