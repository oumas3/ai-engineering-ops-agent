import asyncio
from pathlib import Path

import pytest
from mcp import Client

from ops_agent import mcp_server
from ops_agent.models import CIResult


def test_mcp_discovers_and_calls_ci_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Give the server a controlled report for this test.
    (tmp_path / "ci_run.json").write_text(
        '{"run_id": 42, "service": "backend", "status": "failed"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(mcp_server, "DATA_DIR", tmp_path)

    async def check() -> None:
        async with Client(mcp_server.server) as client:
            listed = await client.list_tools()
            names = [tool.name for tool in listed.tools]

            assert "get_ci_status" in names
            assert "read_logs" in names

            response = await client.call_tool("get_ci_status", {})

            assert response.is_error is False

            ci = CIResult.model_validate(response.structured_content)

            assert ci.run_id == 42
            assert ci.service == "backend"
            assert ci.status == "failed"
            

    asyncio.run(check())