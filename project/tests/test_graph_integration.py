from langchain_core.messages import AIMessage, HumanMessage

from rag_agent.graph import create_agent_graph
from retrieval.milvus_store import SearchHit


class GraphSettings:
    relevance_threshold = 0.2
    max_retrieval_attempts = 2
    context_token_budget = 500


class FakeRetriever:
    def retrieve(self, query, mode):
        return [
            SearchHit(
                id="child-1",
                score=0.8,
                text="住宿费超标需说明原因",
                doc_id="a" * 24,
                parent_id=f"{'a' * 24}-p0",
                source="差旅制度.docx",
                heading="住宿标准",
                locator="section:2",
                retrieval_method="hybrid_rrf_bge_rerank",
                rerank_score=0.9,
            )
        ]


class FakeParentStore:
    def get(self, parent_id):
        return {
            "parent_id": parent_id,
            "doc_id": "a" * 24,
            "source": "差旅制度.docx",
            "heading": "住宿标准",
            "locator": "section:2",
            "text": "住宿费超标时，员工必须说明原因并由部门负责人审批。",
        }


class FakeLLM:
    def __init__(self, grounded=True):
        self.grounded = grounded

    def invoke(self, messages):
        system = str(messages[0].content)
        if "查询规划器" in system:
            return AIMessage(
                content=(
                    '{"intent":"knowledge","rewritten_query":"住宿费 超标 审批",'
                    '"needs_clarification":false,"clarification_question":"",'
                    '"tool_name":"none","identifier":""}'
                )
            )
        if "替代查询" in system:
            return AIMessage(content='{"query":"差旅 住宿 超标准 原因 部门负责人 审批"}')
        if "事实一致性检查器" in system:
            value = "true" if self.grounded else "false"
            claims = "[]" if self.grounded else '["审批要求未确认"]'
            return AIMessage(content=f'{{"grounded":{value},"unsupported_claims":{claims}}}')
        if "严格基于证据" in system:
            return AIMessage(
                content="住宿费超标时需要说明原因并经部门负责人审批 [来源：差旅制度.docx，section:2]。"
            )
        raise AssertionError(f"unexpected prompt: {system}")


def build_graph(grounded=True):
    return create_agent_graph(
        llm=FakeLLM(grounded),
        retriever=FakeRetriever(),
        tools={},
        settings=GraphSettings(),
        parent_store=FakeParentStore(),
    )


def test_graph_expands_parent_and_finishes_grounded_answer():
    result = build_graph().invoke(
        {"messages": [HumanMessage(content="住宿费超标怎么办？")]},
        config={"configurable": {"thread_id": "grounded"}},
    )

    assert result["grounded"] is True
    assert result["retrieval_attempts"] == 1
    assert "员工必须说明原因" in result["evidence"]
    assert result["context_docs"][0]["child_text"] == "住宿费超标需说明原因"


def test_graph_fact_check_failure_retries_then_refuses():
    result = build_graph(grounded=False).invoke(
        {"messages": [HumanMessage(content="住宿费超标怎么办？")]},
        config={"configurable": {"thread_id": "not-grounded"}},
    )

    assert result["retrieval_attempts"] == 2
    assert "没有足够依据" in result["answer"]
