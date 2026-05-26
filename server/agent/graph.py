from langgraph.graph import StateGraph, END
from sqlalchemy.ext.asyncio import AsyncSession

from agent.state import HealthAgentState
from agent.nodes import (
    parse_intent_node,
    record_sleep_start_node,
    run_sleep_analysis_node,
    query_metrics_node,
    health_snapshot_node,
    workout_start_node,
    workout_end_node,
    recovery_node,
    workout_advice_node,
)


def _route(state: HealthAgentState) -> str:
    intent = state.get("intent", "unknown")
    routes = {
        "sleep_start": "record_sleep_start",
        "sleep_end": "run_sleep_analysis",
        "health_snapshot": "health_snapshot",
        "workout_start": "workout_start",
        "workout_end": "workout_end",
        "query_recovery": "recovery",
        "workout_advice": "workout_advice",
    }
    if intent in routes:
        return routes[intent]
    if intent in ("query_hr", "query_hrv"):
        return "query_metrics"
    return END


def build_graph() -> StateGraph:
    g = StateGraph(HealthAgentState)

    g.add_node("parse_intent", parse_intent_node)
    g.add_node("record_sleep_start", record_sleep_start_node)
    g.add_node("run_sleep_analysis", run_sleep_analysis_node)
    g.add_node("query_metrics", query_metrics_node)
    g.add_node("health_snapshot", health_snapshot_node)
    g.add_node("workout_start", workout_start_node)
    g.add_node("workout_end", workout_end_node)
    g.add_node("recovery", recovery_node)
    g.add_node("workout_advice", workout_advice_node)

    g.set_entry_point("parse_intent")
    g.add_conditional_edges("parse_intent", _route)

    for node in (
        "record_sleep_start", "run_sleep_analysis", "query_metrics",
        "health_snapshot", "workout_start", "workout_end",
        "recovery", "workout_advice",
    ):
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
            "workout_type": None,
            "db": db,
        }
    )
