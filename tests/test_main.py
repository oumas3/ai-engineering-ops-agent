from ops_agent.main import main


def test_main_handles_missing_report(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    main()

    output = capsys.readouterr().out
    assert "report not found" in output
    assert "Service:" not in output
    
def test_main_rejects_mismatched_runs(tmp_path, monkeypatch, capsys) -> None:
    data = tmp_path / "data"
    data.mkdir()

    (data / "ci_run.json").write_text(
        '{"run_id": 42, "service": "backend", "status": "failed"}',
        encoding="utf-8",
    )

    (data / "failed_tests.json").write_text(
        """
        {
            "run_id": 99,
            "tests": [
                {
                    "name": "test_other_run",
                    "message": "Failure from another run."
                }
            ]
        }
        """,
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    main()

    output = capsys.readouterr().out
    assert "CI run IDs do not match" in output
    assert "test_other_run" not in output


def test_main_shows_logs_without_failed_tests(
    tmp_path, monkeypatch, capsys
) -> None:
    data = tmp_path / "data"
    data.mkdir()

    (data / "ci_run.json").write_text(
        '{"run_id": 42, "service": "backend", "status": "failed"}',
        encoding="utf-8",
    )

    (data / "logs.json").write_text(
        """
        {
            "run_id": 42,
            "service": "backend",
            "entries": [
                {
                    "level": "ERROR",
                    "message": "Database connection timed out."
                }
            ]
        }
        """,
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    main()

    output = capsys.readouterr().out
    assert "Failed-test report is missing." in output
    assert "[ERROR] Database connection timed out." in output
