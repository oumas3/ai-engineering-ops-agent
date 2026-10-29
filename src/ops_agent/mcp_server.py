from pathlib import Path

from mcp.server import MCPServer

from ops_agent.models import CIResult, LogsReport , ServiceStatus
from ops_agent.models import CIResult, FailedTestsReport

from ops_agent.tools import (
    get_ci_status as load_ci_status,
    get_failed_tests as load_failed_tests,
    read_logs as load_logs,
    get_service_status as load_service_status
)
import os
from uuid import UUID

server = MCPServer("Engineering Operations")

PROJECT_DIR = Path(__file__).resolve().parents[2]
selected_run = os.environ.get("OPS_REPORT_RUN")

if selected_run is None:
    DATA_DIR = PROJECT_DIR / "data"
else:
    run_folder = UUID(selected_run).hex
    DATA_DIR = PROJECT_DIR / "runtime" / "runs" / run_folder

@server.tool()
def get_ci_status() -> CIResult:
    """Read the CI status from the local demonstration report."""
    return load_ci_status(DATA_DIR / "ci_run.json")

@server.tool()
def get_failed_tests() -> FailedTestsReport:
    """Read failed-test details from the local demonstration report."""
    return load_failed_tests(DATA_DIR / "failed_tests.json")

@server.tool()
def read_logs() -> LogsReport:
    """Read application logs from the local demonstration report."""
    return load_logs(DATA_DIR / "logs.json")

@server.tool()
def get_service_status() -> ServiceStatus:
    """Read the service status from the local demonstration report."""
    return load_service_status(DATA_DIR / "service_status.json")        


if __name__ == "__main__":
    server.run(transport="stdio")