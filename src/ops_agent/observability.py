
from collections.abc import Sequence

from ops_agent.api_models import InvestigationEventResponse


def compute_execution_duration_ms(
    events: Sequence[InvestigationEventResponse],
) -> int | None:
    """Calculate execution duration from ordered lifecycle events."""

    started_at = None

    for event in events:
        if started_at is None:
            if event.status == "running":
                started_at = event.occurred_at
            continue

        if event.status in {
            "awaiting_approval",
            "completed",
            "failed",
        }:
            duration = event.occurred_at - started_at
            milliseconds = round(duration.total_seconds() * 1000)

            return milliseconds if milliseconds >= 0 else None

    return None
