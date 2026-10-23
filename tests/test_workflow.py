import asyncio
from pathlib import Path

import pytest
from mcp import Client

from ops_agent import mcp_server
from ops_agent.models import CIResult
from ops_agent.state import create_initial_state
from ops_agent.workflow import build_graph, route_after_ci

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

    async def check() -> None:
        async with Client(mcp_server.server) as client:
            graph = build_graph(client)
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