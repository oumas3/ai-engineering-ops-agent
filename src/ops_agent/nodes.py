from urllib import response

from mcp import Client, client
from pydantic import ValidationError
import asyncio
from mcp import Client
from ops_agent import state
from ops_agent.models import (
    AgentPermissions,
    CIResult,
    FailedTestsReport,
    IssueProposal,
    LogsReport,
    ServiceStatus,
)  
from ops_agent.state import InvestigationState
from langgraph.types import interrupt
from mcp.types import CallToolResult
from pathlib import Path
from uuid import UUID

from ops_agent.tools import create_issue

class InvestigationNodes:
    def __init__(
        self,
        client: Client,
        timeout_seconds: float = 5.0,
        permissions: AgentPermissions | None = None,
        issue_directory: Path | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")

        self.client = client
        self.timeout_seconds = timeout_seconds

        self.permissions = (
            permissions
            if permissions is not None
            else AgentPermissions()
        )

        self.issue_directory = (
            issue_directory
            if issue_directory is not None
            else Path(__file__).resolve().parents[2] / "runtime" / "issues"
        )

    async def _call_read_tool(self, name: str) -> CallToolResult:
        try:
            async with asyncio.timeout(self.timeout_seconds):
                return await self.client.call_tool(name, {})
        except TimeoutError:
            pass

        async with asyncio.timeout(self.timeout_seconds):
            return await self.client.call_tool(name, {})
        
    async def collect_ci(
        self,
        state: InvestigationState,
    ) -> dict[str, object]:
        try:
            response = await self._call_read_tool("get_ci_status")
        except TimeoutError:
            return {
                "ci": None,
                "errors": state["errors"] + [
                    "CI tool timed out."
                ],
            }

        if response.is_error:
            return {
                "ci": None,
                "errors": state["errors"] + ["CI tool execution failed."],
            }

        try:
            ci = CIResult.model_validate(response.structured_content)
        except ValidationError:
            return {
                "ci": None,
                "errors": state["errors"] + ["CI tool returned invalid data."],
            }

        if ci.service != state["service"]:
            return {
                "ci": None,
                "errors": state["errors"] + ["CI report service does not match."],
            }

        return {"ci": ci}
    async def collect_failed_tests(
        self,
        state: InvestigationState,
    ) -> dict[str, object]:
        ci = state["ci"]

        if ci is None:
            return {
                "failed_tests": None,
                "errors": state["errors"] + [
                    "Cannot collect failed tests without a CI report."
                ],
            }

        try:
            response = await self._call_read_tool("get_failed_tests")
        except TimeoutError:
            return {
                "failed_tests": None,
                "errors": state["errors"] + [
                    "Failed-tests tool timed out."
                ],
            }
        if response.is_error:
            return {
                "failed_tests": None,
                "errors": state["errors"] + [
                    "Failed-tests tool execution failed."
                ],
            }

        try:
            report = FailedTestsReport.model_validate(
                response.structured_content
            )
        except ValidationError:
            return {
                "failed_tests": None,
                "errors": state["errors"] + [
                    "Failed-tests tool returned invalid data."
                ],
            }

        if report.run_id != ci.run_id:
            return {
                "failed_tests": None,
                "errors": state["errors"] + [
                    "Failed-test report CI run ID does not match."
                ],
            }

        return {"failed_tests": report}
    async def collect_logs(
        self,
        state: InvestigationState,
    ) -> dict[str, object]:
        ci = state["ci"]

        if ci is None:
            return {
                "logs": None,
                "errors": state["errors"] + [
                    "Cannot collect logs without a CI report."
                ],
            }

        try:
            response = await self._call_read_tool("read_logs")
        except TimeoutError:
            return {
                "logs": None,
                "errors": state["errors"] + [
                    "Logs tool timed out."
                ],
            }
        if response.is_error:
            return {
                "logs": None,
                "errors": state["errors"] + [
                    "Logs tool execution failed."
                ],
            }

        try:
            report = LogsReport.model_validate(
                response.structured_content

            )
        except ValidationError:
            return {
                "logs": None,
                "errors": state["errors"] + [
                    "Logs tool returned invalid data."
                ],
            }

        if report.run_id != ci.run_id or report.service != ci.service:
            return {
                "logs": None,
                "errors": state["errors"] + [
                    "Log report CI run or service does not match."
                ],
            }

        return {"logs": report}
    async def collect_service_status(
        self,
        state: InvestigationState,
    ) -> dict[str, object]:
        try:
            response = await self._call_read_tool("get_service_status")
        except TimeoutError:
            return {
                "service_status": None,
                "errors": state["errors"] + [
                    "Service-status tool timed out."
                ],
            }
        if response.is_error:
            return {
                "service_status": None,
                "errors": state["errors"] + [
                    "Service-status tool execution failed."
                ],
            }

        try:
            report = ServiceStatus.model_validate(
                response.structured_content
            )
        except ValidationError:
            return {
                "service_status": None,
                "errors": state["errors"] + [
                    "Service-status tool returned invalid data."
                ],
            }

        if (
            report.service != state["service"]
            or report.environment != state["environment"]
        ):
            return {
                "service_status": None,
                "errors": state["errors"] + [
                    "Service-status report service or environment does not match."
                ],
            }

        return {"service_status": report}
    def prepare_issue(
        self,
        state: InvestigationState,
    ) -> dict[str, object]:
        ci = state["ci"]

        if ci is None or ci.status != "failed":
            return {"issue_proposal": None}

        lines = [
            f"Service: {ci.service}",
            f"CI run: {ci.run_id}",
            "CI status: failed",
        ]

        tests = state["failed_tests"]
        if tests is not None:
            for test in tests.tests:
                lines.append(f"Failed test: {test.name}: {test.message}")

        logs = state["logs"]
        if logs is not None:
            for entry in logs.entries:
                lines.append(f"Log [{entry.level}]: {entry.message}")

        health = state["service_status"]
        if health is not None:
            lines.append(
                f"Service health: {health.status} "
                f"({health.environment})"
            )

        for error in state["errors"]:
            lines.append(f"Collection limitation: {error}")

        lines.append(
            "Root cause is not established. "
            "Review the collected evidence before choosing a fix."
        )

        proposal = IssueProposal(
            run_id=ci.run_id,
            service=ci.service,
            title=f"Investigate {ci.service} CI run {ci.run_id} failure",
            description="\n".join(lines),
        )

        return {"issue_proposal": proposal}
    def request_approval(
        self,
        state: InvestigationState,
    ) -> dict[str, object]:
        proposal = state.get("issue_proposal")

        if proposal is None:
            return {
                "approval_decision": None,
                "errors": state["errors"] + [
                    "Cannot request approval without an issue proposal."
                ],
            }
        if not self.permissions.can_create_issue:
            return {
                "approval_decision": None,
                "errors": state["errors"] + [
                    "Issue creation is not permitted."
                ],
            }

        decision = interrupt(
            {
                "action": "create_issue",
                "proposal": proposal.model_dump(mode="json"),
                "choices": ["approved", "rejected"],
            }
        )

        if not isinstance(decision, str) or decision not in (
            "approved",
            "rejected",
        ):
            raise ValueError(
                "Approval decision must be 'approved' or 'rejected'."
            )

        return {"approval_decision": decision}

    def create_approved_issue(
        self,
        state: InvestigationState,
    ) -> dict[str, object]:
        if not self.permissions.can_create_issue:
            return {
                "errors": state["errors"] + [
                    "Issue creation is not permitted."
                ],
            }

        if state.get("approval_decision") != "approved":
            return {
                "errors": state["errors"] + [
                    "Issue creation requires explicit approval."
                ],
            }

        proposal = state.get("issue_proposal")
        request_id = state.get("issue_request_id")

        if proposal is None or request_id is None:
            return {
                "errors": state["errors"] + [
                    "Issue creation requires a proposal and request ID."
                ],
            }

        issue = create_issue(
            proposal=proposal,
            directory=self.issue_directory,
            request_id=UUID(request_id),
        )

        return {"created_issue": issue}