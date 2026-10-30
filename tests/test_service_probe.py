import json
from io import BytesIO
from unittest.mock import MagicMock
from urllib.error import HTTPError

import pytest

from ops_agent import service_probe


@pytest.mark.parametrize(
    "http_status, readiness, expected",
    [
        (200, "ready", "healthy"),
        (503, "not_ready", "degraded"),
        (200, "not_ready", "unknown"),
        (503, "ready", "unknown"),
    ],
)
def test_probe_maps_readiness_response(
    monkeypatch: pytest.MonkeyPatch,
    http_status: int,
    readiness: str,
    expected: str,
) -> None:
    body = json.dumps(
        {"service": "backend", "status": readiness}
    ).encode("utf-8")

    mocked_urlopen = MagicMock()

    if http_status >= 400:
        mocked_urlopen.side_effect = HTTPError(
            url="http://127.0.0.1:8000/ready",
            code=http_status,
            msg="Service Unavailable",
            hdrs=None,
            fp=BytesIO(body),
        )
    else:
        response = mocked_urlopen.return_value.__enter__.return_value
        response.status = http_status
        response.read.return_value = body

    monkeypatch.setattr(service_probe, "urlopen", mocked_urlopen)

    result = service_probe.probe_backend()

    assert result.service == "backend"
    assert result.environment == "local"
    assert result.status == expected
    mocked_urlopen.assert_called_once_with(
        "http://127.0.0.1:8000/ready",
        timeout=5,
    )