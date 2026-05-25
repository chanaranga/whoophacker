from __future__ import annotations

from datetime import datetime
from typing import Optional, TypedDict

from langgraph.graph import StateGraph, END
from sqlalchemy.ext.asyncio import AsyncSession

from agent.nodes import (
    parse_intent_node,
    record_sleep_start_node,
    run_sleep_analysis_node,
    query_metrics_node,
    health_snapshot_node,
)


class HealthAgentState(TypedDict):
    user_phone: str
    user_message: str
    intent: str
    sleep_start: Optional[datetime]
    db: AsyncSession   # passed through but not serialised


def _route(state: HealthAgentState) -> str:
    intent = state.get("intent", "unknown")
    if intent == "sleep_start":
        return "record_sleep_start"
    if intent == "sleep_end":
        return "run_sleep_analysis"
    if intent == "health_snapshot":
        return "health_snapshot"
    if intent in ("query_hr", "query_hrv", "query_spo2"):
        return "query_metrics"
    return END


def build_graph() -> StateGraph:
    g = StateGraph(HealthAgentState)

    g.add_node("parse_intent", parse_intent_node)
    g.add_node("record_sleep_start", record_sleep_start_node)
    g.add_node("run_sleep_analysis", run_sleep_analysis_node)
    g.add_node("query_metrics", query_metrics_node)
    g.add_node("health_snapshot", health_snapshot_node)

    g.set_entry_point("parse_intent")
    g.add_conditional_edges("parse_intent", _route)

    for node in ("record_sleep_start", "run_sleep_analysis", "query_metrics", "health_snapshot"):
        g.add_edge(node, END)

    return g.compile()


_graph = build_graph()


async def run_agent(user_phone: str, message: str, db: AsyncSession) -> None:
    await _graph.ainvoke(
        {
            "user_phone": user_phone,
            "user_message": message,
            "intent": "",
            "sleep_start": None,
            "db": db,
        }
    )
