from pathlib import Path
from pydantic import ValidationError

from ops_agent.tools import get_ci_status


def main() -> None:
    path = Path("data/ci_run.json")

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


if __name__ == "__main__":
    main()