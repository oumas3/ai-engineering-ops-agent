
import asyncio
import json

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from mcp import Client

from evals.metrics import calculate_score, evaluate_scenario
from ops_agent.state import create_initial_state
from ops_agent.workflow import build_graph


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evals" / "scenarios.json"
OUTPUT = ROOT / "evals" / "results" / "latest.json"


async def run_scenario(scenario: dict) -> dict:
    """Execute one deterministic evaluation scenario."""
    client = AsyncMock(spec=Client)

    async def call_tool(name: str, arguments: dict):
        return SimpleNamespace(
            is_error=False,
            structured_content=scenario["reports"][name],
        )

    client.call_tool.side_effect = call_tool

    graph = build_graph(client)

    result = await graph.ainvoke(
        create_initial_state("backend", "local")
    )

    called_tools = [
        call.args[0]
        for call in client.call_tool.await_args_list
    ]

    metrics = evaluate_scenario(
        result,
        called_tools,
        scenario["expected"],
    )

    failed_metrics = [
        name
        for name, passed in metrics.items()
        if not passed
    ]

    return {
        "scenario_id": scenario["id"],
        "metrics": metrics,
        "score_pct": calculate_score(metrics),
        "passed": not failed_metrics,
        "failed_metrics": failed_metrics,
    }


async def run_evaluations(scenarios: list[dict]) -> dict:
    """Execute scenarios and summarize their quality metrics."""
    results = []

    for scenario in scenarios:
        results.append(await run_scenario(scenario))

    total_checks = sum(
        len(result["metrics"])
        for result in results
    )

    passed_checks = sum(
        sum(result["metrics"].values())
        for result in results
    )

    passed_scenarios = sum(
        result["passed"]
        for result in results
    )

    return {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "scenario_count": len(results),
        "passed_scenarios": passed_scenarios,
        "scenario_pass_rate_pct": round(
            100 * passed_scenarios / len(results), 2
        ) if results else 0.0,
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "check_pass_rate_pct": round(
            100 * passed_checks / total_checks, 2
        ) if total_checks else 0.0,
        "scenarios": results,
    }


def save_report(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    scenarios = json.loads(
        DATASET.read_text(encoding="utf-8")
    )

    report = asyncio.run(run_evaluations(scenarios))
    save_report(report, OUTPUT)

    print("\nAgent Evaluation Report")
    print("=" * 40)
    print(
        f"Scenarios: "
        f"{report['passed_scenarios']}/"
        f"{report['scenario_count']}"
    )
    print(
        f"Checks: "
        f"{report['passed_checks']}/"
        f"{report['total_checks']}"
    )
    print(
        f"Score: {report['check_pass_rate_pct']}%"
    )

    for result in report["scenarios"]:
        status = "PASS" if result["passed"] else "FAIL"
        print(
            f"{status} | {result['scenario_id']} "
            f"| {result['score_pct']}%"
        )

        if result["failed_metrics"]:
            print(
                "  Failed metrics: "
                + ", ".join(result["failed_metrics"])
            )

    print(f"\nReport: {OUTPUT}")

    return 0 if (
        report["passed_scenarios"]
        == report["scenario_count"]
        and report["scenario_count"] > 0
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
