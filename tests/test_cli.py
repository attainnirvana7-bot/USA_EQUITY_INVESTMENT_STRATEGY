from usequity.cli import main


def test_demo_screen_backtest(tmp_path, capsys):
    db = str(tmp_path / "demo.db")
    assert main(["--db", db, "demo"]) == 0
    assert main(["--db", db, "screen", "--top", "3"]) == 0
    assert "DEMO" in capsys.readouterr().out
    assert main(["--db", db, "backtest", "--start", "2020-01-01", "--output", str(tmp_path / "bt")]) == 0
    out = capsys.readouterr().out
    assert "年化報酬" in out and "基準" in out
    assert (tmp_path / "bt" / "equity.csv").exists()
