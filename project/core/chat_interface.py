"""Thin compatibility wrapper; the real streaming boundary is FastAPI SSE."""

from __future__ import annotations

from .rag_system import RAGSystem


class ChatInterface:
    def __init__(self, rag_system: RAGSystem, thread_id: str | None = None):
        self.rag_system = rag_system
        self.thread_id = thread_id or rag_system.new_thread_id()

    def chat(self, message, history=None):
        for event in self.rag_system.stream(message, self.thread_id):
            if event["event"] == "final":
                yield event["answer"]

    def clear_session(self):
        self.rag_system.reset_thread(self.thread_id)
        self.thread_id = self.rag_system.new_thread_id()
