
from datetime import datetime, timedelta, timezone
from uuid import UUID

from ops_agent.api_models import (
    InvestigationEventResponse,
    InvestigationLifecycleStatus,
)
from ops_agent.observability import compute_execution_duration_ms


INVESTIGATION_ID = UUID("00000000-0000-4000-8000-000000000070")
START = datetime(2026, 11, 8, 14, 7, 13, tzinfo=timezone.utc)


def make_event(
    event_id: int,
    status: InvestigationLifecycleStatus,
    seconds: float,
) -> InvestigationEventResponse:
    return InvestigationEventResponse(
        event_id=event_id,
        investigation_id=INVESTIGATION_ID,
        status=status,
        occurred_at=START + timedelta(seconds=seconds),
    )


def test_completed_execution_duration() -> None:
    events = [
        make_event(1, "queued", 0),
        make_event(2, "running", 1),
        make_event(3, "completed", 6),
    ]

    assert compute_execution_duration_ms(events) == 5000


def test_approval_wait_is_excluded() -> None:
    events = [
        make_event(1, "running", 0),
        make_event(2, "awaiting_approval", 3),
        make_event(3, "completed", 63),
    ]

    assert compute_execution_duration_ms(events) == 3000


def test_running_execution_has_no_final_duration() -> None:
    events = [
        make_event(1, "queued", 0),
        make_event(2, "running", 1),
    ]

    assert compute_execution_duration_ms(events) is None
