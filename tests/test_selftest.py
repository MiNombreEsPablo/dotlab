from t003gui import selftest


def test_selftest_passes(capsys):
    assert selftest.run() == 0
    assert "selftest ok" in capsys.readouterr().out


def test_selftest_log_file(monkeypatch, tmp_path):
    log = tmp_path / "selftest.log"
    monkeypatch.setenv("T003_SELFTEST_LOG", str(log))
    assert selftest.run() == 0
    assert "selftest ok" in log.read_text(encoding="utf-8")
