from uuid import UUID

import pytest
from pydantic import ValidationError

from ops_agent.api_models import  CIResultResponse, InvestigationDecisionRequest, InvestigationResultResponse, StartInvestigationRequest
InvestigationResultResponse, InvestigationDecisionRequest, StartInvestigationRequest


RUN_ID = "94f6c0cdef5d456d9c708b84d986df24"

def test_large_run_id_serializes_as_string() -> None:
    run_id = 6708014345158128627

    response = InvestigationResultResponse(
        investigation_id=UUID("00000000-0000-4000-8000-000000000010"),
        service="backend",
        environment="local",
        ci=CIResultResponse(
            run_id=run_id,
            service="backend",
            status="failed",
        ),
        failed_tests=None,
        logs=None,
        service_status=None,
        analysis=None,
        issue_proposal=None,
        errors=[],
    )

    payload = response.model_dump(mode="json")

    assert payload["ci"]["run_id"] == str(run_id)
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

@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_accepts_explicit_decision(decision: str) -> None:
    request = InvestigationDecisionRequest.model_validate(
        {"decision": decision}
    )
    assert request.decision == decision


@pytest.mark.parametrize(
    "payload",
    [
        {"decision": "maybe"},
        {"decision": "approved", "can_create_issue": True},
    ],
)
def test_rejects_invalid_decision_request(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        InvestigationDecisionRequest.model_validate(payload)