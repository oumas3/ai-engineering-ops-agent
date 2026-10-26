import asyncio
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters

from ops_agent.models import (
    CIResult,
    FailedTestsReport,
    LogsReport,
    ServiceStatus,
)


async def main() -> None:
    src_dir = Path(__file__).resolve().parents[1]

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ops_agent.mcp_server"],
        env={"PYTHONPATH": str(src_dir)},
    )

    target_environment = "staging"

    async with Client(params) as client:
        # Discover the tools exposed by the server.
        result = await client.list_tools()

        for tool in result.tools:
            print(f"Available tool: {tool.name}")

        # Read and validate CI status.
        response = await client.call_tool("get_ci_status", {})

        if response.is_error:
            print("CI tool failed:", response.content)
            return

        ci = CIResult.model_validate(response.structured_content)
        print(f"CI run {ci.run_id}: {ci.status} ({ci.service})")

        if ci.status == "failed":
            # Read failed-test details.
            response = await client.call_tool("get_failed_tests", {})

            if response.is_error:
                print("Failed-tests tool failed:", response.content)
                return

            report = FailedTestsReport.model_validate(
                response.structured_content
            )

            if report.run_id != ci.run_id:
                print(
                    "Cannot use failed-test details: "
                    "CI run IDs do not match."
                )
                return

            if not report.tests:
                print("No failed-test details are available.")
            else:
                for test in report.tests:
                    print(f"- {test.name}: {test.message}")

            # Read application logs.
            log_response = await client.call_tool("read_logs", {})

            if log_response.is_error:
                print("Logs tool failed:", log_response.content)
                return

            logs = LogsReport.model_validate(
                log_response.structured_content
            )

            if logs.run_id != ci.run_id or logs.service != ci.service:
                print("Cannot use logs: CI run or service does not match.")
                return

            if not logs.entries:
                print("No log entries are available.")
            else:
                for entry in logs.entries:
                    print(f"[{entry.level}] {entry.message}")

            # Read service health.
            service_response = await client.call_tool(
                "get_service_status", {}
            )

            if service_response.is_error:
                print("Service-status tool failed:", service_response.content)
                return

            health = ServiceStatus.model_validate(
                service_response.structured_content
            )

            if (
                health.service != ci.service
                or health.environment != target_environment
            ):
                print(
                    "Cannot use service status: "
                    "service or environment does not match."
                )
                return

            print(
                f"Service health: {health.status} "
                f"({health.service}, {health.environment})"
            )


if __name__ == "__main__":
    asyncio.run(main())  