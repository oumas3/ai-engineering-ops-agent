import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiosqlite
from mcp import Client
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from ops_agent.persistence import create_serializer
from ops_agent.state import create_initial_state
from ops_agent.workflow import build_graph


def test_checkpoint_survives_database_reopen(tmp_path: Path) -> None:
    database_path = tmp_path / "checkpoints.sqlite"
    config = {"configurable": {"thread_id": "saved-investigation"}}

    client = AsyncMock(spec=Client)
    client.call_tool.return_value = SimpleNamespace(
        is_error=False,
        structured_content={
            "run_id": 42,
            "service": "backend",
            "status": "passed",
        },
    )

    async def check() -> None:
        async with aiosqlite.connect(str(database_path)) as connection:
            saver = AsyncSqliteSaver(
                connection,
                serde=create_serializer(),
            )
            graph = build_graph(client, checkpointer=saver)

            await graph.ainvoke(
                create_initial_state("backend", "staging"),
                config=config,
            )

        reader_client = AsyncMock(spec=Client)

        async with aiosqlite.connect(str(database_path)) as connection:
            saver = AsyncSqliteSaver(
                connection,
                serde=create_serializer(),
            )
            graph = build_graph(reader_client, checkpointer=saver)

            snapshot = await graph.aget_state(config)

            assert snapshot.values["ci"].run_id == 42
            assert snapshot.values["ci"].status == "passed"
            assert snapshot.next == ()
            missing_snapshot = await graph.aget_state(
                {
                    "configurable": {
                        "thread_id": "another-investigation",
                    }
                }
            )

            assert not missing_snapshot.values
            reader_client.call_tool.assert_not_called()

    asyncio.run(check())
def test_graph_resumes_after_pause(tmp_path: Path) -> None:
    database_path = tmp_path / "resume.sqlite"
    config = {"configurable": {"thread_id": "paused-investigation"}}

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
        "read_logs": {
            "run_id": 42,
            "service": "backend",
            "entries": [],
        },
        "get_service_status": {
            "service": "backend",
            "environment": "staging",
            "status": "degraded",
        },
    }

    async def call_tool(
        name: str,
        arguments: dict[str, object],
    ) -> SimpleNamespace:
        return SimpleNamespace(
            is_error=False,
            structured_content=reports[name],
        )

    client = AsyncMock(spec=Client)
    client.call_tool.side_effect = call_tool

    async def check() -> None:
        async with aiosqlite.connect(str(database_path)) as connection:
            saver = AsyncSqliteSaver(
                connection,
                serde=create_serializer(),
            )
            graph = build_graph(
                client,
                checkpointer=saver,
                interrupt_before=["collect_failed_tests"],
            )

            await graph.ainvoke(
                create_initial_state("backend", "staging"),
                config=config,
            )

            paused = await graph.aget_state(config)

            assert paused.values["ci"].run_id == 42
            assert paused.values["failed_tests"] is None
            assert paused.next == ("collect_failed_tests",)
            client.call_tool.assert_awaited_once_with("get_ci_status", {})

            final_state = await graph.ainvoke(None, config=config)

            assert final_state["failed_tests"] is not None
            assert final_state["service_status"].status == "degraded"
            assert final_state["errors"] == []

            completed = await graph.aget_state(config)
            assert completed.next == ()

            names = [
                call.args[0]
                for call in client.call_tool.await_args_list
            ]
            assert names == [
                "get_ci_status",
                "get_failed_tests",
                "read_logs",
                "get_service_status",
            ]

    asyncio.run(check())