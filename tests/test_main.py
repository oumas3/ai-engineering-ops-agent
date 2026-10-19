from ops_agent.main import main


def test_main_handles_missing_report(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    main()

    output = capsys.readouterr().out
    assert "report not found" in output
    assert "Service:" not in output