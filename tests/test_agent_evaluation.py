import asyncio
import json

import pytest

from evals.run import DATASET, run_scenario

SCENARIOS = json.loads(
    DATASET.read_text(encoding="utf-8")
)


@pytest.mark.parametrize(
    "scenario",
    SCENARIOS,
    ids=lambda scenario: scenario["id"],
)
def test_agent_evaluation(scenario: dict) -> None:
    """Every golden scenario must pass all metrics.

    Uses the same runner as ``python -m evals.run`` so the test and the
    CI scorecard cannot drift apart.
    """
    result = asyncio.run(run_scenario(scenario))

    assert result["passed"], (
        f"Scenario {scenario['id']} scored {result['score_pct']}%."
        f" Failed metrics: {result['failed_metrics']}"
    )
