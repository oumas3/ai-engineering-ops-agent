import pytest
from pydantic import ValidationError
import json

from ops_agent.analysis import build_analysis_input
from ops_agent.models import LogsReport
from ops_agent.state import create_initial_state
from ops_agent.models import InvestigationAnalysis


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