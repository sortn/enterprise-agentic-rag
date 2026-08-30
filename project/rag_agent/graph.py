"""Explicit LangGraph workflow matching the nodes described in the resume."""

from __future__ import annotations

from functools import partial

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from config import Settings, get_settings
from .edges import (
    route_after_analysis,
    route_after_fact_check,
    route_after_retrieval,
    route_after_tool,
)
from .graph_state import State
from .nodes import AgentNodes


def create_agent_graph(
    llm,
    retriever,
    tools,
    settings: Settings | None = None,
    checkpointer=None,
    parent_store=None,
):
    settings = settings or get_settings()
    nodes = AgentNodes(
        llm=llm,
        retriever=retriever,
        tools=tools,
        settings=settings,
        parent_store=parent_store,
    )
    graph = StateGraph(State)

    graph.add_node("analyze_query", nodes.analyze_query)
    graph.add_node("clarification", nodes.clarification)
    graph.add_node("chitchat", nodes.chitchat)
    graph.add_node("retrieve", nodes.retrieve)
    graph.add_node("build_context", nodes.build_context)
    graph.add_node("rewrite_search", nodes.rewrite_search)
    graph.add_node("run_tool", nodes.run_tool)
    graph.add_node("refuse", nodes.refuse)
    graph.add_node("generate_answer", nodes.generate_answer)
    graph.add_node("fact_check", nodes.fact_check)
    graph.add_node("finish", nodes.finish)
    graph.add_node("revise_answer", nodes.revise_answer)

    graph.add_edge(START, "analyze_query")
    graph.add_conditional_edges("analyze_query", route_after_analysis)
    graph.add_edge("clarification", END)
    graph.add_edge("chitchat", END)
    graph.add_conditional_edges(
        "retrieve",
        partial(route_after_retrieval, settings=settings),
    )
    graph.add_edge("rewrite_search", "retrieve")
    graph.add_edge("build_context", "generate_answer")
    graph.add_conditional_edges("run_tool", route_after_tool)
    graph.add_edge("refuse", END)
    graph.add_edge("generate_answer", "fact_check")
    graph.add_conditional_edges(
        "fact_check",
        partial(route_after_fact_check, settings=settings),
    )
    graph.add_edge("finish", END)
    graph.add_edge("revise_answer", END)

    return graph.compile(checkpointer=checkpointer or InMemorySaver())
