from types import SimpleNamespace

from core.rag_system import RAGSystem


class StreamSettings:
    sse_chunk_size = 2


class FakeGraph:
    def stream(self, state, config, stream_mode):
        yield {"analyze_query": {"intent": "knowledge", "rewritten_query": "制度"}}

    def get_state(self, config):
        return SimpleNamespace(
            values={
                "answer": "完整答案",
                "intent": "knowledge",
                "rewritten_query": "制度",
                "citations": [],
                "grounded": True,
                "retrieval_attempts": 1,
            }
        )


def test_stream_emits_verified_answer_chunks():
    system = RAGSystem(StreamSettings())
    system.initialized = True
    system.agent_graph = FakeGraph()

    events = list(system.stream("问题", "thread-1"))
    assert "".join(event["content"] for event in events if event["event"] == "token") == "完整答案"
    assert events[-1]["event"] == "final"
