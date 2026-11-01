import pytest
from pydantic import ValidationError
import json

from ops_agent.analysis import build_analysis_input
from ops_agent.models import LogsReport
from ops_agent.state import create_initial_state
from ops_agent.models import InvestigationAnalysis
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from ops_agent.analysis import analyse_investigation


def test_rejects_observations_as_string() -> None:
    with pytest.raises(ValidationError) as error:
        InvestigationAnalysis(
            observations="The readiness endpoint returned HTTP 503.",
            hypotheses=[],
            recommended_checks=[],
            limitations=[],
        )

    assert error.value.errors()[0]["loc"] == ("observations",)

def test_analysis_input_distinguishes_missing_and_empty_logs() -> None:
    state = create_initial_state("backend", "staging")

    missing = json.loads(build_analysis_input(state))

    assert missing["logs"] is None

    state["logs"] = LogsReport(
        run_id=42,
        service="backend",
        entries=[],
    )

    collected = json.loads(build_analysis_input(state))

    assert collected["logs"] is not None
    assert collected["logs"]["run_id"] == 42
    assert collected["logs"]["entries"] == []
    
def test_analysis_returns_validated_result() -> None:
    expected = InvestigationAnalysis(
        observations=["The readiness endpoint returned HTTP 503."],
        hypotheses=[],
        recommended_checks=["Inspect backend logs."],
        limitations=["Backend logs were not collected."],
    )

    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(
                    content=expected.model_dump_json(),
                ),
            )
        ]
    )

    create = AsyncMock(return_value=response)
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create),
        )
    )

    state = create_initial_state("backend", "local")

    result = asyncio.run(analyse_investigation(state, client))

    assert isinstance(result, InvestigationAnalysis)
    assert result == expected
    create.assert_awaited_once()

    sent = create.call_args.kwargs
    assert json.loads(sent["messages"][1]["content"])["environment"] == "local"


def test_analysis_rejects_invalid_output() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(
                    content=json.dumps(
                        {
                            "observations": "This should be a list.",
                            "hypotheses": [],
                            "recommended_checks": [],
                            "limitations": [],
                        }
                    ),
                ),
            )
        ]
    )

    create = AsyncMock(return_value=response)
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create),
        )
    )

    state = create_initial_state("backend", "local")

    with pytest.raises(ValidationError) as error:
        asyncio.run(analyse_investigation(state, client))

    assert error.value.errors()[0]["loc"] == ("observations",)