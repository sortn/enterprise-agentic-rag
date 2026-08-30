"""Application service container used by FastAPI, Gradio and evaluation scripts."""

from __future__ import annotations

import threading
import uuid
from typing import Any, Iterator

from langchain_core.messages import HumanMessage

from config import Settings, get_settings
from db.parent_store_manager import ParentStoreManager
from ingestion.pipeline import IngestionPipeline
from rag_agent.graph import create_agent_graph
from rag_agent.tools import create_enterprise_tools
from retrieval.hybrid_retriever import HybridRetriever
from retrieval.milvus_store import MilvusStore
from services.business_api import MockBusinessService
from services.model_clients import SiliconFlowEmbeddings, SiliconFlowReranker, build_chat_model
from services.structured_data import StructuredDataService


class RAGSystem:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._lock = threading.Lock()
        self.initialized = False
        self.store: MilvusStore | None = None
        self.retriever: HybridRetriever | None = None
        self.ingestion: IngestionPipeline | None = None
        self.parent_store: ParentStoreManager | None = None
        self.structured_service: StructuredDataService | None = None
        self.business_service: MockBusinessService | None = None
        self.agent_graph = None

    def initialize(self) -> "RAGSystem":
        if self.initialized:
            return self
        with self._lock:
            if self.initialized:
                return self
            embeddings = SiliconFlowEmbeddings(self.settings)
            reranker = SiliconFlowReranker(self.settings)
            self.store = MilvusStore(self.settings)
            self.store.ensure_collection()
            self.parent_store = ParentStoreManager(self.settings)
            self.retriever = HybridRetriever(self.store, embeddings, reranker, self.settings)
            self.ingestion = IngestionPipeline(
                self.store,
                embeddings,
                self.settings,
                parent_store=self.parent_store,
            )
            document_ids = {item["doc_id"] for item in self.store.list_documents()}
            self.ingestion.backfill_parent_store(document_ids)
            self.structured_service = StructuredDataService(self.settings)
            self.business_service = MockBusinessService(self.settings)
            tools = create_enterprise_tools(self.structured_service, self.business_service)
            self.agent_graph = create_agent_graph(
                llm=build_chat_model(self.settings),
                retriever=self.retriever,
                tools=tools,
                settings=self.settings,
                parent_store=self.parent_store,
            )
            self.initialized = True
        return self

    @staticmethod
    def new_thread_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def _graph_config(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}, "recursion_limit": 20}

    def chat(self, question: str, thread_id: str) -> dict[str, Any]:
        self.initialize()
        result = self.agent_graph.invoke(
            {"messages": [HumanMessage(content=question)], "question": question},
            config=self._graph_config(thread_id),
        )
        return {
            "thread_id": thread_id,
            "answer": result.get("answer", ""),
            "intent": result.get("intent", ""),
            "rewritten_query": result.get("rewritten_query", ""),
            "citations": result.get("citations", []),
            "grounded": bool(result.get("grounded", False)),
            "retrieval_attempts": int(result.get("retrieval_attempts", 0)),
        }

    def stream(self, question: str, thread_id: str) -> Iterator[dict[str, Any]]:
        self.initialize()
        config = self._graph_config(thread_id)
        yield {"event": "start", "thread_id": thread_id}
        for update in self.agent_graph.stream(
            {"messages": [HumanMessage(content=question)], "question": question},
            config=config,
            stream_mode="updates",
        ):
            for node_name, values in update.items():
                event: dict[str, Any] = {"event": "node", "node": node_name}
                if node_name == "analyze_query":
                    event.update(
                        intent=values.get("intent"),
                        rewritten_query=values.get("rewritten_query"),
                    )
                elif node_name == "retrieve":
                    event.update(
                        retrieved=len(values.get("documents", [])),
                        retrieval_attempts=values.get("retrieval_attempts", 0),
                    )
                elif node_name == "fact_check":
                    event.update(grounded=values.get("grounded", False))
                yield event

        snapshot = self.agent_graph.get_state(config).values
        answer = str(snapshot.get("answer", ""))
        for start in range(0, len(answer), self.settings.sse_chunk_size):
            yield {
                "event": "token",
                "content": answer[start : start + self.settings.sse_chunk_size],
            }
        yield {
            "event": "final",
            "thread_id": thread_id,
            "answer": answer,
            "intent": snapshot.get("intent", ""),
            "rewritten_query": snapshot.get("rewritten_query", ""),
            "citations": snapshot.get("citations", []),
            "grounded": bool(snapshot.get("grounded", False)),
            "retrieval_attempts": int(snapshot.get("retrieval_attempts", 0)),
        }

    def delete_document(self, doc_id: str) -> None:
        self.initialize()
        self.store.delete_document(doc_id)
        self.parent_store.delete_document(doc_id)
        (self.settings.parsed_dir / f"{doc_id}.json").unlink(missing_ok=True)

    def reset_thread(self, thread_id: str) -> None:
        if self.agent_graph and self.agent_graph.checkpointer:
            self.agent_graph.checkpointer.delete_thread(thread_id)
