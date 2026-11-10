import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from mcp import Client
from ops_agent import mcp_server
from ops_agent.models import CIResult
from ops_agent.state import create_initial_state
from ops_agent.workflow import build_graph, route_after_ci
from unittest.mock import AsyncMock
from groq import AsyncGroq
from ops_agent.models import InvestigationAnalysis
import sqlite3
from uuid import UUID
from ops_agent.api_status_store import initialize_status_store
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from ops_agent.api_status_store import initialize_status_store
from ops_agent.models import AgentPermissions
from ops_agent.persistence import create_serializer

def test_failed_ci_routes_to_failed_tests() -> None:
    state = create_initial_state("backend", "staging")
    state["ci"] = CIResult(
        run_id=42,
        service="backend",
        status="failed",
    )

    route = route_after_ci(state)

    assert route == "collect_failed_tests"

def test_passed_ci_routes_to_finish() -> None:
    state = create_initial_state("backend", "staging")
    state["ci"] = CIResult(
        run_id=42,
        service="backend",
        status="passed",
    )

    route = route_after_ci(state)

    assert route == "finish"

def test_missing_ci_routes_to_finish() -> None:
    state = create_initial_state("backend", "staging")

    route = route_after_ci(state)

    assert route == "finish"

def test_running_ci_routes_to_finish() -> None:
    state = create_initial_state("backend", "staging")
    state["ci"] = CIResult(
        run_id=42,
        service="backend",
        status="running",
    )

    route = route_after_ci(state)

    assert route == "finish"

def test_graph_collects_failed_tests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "ci_run.json").write_text(
        '{"run_id": 42, "service": "backend", "status": "failed"}',
        encoding="utf-8",
    )
    (tmp_path / "failed_tests.json").write_text(
        '{"run_id": 42, "tests": ['
        '{"name": "test_health", "message": "Expected 200, received 503."}'
        ']}',
        encoding="utf-8",
    )
    (tmp_path / "logs.json").write_text(
        '{"run_id": 42, "service": "backend", "entries": ['
        '{"level": "ERROR", "message": "Database connection timed out."}'
        ']}',
        encoding="utf-8",
    )
    (tmp_path / "service_status.json").write_text(
        '{"service": "backend", "environment": "staging", '
        '"status": "degraded"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(mcp_server, "DATA_DIR", tmp_path)
    expected_analysis = InvestigationAnalysis(
        observations=["CI run 42 failed."],
        hypotheses=[],
        recommended_checks=["Inspect database connectivity."],
        limitations=["The root cause is not established."],
    )

    analyse = AsyncMock(return_value=expected_analysis)
    monkeypatch.setattr(
        "ops_agent.nodes.analyse_investigation",
        analyse,
    )

    llm_client = AsyncMock(spec=AsyncGroq)

    async def check() -> None:
        async with Client(mcp_server.server) as client:
            graph = build_graph(client, llm_client=llm_client)
            state = create_initial_state("backend", "staging")
            final_state = await graph.ainvoke(state)

        report = final_state["failed_tests"]

        assert report is not None
        assert report.run_id == 42
        assert report.tests[0].name == "test_health"
        assert final_state["errors"] == []
        assert final_state["logs"] is not None
        assert final_state["logs"].run_id == 42
        assert final_state["logs"].service == "backend"
        assert final_state["logs"].entries[0].message == "Database connection timed out."
        assert final_state["analysis"] == expected_analysis
        analyse.assert_awaited_once()

        analysed_state = analyse.call_args.args[0]
        assert analysed_state["ci"] is not None
        assert analysed_state["failed_tests"] is not None
        assert analysed_state["logs"] is not None
        assert analysed_state["service_status"] is not None
        health = final_state["service_status"]
        assert health is not None
        assert health.service == "backend"
        assert health.environment == "staging"
        assert health.status == "degraded"


    asyncio.run(check())

def test_graph_collects_logs_when_failed_tests_are_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "ci_run.json").write_text(
        '{"run_id": 42, "service": "backend", "status": "failed"}',
        encoding="utf-8",
    )
    (tmp_path / "logs.json").write_text(
        '{"run_id": 42, "service": "backend", "entries": ['
        '{"level": "ERROR", "message": "Database connection timed out."}'
        ']}',
        encoding="utf-8",
    )
    (tmp_path / "service_status.json").write_text(
        '{"service": "backend", "environment": "staging", '
        '"status": "degraded"}',
        encoding="utf-8",
    )

    monkeypatch.setattr(mcp_server, "DATA_DIR", tmp_path)

    async def check() -> None:
        async with Client(mcp_server.server) as client:
            graph = build_graph(client)
            state = create_initial_state("backend", "staging")

            final_state = await graph.ainvoke(state)

        assert final_state["failed_tests"] is None
        assert "Failed-tests tool execution failed." in final_state["errors"]

        logs = final_state["logs"]
        assert logs is not None
        assert logs.entries[0].message == "Database connection timed out."
        health = final_state["service_status"]
        assert health is not None
        assert health.service == "backend"          
        assert health.environment == "staging"
        assert health.status == "degraded"
        

    asyncio.run(check())


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


