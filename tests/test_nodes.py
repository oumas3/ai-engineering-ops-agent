import asyncio
from unittest.mock import AsyncMock

import pytest

from types import SimpleNamespace
from mcp import Client

from ops_agent.models import CIResult
from ops_agent.nodes import InvestigationNodes
from ops_agent.state import create_initial_state


def test_collect_logs_handles_timeout() -> None:
    async def slow_call(*args: object, **kwargs: object) -> None:
        await asyncio.sleep(60)

    client = AsyncMock(spec=Client)
    client.call_tool.side_effect = slow_call

    nodes = InvestigationNodes(client)
    state = create_initial_state("backend", "staging")
    state["ci"] = CIResult(
        run_id=42,
        service="backend",
        status="failed",
    )



    update = asyncio.run(nodes.collect_logs(state))

    assert update["logs"] is None
    assert update["errors"] == ["Logs tool timed out."]
    assert update["logs"] is None
    assert update["errors"] == ["Logs tool timed out."]
    assert client.call_tool.await_count == 2
    client.call_tool.assert_awaited_with("read_logs", {})


def test_collect_logs_recovers_after_timeout() -> None:
    successful_response = SimpleNamespace(
        is_error=False,
        structured_content={
            "run_id": 42,
            "service": "backend",
            "entries": [
                {
                    "level": "ERROR",
                    "message": "Database connection timed out.",
                }
            ],
        },
    )

    client = AsyncMock(spec=Client)
    client.call_tool.side_effect = [
        TimeoutError(),
        successful_response,
    ]

    nodes = InvestigationNodes(client)
    state = create_initial_state("backend", "staging")
    state["ci"] = CIResult(
        run_id=42,
        service="backend",
        status="failed",
    )

    update = asyncio.run(nodes.collect_logs(state))

    logs = update["logs"]
    assert logs is not None
    assert logs.run_id == 42
    assert logs.entries[0].message == "Database connection timed out."
    assert "errors" not in update
    assert client.call_tool.await_count == 2


def test_collect_logs_does_not_retry_success() -> None:
    response = SimpleNamespace(
        is_error=False,
        structured_content={
            "run_id": 42,
            "service": "backend",
            "entries": [],
        },
    )

    client = AsyncMock(spec=Client)
    client.call_tool.return_value = response

    nodes = InvestigationNodes(client)
    state = create_initial_state("backend", "staging")
    state["ci"] = CIResult(
        run_id=42,
        service="backend",
        status="failed",
    )

    update = asyncio.run(nodes.collect_logs(state))

    logs = update["logs"]
    assert logs is not None
    assert logs.entries == []
    assert "errors" not in update
    client.call_tool.assert_awaited_once_with("read_logs", {})


def test_collect_logs_does_not_retry_invalid_data() -> None:
    response = SimpleNamespace(
        is_error=False,
        structured_content={
            "run_id": 0,
            "service": "backend",
            "entries": [],
        },
    )

    client = AsyncMock(spec=Client)
    client.call_tool.return_value = response

    nodes = InvestigationNodes(client, timeout_seconds=0.05)
    state = create_initial_state("backend", "staging")
    state["ci"] = CIResult(
        run_id=42,
        service="backend",
        status="failed",
    )

    update = asyncio.run(nodes.collect_logs(state))

    assert update["logs"] is None
    assert update["errors"] == ["Logs tool returned invalid data."]
    client.call_tool.assert_awaited_once_with("read_logs", {})


@pytest.mark.parametrize("timeout_seconds", [0, -1])
def test_rejects_nonpositive_timeout(timeout_seconds: float) -> None:
    client = AsyncMock(spec=Client)

    with pytest.raises(
        ValueError,
        match="timeout_seconds must be greater than zero.",
    ):
        InvestigationNodes(client, timeout_seconds=timeout_seconds)

    client.call_tool.assert_not_called()


def test_collect_ci_handles_timeout() -> None:
    client = AsyncMock(spec=Client)
    client.call_tool.side_effect = TimeoutError()

    nodes = InvestigationNodes(client)
    state = create_initial_state("backend", "staging")

    update = asyncio.run(nodes.collect_ci(state))

    assert update["ci"] is None
    assert update["errors"] == ["CI tool timed out."]
    assert client.call_tool.await_count == 2
    client.call_tool.assert_awaited_with("get_ci_status", {})


@pytest.mark.parametrize(
    "method_name, tool_name, field, message",
    [
        (
            "collect_failed_tests",
            "get_failed_tests",
            "failed_tests",
            "Failed-tests tool timed out.",
        ),
        (
            "collect_service_status",
            "get_service_status",
            "service_status",
            "Service-status tool timed out.",
        ),
    ],
)
def test_remaining_nodes_handle_timeout(
    method_name: str,
    tool_name: str,
    field: str,
    message: str,
) -> None:
    client = AsyncMock(spec=Client)
    client.call_tool.side_effect = TimeoutError()

    nodes = InvestigationNodes(client)
    state = create_initial_state("backend", "staging")
    state["ci"] = CIResult(
        run_id=42,
        service="backend",
        status="failed",
    )

    method = getattr(nodes, method_name)
    update = asyncio.run(method(state))

    assert update[field] is None
    assert update["errors"] == [message]
    assert client.call_tool.await_count == 2
    client.call_tool.assert_awaited_with(tool_name, {})

