import asyncio
from unittest.mock import AsyncMock

import pytest
from groq import AsyncGroq

from ops_agent.models import CIResult, InvestigationAnalysis
from ops_agent.nodes import AnalysisNode
from ops_agent.state import create_initial_state


def test_node_returns_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = InvestigationAnalysis(
        observations=["CI run 42 failed."],
        hypotheses=[],
        recommended_checks=["Inspect backend logs."],
        limitations=["Backend logs were not collected."],
    )
    analyse = AsyncMock(return_value=expected)
    monkeypatch.setattr("ops_agent.nodes.analyse_investigation", analyse)

    client = AsyncMock(spec=AsyncGroq)
    node = AnalysisNode(client)
    state = create_initial_state("backend", "local")
    state["ci"] = CIResult(
        run_id=42,
        service="backend",
        status="failed",
    )

    update = asyncio.run(node.collect_analysis(state))

    assert update == {"analysis": expected}
    analyse.assert_awaited_once_with(state, client)
    assert state["analysis"] is None


@pytest.mark.parametrize(
    ("error", "expected_message"),
    [
        (
            TimeoutError(),
            "Analysis request timed out.",
        ),
        (
            ValueError("Empty response"),
            "Analysis returned an incomplete or empty response.",
        ),
    ],
)
def test_node_preserves_evidence_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_message: str,
) -> None:
    analyse = AsyncMock(side_effect=error)
    monkeypatch.setattr("ops_agent.nodes.analyse_investigation", analyse)

    node = AnalysisNode(AsyncMock(spec=AsyncGroq))
    state = create_initial_state("backend", "local")
    ci = CIResult(
        run_id=42,
        service="backend",
        status="failed",
    )
    state["ci"] = ci
    state["errors"] = ["Logs could not be collected."]

    update = asyncio.run(node.collect_analysis(state))

    assert update["analysis"] is None
    assert update["errors"] == [
        "Logs could not be collected.",
        expected_message,
    ]
    assert "ci" not in update
    assert state["ci"] is ci
    assert state["errors"] == ["Logs could not be collected."]