from pathlib import Path

import pytest
from pydantic import ValidationError

from ops_agent.tools import get_ci_status


def test_loads_ci_result(tmp_path: Path) -> None:
    path = tmp_path / "ci_run.json"
    path.write_text(
        '{"run_id": 42, "service": "backend", "status": "failed"}',
        encoding="utf-8",
    )

    result = get_ci_status(path)

    assert result.run_id == 42
    assert result.service == "backend"
    assert result.status == "failed"


def test_rejects_invalid_file_data(tmp_path: Path) -> None:
    path = tmp_path / "ci_run.json"
    path.write_text(
        '{"run_id": 42, "service": "backend", "status": "broken"}',
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        get_ci_status(path)