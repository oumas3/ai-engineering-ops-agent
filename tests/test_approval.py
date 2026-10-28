from unittest.mock import AsyncMock

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from mcp import Client
from pathlib import Path

from ops_agent.models import CreatedIssue, IssueProposal
from ops_agent.nodes import InvestigationNodes
from ops_agent.state import InvestigationState, create_initial_state
from ops_agent.models import AgentPermissions, IssueProposal
import pytest

from ops_agent.persistence import create_serializer
from ops_agent.workflow import route_after_approval

@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_approval_pauses_then_records_decision(decision: str) -> None:
    client = AsyncMock(spec=Client)

    nodes = InvestigationNodes(
        client,
        permissions=AgentPermissions(can_create_issue=True),
    )
    builder = StateGraph(InvestigationState)
    builder.add_node("request_approval", nodes.request_approval)
    builder.add_edge(START, "request_approval")
    builder.add_edge("request_approval", END)

    graph = builder.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "approval-test"}}

    state = create_initial_state("backend", "staging")
    state["issue_proposal"] = IssueProposal(
        run_id=42,
        service="backend",
        title="Investigate backend CI failure",
        description="The health test received HTTP 503.",
    )

    paused = graph.invoke(state, config=config)

    assert paused["approval_decision"] is None
    assert paused["__interrupt__"][0].value["action"] == "create_issue"
    client.call_tool.assert_not_called()

    completed = graph.invoke(
        Command(resume=decision),
        config=config,
    )

    assert completed["approval_decision"] == decision
    assert graph.get_state(config).next == ()
    client.call_tool.assert_not_called()
def test_disabled_permission_blocks_approval_request() -> None:
    client = AsyncMock(spec=Client)
    nodes = InvestigationNodes(client)

    state = create_initial_state("backend", "staging")
    state["issue_proposal"] = IssueProposal(
        run_id=42,
        service="backend",
        title="Investigate backend CI failure",
        description="The health test received HTTP 503.",
    )

    update = nodes.request_approval(state)

    assert update["approval_decision"] is None
    assert update["errors"] == ["Issue creation is not permitted."]
    client.call_tool.assert_not_called()
@pytest.mark.parametrize("decision", [None, "rejected"])
def test_write_requires_explicit_approval(
    tmp_path: Path,
    decision: str | None,
) -> None:
    directory = tmp_path / "issues"
    client = AsyncMock(spec=Client)
    nodes = InvestigationNodes(
        client,
        permissions=AgentPermissions(can_create_issue=True),
        issue_directory=directory,
    )

    state = create_initial_state("backend", "staging")
    state["issue_proposal"] = IssueProposal(
        run_id=42,
        service="backend",
        title="Investigate backend CI failure",
        description="The health test received HTTP 503.",
    )
    state["approval_decision"] = decision

    update = nodes.create_approved_issue(state)

    assert update["errors"] == [
        "Issue creation requires explicit approval."
    ]
    assert "created_issue" not in update
    assert not directory.exists()
    client.call_tool.assert_not_called()

def test_write_permission_blocks_even_approved_proposal(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "issues"
    client = AsyncMock(spec=Client)
    nodes = InvestigationNodes(
        client,
        issue_directory=directory,
    )

    state = create_initial_state("backend", "staging")
    state["issue_proposal"] = IssueProposal(
        run_id=42,
        service="backend",
        title="Investigate backend CI failure",
        description="The health test received HTTP 503.",
    )
    state["approval_decision"] = "approved"

    update = nodes.create_approved_issue(state)

    assert update["errors"] == ["Issue creation is not permitted."]
    assert "created_issue" not in update
    assert not directory.exists()

def test_approved_issue_is_saved(tmp_path: Path) -> None:
    directory = tmp_path / "issues"
    client = AsyncMock(spec=Client)
    nodes = InvestigationNodes(
        client,
        permissions=AgentPermissions(can_create_issue=True),
        issue_directory=directory,
    )

    state = create_initial_state("backend", "staging")
    proposal = IssueProposal(
        run_id=42,
        service="backend",
        title="Investigate backend CI failure",
        description="The health test received HTTP 503.",
    )
    state["issue_proposal"] = proposal
    state["approval_decision"] = "approved"

    update = nodes.create_approved_issue(state)

    issue = update["created_issue"]
    path = directory / f"{state['issue_request_id']}.json"

    assert path.exists()

    saved = CreatedIssue.model_validate_json(
        path.read_text(encoding="utf-8")
    )

    assert saved == issue
    assert saved.issue_id == state["issue_request_id"]
    assert saved.run_id == proposal.run_id
    assert saved.service == proposal.service
    assert saved.title == proposal.title
    assert saved.description == proposal.description
    assert "errors" not in update

@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_approval_routes_to_write_only_when_approved(
    tmp_path: Path,
    decision: str,
) -> None:
    directory = tmp_path / "issues"
    client = AsyncMock(spec=Client)
    nodes = InvestigationNodes(
        client,
        permissions=AgentPermissions(can_create_issue=True),
        issue_directory=directory,
    )

    builder = StateGraph(InvestigationState)
    builder.add_node("request_approval", nodes.request_approval)
    builder.add_node("create_issue", nodes.create_approved_issue)
    builder.add_edge(START, "request_approval")
    builder.add_conditional_edges(
        "request_approval",
        route_after_approval,
        {
            "create_issue": "create_issue",
            "finish": END,
        },
    )
    builder.add_edge("create_issue", END)

    graph = builder.compile(
        checkpointer=InMemorySaver(serde=create_serializer())
    )
    config = {"configurable": {"thread_id": "approval-write-test"}}

    state = create_initial_state("backend", "staging")
    state["issue_proposal"] = IssueProposal(
        run_id=42,
        service="backend",
        title="Investigate backend CI failure",
        description="The health test received HTTP 503.",
    )

    graph.invoke(state, config=config)

    assert not directory.exists()

    completed = graph.invoke(
        Command(resume=decision),
        config=config,
    )

    assert completed["approval_decision"] == decision
    assert completed["errors"] == []
    assert graph.get_state(config).next == ()

    if decision == "approved":
        issue = completed["created_issue"]
        assert issue is not None
        assert (directory / f"{issue.issue_id}.json").exists()
    else:
        assert completed["created_issue"] is None
        assert not directory.exists()

    client.call_tool.assert_not_called()