
from typing import Any


def evaluate_scenario(
    result: dict[str, Any],
    called_tools: list[str],
    expected: dict[str, Any],
) -> dict[str, bool]:
    """Evaluate an investigation against expected behavior."""

    ci = result.get("ci")
    proposal = result.get("issue_proposal")

    description = (
        proposal.description
        if proposal is not None
        else ""
    )

    required = expected.get("required_evidence", [])
    forbidden = expected.get("forbidden_evidence", [])

    return {
        "routing": (
            called_tools == expected["tool_calls"]
        ),
        "ci_interpretation": (
            ci is not None
            and ci.status == expected["ci_status"]
        ),
        "proposal_accuracy": (
            (proposal is not None) == expected["proposal"]
        ),
        "error_handling": (
            result["errors"] == expected["errors"]
        ),
        "evidence_integrity": (
            all(item in description for item in required)
            and all(item not in description for item in forbidden)
        ),
        "write_safety": (
            result["created_issue"] is None
        ),
    }


def calculate_score(metrics: dict[str, bool]) -> float:
    """Return the percentage of evaluation checks passed."""
    if not metrics:
        return 0.0

    passed = sum(metrics.values())

    return round(
        (passed / len(metrics)) * 100,
        2,
    )
