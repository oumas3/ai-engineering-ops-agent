import asyncio

from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from evals.run import build_fake_client
from ops_agent.models import AgentPermissions
from ops_agent.persistence import create_serializer
from ops_agent.state import create_initial_state
from ops_agent.workflow import build_graph


REPORTS = {
    "get_ci_status": {"run_id": 42, "service": "backend", "status": "failed"},
    "get_failed_tests": {"run_id": 42, "tests": []},
    "read_logs": {"run_id": 42, "service": "backend", "entries": []},
    "get_service_status": {
        "service": "backend",
        "environment": "local",
        "status": "healthy",
    },
}


def test_approved_issue_is_written_to_given_directory(tmp_path: Path) -> None:
    issue_directory = tmp_path / "issues"
    client = build_fake_client({"id": "issue_dir", "reports": REPORTS})
    graph = build_graph(
        client,
        checkpointer=InMemorySaver(serde=create_serializer()),
        permissions=AgentPermissions(can_create_issue=True),
        issue_directory=issue_directory,
    )
    config = {"configurable": {"thread_id": "issue-dir-test"}}

    async def run() -> dict:
        paused = await graph.ainvoke(
            create_initial_state("backend", "local"), config=config
        )
        assert "__interrupt__" in paused
        assert not issue_directory.exists()

        return await graph.ainvoke(Command(resume="approved"), config=config)

    result = asyncio.run(run())

    assert result["created_issue"] is not None
    assert len(list(issue_directory.glob("*.json"))) == 1