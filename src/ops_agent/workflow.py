from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from mcp import Client

from typing import Literal
from ops_agent.nodes import InvestigationNodes
from ops_agent.state import InvestigationState


def build_graph(client: Client) -> CompiledStateGraph:
    nodes = InvestigationNodes(client)
    builder = StateGraph(InvestigationState)

    builder.add_node("collect_ci", nodes.collect_ci)
    builder.add_node("collect_failed_tests", nodes.collect_failed_tests)
    builder.add_node("collect_logs", nodes.collect_logs)
    builder.add_node("collect_service_status", nodes.collect_service_status)
    builder.add_edge(START, "collect_ci")

    builder.add_conditional_edges(
        "collect_ci",
        route_after_ci,
        {
            "collect_failed_tests": "collect_failed_tests",
            "finish": END,
        },
    )

    builder.add_edge("collect_failed_tests", "collect_logs")
    builder.add_edge("collect_logs", "collect_service_status")
    builder.add_edge("collect_service_status", END)

    return builder.compile()

def route_after_ci(
    state: InvestigationState,
) -> Literal["collect_failed_tests", "finish"]:
    ci = state["ci"]

    if ci is not None and ci.status == "failed":
        return "collect_failed_tests"

    return "finish"  