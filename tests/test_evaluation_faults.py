import asyncio

import pytest

from ops_agent.state import create_initial_state
from ops_agent.workflow import build_graph
from evals.run import build_fake_client, run_scenario


FAILED_RUN_REPORTS = {
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
        "status": "healthy",
    },
}


def run_with_faults(faults: dict) -> tuple[dict, list[str]]:
    scenario = {
        "id": "fault_test",
        "reports": FAILED_RUN_REPORTS,
        "faults": faults,
    }
    client = build_fake_client(scenario)
    graph = build_graph(client)

    result = asyncio.run(
        graph.ainvoke(create_initial_state("backend", "local"))
    )
    called_tools = [
        call.args[0]
        for call in client.call_tool.await_args_list
    ]
    return result, called_tools


def test_no_faults_replays_reports() -> None:
    result, called_tools = run_with_faults({})

    assert result["errors"] == []
    assert called_tools == [
        "get_ci_status",
        "get_failed_tests",
        "read_logs",
        "get_service_status",
    ]


def test_timeout_fault_is_retried_once_then_recorded() -> None:
    result, called_tools = run_with_faults({"read_logs": "timeout"})

    # The agent retries a timed-out read tool exactly once.
    assert called_tools.count("read_logs") == 2
    assert result["logs"] is None
    assert result["errors"] == ["Logs tool timed out."]


def test_error_fault_is_recorded_without_retry() -> None:
    result, called_tools = run_with_faults({"read_logs": "error"})

    assert called_tools.count("read_logs") == 1
    assert result["logs"] is None
    assert result["errors"] == ["Logs tool execution failed."]


def test_fault_keeps_other_evidence() -> None:
    result, _ = run_with_faults({"get_failed_tests": "error"})

    # Partial evidence: one failed tool must not discard the others.
    assert result["failed_tests"] is None
    assert result["logs"] is not None
    assert result["service_status"] is not None
    assert result["issue_proposal"] is not None


def test_unknown_fault_type_is_rejected() -> None:
    scenario = {
        "id": "bad_fault",
        "reports": FAILED_RUN_REPORTS,
        "faults": {"read_logs": "explode"},
    }

    with pytest.raises(ValueError, match="unknown fault types"):
        build_fake_client(scenario)

def test_unexpected_tool_call_is_scored_not_crashed() -> None:
    # Failed CI makes the agent call more tools, but this scenario
    # (deliberately) only provides the CI report and expects one call.
    scenario = {
        "id": "unexpected_tool_call",
        "reports": {
            "get_ci_status": FAILED_RUN_REPORTS["get_ci_status"],
        },
        "expected": {
            "ci_status": "failed",
            "tool_calls": ["get_ci_status"],
            "proposal": False,
            "errors": [],
        },
    }

    result = asyncio.run(run_scenario(scenario))

    assert result["passed"] is False
    assert "routing" in result["failed_metrics"]