
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

def test_ci_interpretation_expects_rejected_ci() -> None:
    expected = {
        "ci_status": None,
        "tool_calls": ["get_ci_status"],
        "proposal": False,
        "errors": ["CI tool returned invalid data."],
    }
    rejected = {
        "ci": None,
        "issue_proposal": None,
        "errors": ["CI tool returned invalid data."],
        "created_issue": None,
    }
    accepted = {**rejected, "ci": SimpleNamespace(status="failed")}

    rejected_metrics = evaluate_scenario(
        rejected, ["get_ci_status"], expected
    )
    accepted_metrics = evaluate_scenario(
        accepted, ["get_ci_status"], expected
    )

    assert rejected_metrics["ci_interpretation"] is True
    assert accepted_metrics["ci_interpretation"] is False
