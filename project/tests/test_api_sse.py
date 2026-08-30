import pytest

from api.main import _sse_response


class FakeRag:
    def stream(self, question, thread_id):
        assert question == "测试问题"
        assert thread_id == "thread-1"
        yield {"event": "token", "content": "回答"}


@pytest.mark.asyncio
async def test_sse_response_uses_explicit_question():
    response = _sse_response(FakeRag(), "测试问题", "thread-1")
    body = b""
    async for chunk in response.body_iterator:
        body += chunk.encode() if isinstance(chunk, str) else chunk

    assert '"event": "token"'.encode() in body
    assert "回答".encode() in body
