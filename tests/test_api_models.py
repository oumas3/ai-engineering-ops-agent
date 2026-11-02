from uuid import UUID

import pytest
from pydantic import ValidationError

from ops_agent.api_models import StartInvestigationRequest


RUN_ID = "94f6c0cdef5d456d9c708b84d986df24"


def test_start_request_accepts_report_folder_id() -> None:
    request = StartInvestigationRequest.model_validate({"report_run": RUN_ID})

    assert request.report_run == UUID(RUN_ID)
    assert request.analyse is False


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"report_run": "../data"}, "report_run"),
        ({"analyse": "false"}, "analyse"),
        ({"allow_create_issue": True}, "allow_create_issue"),
    ],
)
def test_start_request_rejects_invalid_input(
    change: dict[str, object],
    field: str,
) -> None:
    payload = {"report_run": RUN_ID, **change}

    with pytest.raises(ValidationError) as error:
        StartInvestigationRequest.model_validate(payload)

    assert error.value.errors()[0]["loc"] == (field,)