from uuid import UUID

from langgraph.graph.state import CompiledStateGraph
import sys
from pathlib import Path
from typing import Literal

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from mcp import Client, StdioServerParameters

from ops_agent.models import AgentPermissions
from ops_agent.persistence import create_serializer
from ops_agent.workflow import build_graph


class InvestigationNotFound(Exception):
    pass


class NoPendingApproval(Exception):
    pass


async def is_approval_pending(investigation_id: UUID) -> bool:
    src_dir = Path(__file__).resolve().parents[1]
    database = src_dir.parent / "runtime" / "checkpoints.sqlite"

    if not database.is_file():
        raise InvestigationNotFound("No saved investigation found.")

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ops_agent.mcp_server"],
        env={"PYTHONPATH": str(src_dir)},
    )

    async with aiosqlite.connect(str(database)) as connection:
        saver = AsyncSqliteSaver(
            connection,
            serde=create_serializer(),
        )

        async with Client(params) as client:
            graph = build_graph(
                client,
                checkpointer=saver,
                permissions=AgentPermissions(can_create_issue=True),
            )

            try:
                await require_pending_approval(graph, investigation_id)
            except NoPendingApproval:
                return False

            return True


async def require_pending_approval(
    graph: CompiledStateGraph,
    investigation_id: UUID,
) -> None:
    config = {"configurable": {"thread_id": str(investigation_id)}}
    snapshot = await graph.aget_state(config)

    if not snapshot.values:
        raise InvestigationNotFound("No saved investigation found.")

    for task in snapshot.tasks:
        if task.name != "request_approval":
            continue

        for interrupt in task.interrupts:
            payload = interrupt.value
            if isinstance(payload, dict) and payload.get("action") == "create_issue":
                return

    raise NoPendingApproval("No issue-creation approval is pending.")

class IssueCreationDisabled(Exception):
    pass


async def apply_decision(
    investigation_id: UUID,
    decision: Literal["approved", "rejected"],
    *,
    allow_create_issue: bool,
) -> None:
    src_dir = Path(__file__).resolve().parents[1]
    database = src_dir.parent / "runtime" / "checkpoints.sqlite"

    if not database.is_file():
        raise InvestigationNotFound("No saved investigation found.")

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ops_agent.mcp_server"],
        env={"PYTHONPATH": str(src_dir)},
    )

    decision_error: Exception | None = None

    async with aiosqlite.connect(str(database)) as connection:
        saver = AsyncSqliteSaver(
            connection,
            serde=create_serializer(),
        )

        async with Client(params) as client:
            graph = build_graph(
                client,
                checkpointer=saver,
                permissions=AgentPermissions(can_create_issue=True),
            )

            try:
                await require_pending_approval(
                    graph,
                    investigation_id,
                )
            except (
                InvestigationNotFound,
                NoPendingApproval,
            ) as error:
                decision_error = error
            else:
                if not allow_create_issue:
                    decision_error = IssueCreationDisabled(
                        "Issue creation is disabled."
                    )
                else:
                    config = {
                        "configurable": {
                            "thread_id": str(investigation_id)
                        }
                    }

                    await graph.ainvoke(
                        Command(resume=decision),
                        config=config,
                    )

        if decision_error is not None:
            raise decision_error