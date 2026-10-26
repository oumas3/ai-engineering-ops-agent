from urllib import response

from mcp import Client, client
from pydantic import ValidationError
import asyncio
from mcp import Client
from ops_agent import state
from ops_agent.models import (
    CIResult,
    FailedTestsReport,
    LogsReport,
    ServiceStatus,
)  
from ops_agent.state import InvestigationState


from mcp.types import CallToolResult

class InvestigationNodes:
    def __init__(
        self,
        client: Client,
        timeout_seconds: float = 5.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")

        self.client = client
        self.timeout_seconds = timeout_seconds


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