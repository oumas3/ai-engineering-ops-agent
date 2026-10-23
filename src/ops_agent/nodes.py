from mcp import Client
from pydantic import ValidationError

from ops_agent.models import (
    CIResult,
    FailedTestsReport,
    LogsReport,
    ServiceStatus,
)  
from ops_agent.state import InvestigationState


class InvestigationNodes:
    def __init__(self, client: Client) -> None:
        self.client = client

    async def collect_ci(
        self,
        state: InvestigationState,
    ) -> dict[str, object]:
        response = await self.client.call_tool("get_ci_status", {})

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

        response = await self.client.call_tool("get_failed_tests", {})

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

        response = await self.client.call_tool("read_logs", {})

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
        response = await self.client.call_tool("get_service_status", {})

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