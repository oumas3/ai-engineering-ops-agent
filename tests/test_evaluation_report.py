
import asyncio
import json

from copy import deepcopy
from pathlib import Path

from evals.run import (
    DATASET,
    run_evaluations,
    save_report,
)


def load_scenarios() -> list[dict]:
    return json.loads(
        DATASET.read_text(encoding="utf-8")
    )


def test_scorecard_aggregates_scenarios() -> None:
    report = asyncio.run(
        run_evaluations(load_scenarios())
    )

    assert report["scenario_count"] == 3
    assert report["passed_scenarios"] == 3
    assert report["total_checks"] == 18
    assert report["passed_checks"] == 18
    assert report["check_pass_rate_pct"] == 100.0


def test_scorecard_detects_regression() -> None:
    scenarios = deepcopy(load_scenarios())

    # Deliberately introduce an incorrect expectation.
    scenarios[0]["expected"]["ci_status"] = "failed"

    report = asyncio.run(run_evaluations(scenarios))

    assert report["passed_scenarios"] == 2
    assert report["check_pass_rate_pct"] < 100.0

    first = report["scenarios"][0]

    assert first["passed"] is False
    assert "ci_interpretation" in first["failed_metrics"]


def test_scorecard_saved_as_json(tmp_path: Path) -> None:
    path = tmp_path / "evaluation.json"

    report = {
        "scenario_count": 3,
        "passed_scenarios": 3,
        "check_pass_rate_pct": 100.0,
    }

    save_report(report, path)

    assert path.exists()
    assert json.loads(
        path.read_text(encoding="utf-8")
    ) == report
