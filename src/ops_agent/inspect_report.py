import argparse
from pathlib import Path

from ops_agent.report_parser import parse_failed_tests


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--run-id", type=int, required=True)
    args = parser.parse_args()

    report = parse_failed_tests(
        path=args.path,
        run_id=args.run_id,
    )

    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    main()