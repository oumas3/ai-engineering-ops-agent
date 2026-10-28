import asyncio

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from mcp import Client

from types import SimpleNamespace
from unittest.mock import AsyncMock

from typing import Literal
from ops_agent.nodes import InvestigationNodes
from ops_agent.state import InvestigationState
from langgraph.checkpoint.base import BaseCheckpointSaver
from ops_agent.models import AgentPermissions


def route_after_approval(
    state: InvestigationState,
) -> Literal["create_issue", "finish"]:
    if state.get("approval_decision") == "approved":
        return "create_issue"

    return "finish"
def build_graph(
    client: Client,
    timeout_seconds: float = 5.0,
    checkpointer: BaseCheckpointSaver | None = None,
    interrupt_before: list[str] | None = None,
    permissions: AgentPermissions | None = None,
) -> CompiledStateGraph:
    nodes = InvestigationNodes(
        client,
        timeout_seconds=timeout_seconds,
        permissions=permissions,
    )
    builder = StateGraph(InvestigationState)

    builder.add_node("collect_ci", nodes.collect_ci)
    builder.add_node("collect_failed_tests", nodes.collect_failed_tests)
    builder.add_node("collect_logs", nodes.collect_logs)
    builder.add_node("collect_service_status", nodes.collect_service_status)
    builder.add_node("prepare_issue", nodes.prepare_issue)
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
    builder.add_edge("collect_service_status", "prepare_issue")
    if nodes.permissions.can_create_issue:
        if checkpointer is None:
            raise ValueError("Approval requires a checkpointer.")

        builder.add_node("request_approval", nodes.request_approval)
        builder.add_node("create_issue", nodes.create_approved_issue)

        builder.add_edge("prepare_issue", "request_approval")

        builder.add_conditional_edges(
            "request_approval",
            route_after_approval,
            {
                "create_issue": "create_issue",
                "finish": END,
            },
        )

        builder.add_edge("create_issue", END)
    else:
        builder.add_edge("prepare_issue", END)
    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_before,
    )

def route_after_ci(
    state: InvestigationState,
) -> Literal["collect_failed_tests", "finish"]:
    ci = state["ci"]

    if ci is not None and ci.status == "failed":
        return "collect_failed_tests"

    return "finish"  


def test_graph_collects_service_status_after_logs_timeout() -> None:
    reports = {
        "get_ci_status": {
            "run_id": 42,
            "service": "backend",
            "status": "failed",
        },
        "get_failed_tests": {
            "run_id": 42,
            "tests": [],
        },
        "get_service_status": {
            "service": "backend",
            "environment": "staging",
            "status": "degraded",
        },
    }

    async def call_tool(name: str, arguments: dict) -> SimpleNamespace:
        if name == "read_logs":
            await asyncio.sleep(60)
            raise AssertionError("The logs call should have timed out.")

        return SimpleNamespace(
            is_error=False,
            structured_content=reports[name],
        )

    client = AsyncMock(spec=Client)
    client.call_tool.side_effect = call_tool

    async def check() -> None:
        graph = build_graph(client, timeout_seconds=0.05)
        state = create_initial_state("backend", "staging")

        final_state = await graph.ainvoke(state)

        assert final_state["logs"] is None
        assert final_state["errors"] == ["Logs tool timed out."]

        health = final_state["service_status"]
        assert health is not None
        assert health.status == "degraded"

        names = [
            call.args[0]
            for call in client.call_tool.await_args_list
        ]
        assert names == [
            "get_ci_status",
            "get_failed_tests",
            "read_logs",
            "read_logs",
            "get_service_status",
        ]

    asyncio.run(check())