from pathlib import Path
from ops_agent.models import CIResult
from pydantic import ValidationError

from ops_agent.tools import get_ci_status , get_failed_tests, get_service_status , read_logs


def main() -> None:
    path = Path("data/ci_run.json")
    target_environment = "staging"

    try:
        result = get_ci_status(path)
    except FileNotFoundError:
        print(f"Cannot read CI status: report not found at {path}")
        return
    except ValidationError as error:
        print("Cannot read CI status: the report contains invalid data.")
        print(error)
        return

    print(f"Service: {result.service}")
    print(f"CI run: {result.run_id}")
    print(f"Status: {result.status}")
    if result.status == "failed":
     show_failed_tests(result)
     show_logs(result)
     show_service_status(result, target_environment)
   
def show_failed_tests(ci: CIResult) -> None:
    try:
        report = get_failed_tests(Path("data/failed_tests.json"))
    except FileNotFoundError:
        print("Failed-test report is missing.")
        return
    except ValidationError as error:
        print("Failed-test report contains invalid data.")
        print(error)
        return

    if report.run_id != ci.run_id:
        print("Cannot use failed-test details: CI run IDs do not match.")
        return

    if not report.tests:
        print("No failed-test details are available for this CI run.")
        return

    for test in report.tests:
        print(f"- {test.name}: {test.message}")



def show_logs(ci: CIResult) -> None:
    try:
        report = read_logs(Path("data/logs.json"))
    except FileNotFoundError:
        print("Log report is missing.")
        return
    except ValidationError as error:
        print("Log report contains invalid data.")
        print(error)
        return

    if report.run_id != ci.run_id or report.service != ci.service:
        print("Cannot use logs: CI run or service does not match.")
        return

    if not report.entries:
        print("No log entries are available for this CI run.")
        return

    for entry in report.entries:
        print(f"[{entry.level}] {entry.message}")

def show_service_status(ci: CIResult, environment: str) -> None:
    try:
        report = get_service_status(Path("data/service_status.json"))
    except FileNotFoundError:
        print("Service-status report is missing.")
        return
    except ValidationError as error:
        print("Service-status report contains invalid data.")
        print(error)
        return

    if report.service != ci.service or report.environment != environment:
        print("Cannot use service status: service or environment does not match.")
        return

    print(
        f"Service health: {report.status} "
        f"({report.service}, {report.environment})"
    )

if __name__ == "__main__":
    main()
    