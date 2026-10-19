import pytest
from pydantic import ValidationError

from ops_agent.models import CIResult


def test_accepts_valid_ci_result() -> None:
    result = CIResult(
        run_id=42,
        service="backend",
        status="failed",
    )

    assert result.run_id == 42
    assert result.service == "backend"
    assert result.status == "failed"


def test_rejects_unknown_ci_status() -> None:
    with pytest.raises(ValidationError) as error:
        CIResult(
            run_id=42,
            service="backend",
            status="broken",
      )

    assert error.value.errors()[0]["loc"] == ("status",)


def test_rejects_zero_run_id() -> None:
    with pytest.raises(ValidationError) as error:
        CIResult(
            run_id=0,
            service="backend",
            status="failed",
        )

    assert error.value.errors()[0]["loc"] == ("run_id",)