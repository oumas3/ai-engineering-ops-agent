import json
from urllib.error import HTTPError
from urllib.request import urlopen


def test_backend_is_ready() -> None:
    url = "http://127.0.0.1:8000/ready"

    try:
        with urlopen(url, timeout=5) as response:
            status = response.status
            body = response.read()
    except HTTPError as error:
        with error:
            status = error.code
            body = error.read()

    assert status == 200, (
        f"Expected HTTP 200, received HTTP {status}. "
        f"Response: {body.decode('utf-8', errors='replace')}"
    )

    payload = json.loads(body)
    assert payload["service"] == "backend"
    assert payload["status"] == "ready"