import pytest
from pydantic import ValidationError

from api.schemas import ChatRequest


def test_chat_question_validation():
    with pytest.raises(ValidationError):
        ChatRequest(question="")
    assert ChatRequest(question="怎么报销？").question == "怎么报销？"
