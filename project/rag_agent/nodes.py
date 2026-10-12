"""LangGraph nodes for planning, retrieval, tools, generation and verification."""

from __future__ import annotations

import json
import logging
import math
import re
import time
import threading
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from config import Settings, get_settings
from retrieval.hybrid_retriever import HybridRetriever
from .graph_state import State
from .prompts import (
    ANSWER_PROMPT,
    FACT_CHECK_PROMPT,
    QUERY_PLAN_PROMPT,
    SEARCH_REWRITE_PROMPT,
)
from .schemas import FaithfulnessCheck, QueryPlan, SearchRewrite

logger = logging.getLogger(__name__)


class AgentNodes:
    def __init__(
        self,
        llm,
        retriever: HybridRetriever,
        tools: dict[str, Any],
        settings: Settings | None = None,
        parent_store=None,
    ):
        self.llm = llm
        self.retriever = retriever
        self.tools = tools
        self.settings = settings or get_settings()
        self.parent_store = parent_store
        self._local = threading.local()

    def analyze_query(self, state: State) -> dict[str, Any]:
        self._local.prompt_tokens = 0
        self._local.completion_tokens = 0
        question = self._current_question(state)
        history = self._conversation_context(state.get("messages", []))
        started = time.perf_counter()
        plan = self._invoke_structured(
            QueryPlan,
            [
                SystemMessage(content=QUERY_PLAN_PROMPT),
                HumanMessage(content=f"最近对话：\n{history or '(无)'}\n\n当前问题：\n{question}"),
            ],
        )
        llm_latency_ms = round((time.perf_counter() - started) * 1000, 3)
        plan = self._enforce_plan_policy(question, plan)
        return {
            "question": question,
            "intent": plan.intent,
            "rewritten_query": (
                plan.rewritten_query
                if getattr(self.settings, "query_rewrite_enabled", True)
                else question
            ),
            "plan": plan.model_dump(),
            "retrieval_attempts": 0,
            "retrieve_chunks": [],
            "documents": [],
            "context_docs": [],
            "tool_result": "",
            "evidence": "",
            "answer": "",
            "citations": [],
            "grounded": False,
            "refused": False,
            "unsupported_claims": [],
            "last_error": "",
            "retrieval_metrics": {},
            "llm_latency_ms": llm_latency_ms,
            **self._token_usage(),
        }

    @staticmethod
    def _enforce_plan_policy(question: str, plan: QueryPlan) -> QueryPlan:
        """Clamp probabilistic planner output to the supported tool boundary."""
        updates: dict[str, Any] = {}
        product_cues = ("价格", "售价", "标价", "多少钱", "质保", "保修期", "质保期")
        department_cues = ("联系人", "联系电话", "联系方式", "电话", "热线")
        inventory_cues = ("实时库存", "当前库存", "可用库存", "还有多少件")
        service_cues = ("服务状态", "是否在线", "运行状态", "接口延迟", "服务延迟")

        if plan.intent == "structured_data":
            allowed = (
                plan.tool_name == "product" and any(cue in question for cue in product_cues)
            ) or (
                plan.tool_name == "department" and any(cue in question for cue in department_cues)
            )
            if not allowed:
                updates.update(intent="knowledge", tool_name="none", identifier="")
        elif plan.intent == "business_api":
            allowed = (
                plan.tool_name == "inventory" and any(cue in question for cue in inventory_cues)
            ) or (
                plan.tool_name == "service_status" and any(cue in question for cue in service_cues)
            )
            if not allowed:
                updates.update(intent="knowledge", tool_name="none", identifier="")
        elif plan.intent == "chitchat" and not AgentNodes._is_explicit_chitchat(question):
            # An unfamiliar name may be the subject of an uploaded document. Only
            # keep deterministic social phrases in the no-retrieval chitchat path.
            updates.update(
                intent="knowledge",
                tool_name="none",
                identifier="",
                needs_clarification=False,
                clarification_question="",
            )

        ambiguous_reference = re.search(r"(?:它|那个|上一个|上一款|这款|该产品|该服务)", question)
        if plan.needs_clarification and not ambiguous_reference:
            updates.update(needs_clarification=False, clarification_question="")
        return plan.model_copy(update=updates) if updates else plan

    @staticmethod
    def _is_explicit_chitchat(question: str) -> bool:
        normalized = re.sub(r"[\s，。！？!?、,.~～]+", "", question).lower()
        return normalized in {
            "你好",
            "您好",
            "嗨",
            "哈喽",
            "hello",
            "hi",
            "hey",
            "早上好",
            "下午好",
            "晚上好",
            "谢谢",
            "多谢",
            "再见",
            "拜拜",
            "你是谁",
            "你能做什么",
            "你会什么",
            "介绍一下你自己",
        }

    def clarification(self, state: State) -> dict[str, Any]:
        message = state.get("plan", {}).get("clarification_question") or "请补充你所指的具体制度、产品或服务名称。"
        return {"answer": message, "messages": [AIMessage(content=message)]}

    def chitchat(self, state: State) -> dict[str, Any]:
        message = "你好，我可以查询企业制度、产品手册、产品价格、部门联系方式、实时库存和服务状态。你想了解哪一项？"
        return {
            "answer": message,
            "messages": [AIMessage(content=message)],
            "grounded": False,
            "refused": False,
        }

    def retrieve(self, state: State) -> dict[str, Any]:
        attempts = state.get("retrieval_attempts", 0) + 1
        try:
            user_context = state.get("user_context", {})
            scope = {}
            if user_context.get("tenant_id"):
                scope["tenant_id"] = user_context["tenant_id"]
            if user_context.get("knowledge_base_id"):
                scope["knowledge_base_id"] = user_context["knowledge_base_id"]
            hits = self.retriever.retrieve(
                state["rewritten_query"], mode="hybrid_rerank", **scope
            )
            documents = [hit.to_dict() for hit in hits]
            return {
                "retrieval_attempts": attempts,
                "retrieve_chunks": documents,
                "documents": documents,
                "context_docs": [],
                "last_error": "",
                "retrieval_metrics": self.retriever.last_trace()
                if hasattr(self.retriever, "last_trace")
                else {},
            }
        except Exception as exc:
            logger.exception("Knowledge retrieval failed")
            return {
                "retrieval_attempts": attempts,
                "retrieve_chunks": [],
                "documents": [],
                "context_docs": [],
                "last_error": f"{type(exc).__name__}: {exc}",
            }

    def rewrite_search(self, state: State) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            result = self._invoke_structured(
                SearchRewrite,
                [
                    SystemMessage(content=SEARCH_REWRITE_PROMPT),
                    HumanMessage(
                        content=f"原问题：{state['question']}\n初次查询：{state['rewritten_query']}"
                    ),
                ],
            )
            query = result.query
        except Exception as exc:
            logger.warning("Search rewrite failed, using original question: %s", exc)
            query = state["question"]
        return {
            "rewritten_query": query,
            "retrieve_chunks": [],
            "documents": [],
            "context_docs": [],
            "last_error": "",
            "llm_latency_ms": round(
                state.get("llm_latency_ms", 0.0)
                + (time.perf_counter() - started) * 1000,
                3,
            ),
            **self._token_usage(),
        }

    def build_context(self, state: State) -> dict[str, Any]:
        """Expand child hits to unique parents and enforce the context budget."""
        children = state.get("retrieve_chunks") or state.get("documents", [])
        selected: list[dict[str, Any]] = []
        seen: set[str] = set()
        used_tokens = 0

        for child in children:
            parent_id = str(child.get("parent_id", ""))
            if parent_id in seen:
                continue
            seen.add(parent_id)
            parent = None
            if (
                self.parent_store
                and parent_id
                and getattr(self.settings, "parent_expansion_enabled", True)
            ):
                try:
                    parent = self.parent_store.get(parent_id)
                except (OSError, ValueError, json.JSONDecodeError) as exc:
                    logger.warning("Failed to load parent %s: %s", parent_id, exc)

            context = dict(child)
            context["child_text"] = str(child.get("text", ""))
            if parent:
                context.update(parent)
                context["score"] = child.get("score", 0.0)
                context["rerank_score"] = child.get("rerank_score")
                context["retrieval_method"] = child.get("retrieval_method", "")

            token_count = self._estimate_tokens(str(context.get("text", "")))
            if selected and used_tokens + token_count > self.settings.context_token_budget:
                continue
            selected.append(context)
            used_tokens += token_count
            if used_tokens >= self.settings.context_token_budget:
                break

        return {"context_docs": selected}

    def run_tool(self, state: State) -> dict[str, Any]:
        plan = state.get("plan", {})
        intent = state.get("intent")
        try:
            if intent == "structured_data":
                result = self.tools["structured_data"].invoke(
                    {"query_type": plan.get("tool_name"), "identifier": plan.get("identifier", "")}
                )
                source = "结构化数据库"
            elif intent == "business_api":
                result = self.tools["business_api"].invoke(
                    {"resource": plan.get("tool_name"), "identifier": plan.get("identifier", "")}
                )
                source = "业务接口"
            else:
                raise ValueError(f"不支持的工具意图：{intent}")
            evidence = f"[来源：{source}]\n{result}"
            return {
                "tool_result": result,
                "evidence": evidence,
                "citations": [{"source": source, "locator": ""}],
                "last_error": "",
            }
        except Exception as exc:
            logger.exception("Enterprise tool call failed")
            return {
                "tool_result": "",
                "evidence": "",
                "last_error": f"{type(exc).__name__}: {exc}",
            }

    def refuse(self, state: State) -> dict[str, Any]:
        detail = "检索两次后仍未找到足够相关的文档证据"
        if state.get("last_error"):
            detail = "检索服务暂时不可用"
        message = f"当前知识库没有足够依据回答这个问题（{detail}）。请补充文档或换一个更具体的问法。"
        return {
            "answer": message,
            "messages": [AIMessage(content=message)],
            "grounded": False,
            "refused": True,
        }

    def generate_answer(self, state: State) -> dict[str, Any]:
        if state.get("tool_result"):
            answer = self._format_tool_answer(state)
            return {"answer": answer}
        evidence, citations = self._build_evidence(state)
        if not evidence:
            message = "当前数据源没有返回可用证据，暂时无法回答。"
            return {
                "answer": message,
                "messages": [AIMessage(content=message)],
                "grounded": False,
                "refused": True,
            }
        started = time.perf_counter()
        response = self.llm.invoke(
            [
                SystemMessage(content=ANSWER_PROMPT),
                HumanMessage(content=f"问题：\n{state['question']}\n\n证据：\n{evidence}"),
            ]
        )
        self._record_usage(response)
        answer = str(response.content).strip()
        return {
            "answer": answer,
            "evidence": evidence,
            "citations": citations,
            "llm_latency_ms": round(
                state.get("llm_latency_ms", 0.0)
                + (time.perf_counter() - started) * 1000,
                3,
            ),
            **self._token_usage(),
        }

    def fact_check(self, state: State) -> dict[str, Any]:
        # Tool answers are formatted directly from Pydantic-validated JSON, so
        # there is no generative claim to ask another LLM to judge.
        if state.get("tool_result"):
            return {"grounded": True, "unsupported_claims": []}
        try:
            started = time.perf_counter()
            result = self._invoke_structured(
                FaithfulnessCheck,
                [
                    SystemMessage(content=FACT_CHECK_PROMPT),
                    HumanMessage(content=f"证据：\n{state.get('evidence', '')}\n\n回答：\n{state.get('answer', '')}"),
                ],
            )
            return {
                "grounded": result.grounded,
                "unsupported_claims": result.unsupported_claims,
                "llm_latency_ms": round(
                    state.get("llm_latency_ms", 0.0)
                    + (time.perf_counter() - started) * 1000,
                    3,
                ),
                **self._token_usage(),
            }
        except Exception as exc:
            logger.warning("Fact check failed closed: %s", exc)
            return {"grounded": False, "unsupported_claims": ["事实校验服务未成功完成"]}

    def finish(self, state: State) -> dict[str, Any]:
        answer = state.get("answer", "")
        return {"messages": [AIMessage(content=answer)]}

    @staticmethod
    def _current_question(state: State) -> str:
        for message in reversed(state.get("messages", [])):
            if isinstance(message, HumanMessage):
                return str(message.content).strip()
        return state.get("question", "").strip()

    @staticmethod
    def _conversation_context(messages: list[Any]) -> str:
        lines = []
        for message in messages[-6:-1]:
            role = "用户" if isinstance(message, HumanMessage) else "助手"
            content = str(getattr(message, "content", "")).strip()
            if content:
                lines.append(f"{role}: {content[:500]}")
        return "\n".join(lines)

    def _invoke_structured(self, schema, messages: list[Any]):
        """Request JSON once and always validate it with Pydantic.

        SiliconFlow is OpenAI-compatible, but free models differ in native
        function-call support. Prompted JSON avoids a failed tool-call request
        plus retry while retaining strict structured-output validation.
        """
        json_instruction = HumanMessage(
            content=(
                "只输出一个 JSON 对象，不要 Markdown 代码块。JSON 必须符合这个 schema：\n"
                + json.dumps(schema.model_json_schema(), ensure_ascii=False)
            )
        )
        response = self.llm.invoke([*messages, json_instruction])
        self._record_usage(response)
        content = str(response.content).strip()
        match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if not match:
            raise ValueError(f"模型没有返回可解析的 {schema.__name__} JSON")
        return schema.model_validate_json(match.group(0))

    def _record_usage(self, response: Any) -> None:
        usage = getattr(response, "usage_metadata", None) or {}
        response_metadata = getattr(response, "response_metadata", None) or {}
        token_usage = response_metadata.get("token_usage", {})
        prompt = usage.get("input_tokens", token_usage.get("prompt_tokens", 0))
        completion = usage.get("output_tokens", token_usage.get("completion_tokens", 0))
        self._local.prompt_tokens = int(getattr(self._local, "prompt_tokens", 0)) + int(
            prompt or 0
        )
        self._local.completion_tokens = int(
            getattr(self._local, "completion_tokens", 0)
        ) + int(completion or 0)

    def _token_usage(self) -> dict[str, int]:
        return {
            "prompt_tokens": int(getattr(self._local, "prompt_tokens", 0)),
            "completion_tokens": int(getattr(self._local, "completion_tokens", 0)),
        }

    @staticmethod
    def _build_evidence(state: State) -> tuple[str, list[dict[str, str]]]:
        if state.get("evidence"):
            return state["evidence"], state.get("citations", [])
        blocks: list[str] = []
        citations: list[dict[str, str]] = []
        documents = state.get("context_docs") or state.get("documents", [])
        for index, document in enumerate(documents, start=1):
            source = str(document.get("source", "unknown"))
            locator = str(document.get("locator") or document.get("heading") or "未标注位置")
            blocks.append(
                f"[证据 {index}｜来源：{source}｜位置：{locator}]\n{document.get('text', '')}"
            )
            citation = {"source": source, "locator": locator}
            if citation not in citations:
                citations.append(citation)
        return "\n\n".join(blocks), citations

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Conservative tokenizer-free estimate for mixed Chinese/Latin text."""
        cjk = len(re.findall(r"[\u3400-\u9fff]", text))
        non_cjk = max(0, len(text) - cjk)
        return cjk + math.ceil(non_cjk / 4)

    @staticmethod
    def _format_tool_answer(state: State) -> str:
        data = json.loads(state["tool_result"])
        source = "结构化数据库" if state.get("intent") == "structured_data" else "业务接口"
        if not data.get("found"):
            return f"{source}中没有找到 `{data.get('identifier', '')}` 的记录 [来源：{source}]。"

        if data.get("query_type") == "product":
            return (
                f"{data['name']}（{data['sku']}）的含税标价为 {data['list_price']:.0f} 元，"
                f"标准质保期为 {data['warranty_years']} 年 [来源：结构化数据库]。"
            )
        if data.get("query_type") == "department":
            return (
                f"{data['name']}联系人为{data['contact']}，联系电话是 {data['hotline']} "
                "[来源：结构化数据库]。"
            )
        if data.get("resource") == "inventory":
            return (
                f"{data['identifier']} 当前可用库存为 {data['available']} 件，预留 {data['reserved']} 件，"
                f"仓库为{data['warehouse']}，更新时间 {data['updated_at']} [来源：业务接口]。"
            )
        if data.get("resource") == "service_status":
            return (
                f"服务 `{data['identifier']}` 当前状态为 {data['status']}，延迟 {data['latency_ms']} ms，"
                f"更新时间 {data['updated_at']} [来源：业务接口]。"
            )
        return f"{json.dumps(data, ensure_ascii=False)} [来源：{source}]"