def test_graph_records_real_node_execution(
    tmp_path: Path,
) -> None:
    database = tmp_path / "statuses.sqlite"
    investigation_id = UUID(
        "00000000-0000-4000-8000-000000000091"
    )

    async def check() -> None:
        await initialize_status_store(database)

        client = AsyncMock(spec=Client)
        client.call_tool.return_value = SimpleNamespace(
            is_error=False,
            structured_content={
                "run_id": 42,
                "service": "backend",
                "status": "passed",
            },
        )

        graph = build_graph(
            client,
            trace_database=database,
            investigation_id=investigation_id,
        )

        result = await graph.ainvoke(
            create_initial_state("backend", "local")
        )

        assert result["ci"].status == "passed"

    asyncio.run(check())

    with sqlite3.connect(database) as db:
        rows = db.execute(
            """
            SELECT node_name, outcome, duration_ms, error_type
            FROM node_executions
            WHERE investigation_id = ?
            ORDER BY execution_id
            """,
            (str(investigation_id),),
        ).fetchall()

    assert len(rows) == 1
    assert rows[0][0] == "collect_ci"
    assert rows[0][1] == "completed"
    assert rows[0][2] >= 0
    assert rows[0][3] is None


def test_tracing_survives_approval_resumption(
    tmp_path: Path,
) -> None:
    database = tmp_path / "statuses.sqlite"
    investigation_id = UUID(
        "00000000-0000-4000-8000-000000000092"
    )

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
            "environment": "local",
            "status": "degraded",
        },
    }

    async def call_tool(name: str, arguments: dict):
        return SimpleNamespace(
            is_error=False,
            structured_content=reports[name],
        )

    async def check() -> None:
        await initialize_status_store(database)

        client = AsyncMock(spec=Client)
        client.call_tool.side_effect = call_tool

        checkpointer = InMemorySaver(
            serde=create_serializer()
        )

        config = {
            "configurable": {
                "thread_id": str(investigation_id)
            }
        }

        def create_graph():
            return build_graph(
                client,
                checkpointer=checkpointer,
                permissions=AgentPermissions(
                    can_create_issue=True
                ),
                trace_database=database,
                investigation_id=investigation_id,
            )

        # First execution: pause for approval.
        graph = create_graph()

        paused = await graph.ainvoke(
            create_initial_state("backend", "local"),
            config=config,
        )

        assert paused["__interrupt__"]
        assert (
            paused["__interrupt__"][0].value["action"]
            == "create_issue"
        )

        snapshot = await graph.aget_state(config)

        assert any(
            task.name == "request_approval"
            and task.interrupts
            for task in snapshot.tasks
        )

        # Reconstruct graph, then resume with rejection.
        resumed_graph = create_graph()

        completed = await resumed_graph.ainvoke(
            Command(resume="rejected"),
            config=config,
        )

        assert completed["approval_decision"] == "rejected"
        assert completed["created_issue"] is None

        final_snapshot = await resumed_graph.aget_state(
            config
        )
        assert final_snapshot.next == ()

    asyncio.run(check())

    # Inspect persisted node traces.
    with sqlite3.connect(database) as db:
        rows = db.execute(
            """
            SELECT node_name, outcome
            FROM node_executions
            WHERE investigation_id = ?
            ORDER BY execution_id
            """,
            (str(investigation_id),),
        ).fetchall()

    approval_outcomes = [
        outcome
        for name, outcome in rows
        if name == "request_approval"
    ]

    assert approval_outcomes == [
        "interrupted",
        "completed",
    ]

    # Rejection must never run the issue-writing node.
    assert all(
        name != "create_issue"
        for name, _ in rows
    )
