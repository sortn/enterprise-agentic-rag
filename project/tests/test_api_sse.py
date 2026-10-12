import pytest

from api.application import _sse_payload_response


@pytest.mark.asyncio
async def test_sse_response_contains_start_tokens_and_final_result():
    response = _sse_payload_response(
        {
            "thread_id": "thread-1",
            "answer": "测试回答",
            "route": "retrieval",
        }
    )
    body = b""
    async for chunk in response.body_iterator:
        body += chunk.encode() if isinstance(chunk, str) else chunk

    assert '"event": "start"'.encode() in body
    assert '"event": "token"'.encode() in body
    assert '"event": "final"'.encode() in body
    assert "测试回答".encode() in body
