
import asyncio
import json

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mcp import Client

from ops_agent.state import create_initial_state
from ops_agent.workflow import build_graph
from evals.metrics import evaluate_scenario, calculate_score

DATASET = (
    Path(__file__).resolve().parents[1]
    / "evals"
    / "scenarios.json"
)

SCENARIOS = json.loads(
    DATASET.read_text(encoding="utf-8")
)


@pytest.mark.parametrize(
    "scenario",
    SCENARIOS,
    ids=lambda scenario: scenario["id"],
)
def test_agent_evaluation(scenario: dict) -> None:
    expected = scenario["expected"]

    async def evaluate() -> None:
        client = AsyncMock(spec=Client)

        async def call_tool(name: str, arguments: dict):
            report = scenario["reports"][name]

            return SimpleNamespace(
                is_error=False,
                structured_content=report,
            )

        client.call_tool.side_effect = call_tool

        graph = build_graph(client)

        result = await graph.ainvoke(
            create_initial_state("backend", "local")
        )

        # 1. Routing accuracy
        called_tools = [
            call.args[0]
            for call in client.call_tool.await_args_list
        ]

        assert called_tools == expected["tool_calls"]

        # 2. Correct CI interpretation
        ci = result["ci"]

        assert ci is not None
        assert ci.status == expected["ci_status"]

        # 3. Proposal decision
        proposal = result["issue_proposal"]

        assert (proposal is not None) == expected["proposal"]

        # 4. Expected evidence-collection errors
        assert result["errors"] == expected["errors"]

        if proposal is not None:
            description = proposal.description

            # 5. Required evidence must be present
            for evidence in expected.get(
                "required_evidence", []
            ):
                assert evidence in description

            # 6. Unrelated evidence must be excluded
            for evidence in expected.get(
                "forbidden_evidence", []
            ):
                assert evidence not in description

        # 7. No write action without approval
        assert result["created_issue"] is None
    
        metrics = evaluate_scenario(
            result,
            called_tools,
            expected,
        )

        score = calculate_score(metrics)

        failed_metrics = [
            name
            for name, passed in metrics.items()
            if not passed
        ]

        assert score == 100.0, (
            f"Scenario {scenario['id']} scored {score}%."
            f" Failed metrics: {failed_metrics}"
        )



    asyncio.run(evaluate())
