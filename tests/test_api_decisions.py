import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest

from ops_agent.api_decisions import NoPendingApproval, require_pending_approval


def test_completed_proposal_cannot_be_approved() -> None:
    investigation_id = UUID("ce0615bc-9d65-4b11-828d-fc27a93a5eb1")
    graph = Mock()
    graph.aget_state = AsyncMock(
        return_value=SimpleNamespace(
            values={"issue_proposal": {"title": "Investigate backend failure"}},
            tasks=(),
        )
    )

    with pytest.raises(NoPendingApproval):
        asyncio.run(require_pending_approval(graph, investigation_id))

    graph.aget_state.assert_awaited_once_with(
        {"configurable": {"thread_id": str(investigation_id)}}
    )
    graph.ainvoke.assert_not_called()