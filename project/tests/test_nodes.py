import json

from rag_agent.nodes import AgentNodes
from rag_agent.schemas import QueryPlan


def test_business_tool_answer_is_grounded_without_generation():
    state = {
        "intent": "business_api",
        "tool_result": json.dumps(
            {
                "found": True,
                "resource": "inventory",
                "identifier": "NX-MEET-PRO",
                "available": 24,
                "reserved": 6,
                "warehouse": "华东仓",
                "updated_at": "2026-08-01T09:00:00+08:00",
            },
            ensure_ascii=False,
        ),
    }
    answer = AgentNodes._format_tool_answer(state)
    assert "24" in answer
    assert "华东仓" in answer
    assert "[来源：业务接口]" in answer


def test_refusal_is_not_reported_as_grounded():
    result = AgentNodes(None, None, {}).refuse({"retrieval_attempts": 2})

    assert result["refused"] is True
    assert result["grounded"] is False


class ContextSettings:
    context_token_budget = 100


class FakeParentStore:
    def get(self, parent_id):
        return {
            "parent_id": parent_id,
            "doc_id": "a" * 24,
            "source": "制度.txt",
            "heading": "报销制度",
            "locator": "section:1",
            "text": "这是父块完整正文，包含比命中子块更多的上下文。",
        }


def test_context_build_expands_and_deduplicates_parents():
    nodes = AgentNodes(None, None, {}, ContextSettings(), FakeParentStore())
    child = {
        "id": "c1",
        "parent_id": f"{'a' * 24}-p0",
        "source": "制度.txt",
        "text": "命中子块",
        "rerank_score": 0.9,
    }
    result = nodes.build_context({"retrieve_chunks": [child, {**child, "id": "c2"}]})

    assert len(result["context_docs"]) == 1
    assert result["context_docs"][0]["text"].startswith("这是父块完整正文")
    assert result["context_docs"][0]["child_text"] == "命中子块"


def test_plan_policy_routes_document_amount_question_back_to_knowledge():
    plan = QueryPlan(
        intent="structured_data",
        rewritten_query="西南区备用金核销 提前 工作日",
        needs_clarification=True,
        clarification_question="请补充产品",
        tool_name="product",
        identifier="西南区备用金核销",
    )

    fixed = AgentNodes._enforce_plan_policy(
        "办理西南区备用金核销最晚需提前几个工作日提交材料？",
        plan,
    )

    assert fixed.intent == "knowledge"
    assert fixed.tool_name == "none"
    assert fixed.identifier == ""
    assert fixed.needs_clarification is False


def test_plan_policy_preserves_supported_tool_queries_and_real_ambiguity():
    product = QueryPlan(
        intent="structured_data",
        rewritten_query="NX-MEET-PRO 价格",
        tool_name="product",
        identifier="NX-MEET-PRO",
    )
    ambiguous = QueryPlan(
        intent="knowledge",
        rewritten_query="该产品保修期",
        needs_clarification=True,
        clarification_question="请问是哪款产品？",
    )

    assert AgentNodes._enforce_plan_policy("NX-MEET-PRO 的标价是多少？", product) == product
    assert AgentNodes._enforce_plan_policy("该产品的保修期呢？", ambiguous) == ambiguous
