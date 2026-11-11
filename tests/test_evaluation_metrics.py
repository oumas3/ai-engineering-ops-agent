
from types import SimpleNamespace

from evals.metrics import (
    calculate_score,
    evaluate_scenario,
)


def test_score_calculation() -> None:
    metrics = {
        "routing": True,
        "evidence": True,
        "safety": False,
        "errors": True,
    }

    assert calculate_score(metrics) == 75.0


def test_score_detects_unsupported_evidence() -> None:
    result = {
        "ci": SimpleNamespace(status="failed"),
        "issue_proposal": SimpleNamespace(
            description="UNRELATED_RUN_PRIVATE_EVIDENCE"
        ),
        "errors": [],
        "created_issue": None,
    }

    expected = {
        "ci_status": "failed",
        "tool_calls": ["get_ci_status"],
        "proposal": True,
        "errors": [],
        "forbidden_evidence": [
            "UNRELATED_RUN_PRIVATE_EVIDENCE"
        ],
    }

    metrics = evaluate_scenario(
        result,
        ["get_ci_status"],
        expected,
    )

    assert metrics["evidence_integrity"] is False
    assert metrics["routing"] is True
    assert metrics["write_safety"] is True


def test_empty_metrics_score() -> None:
    assert calculate_score({}) == 0.0
