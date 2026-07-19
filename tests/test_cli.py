"""CLI smoke tests (no GUI)."""

from pathlib import Path

from re2_outfit_converter.cli import main
from tests.fixtures import build_elza_full


def test_cli_list_outfits():
    assert main(["list-outfits"]) == 0


def test_cli_analyze_and_convert(tmp_path: Path, capsys):
    root = build_elza_full(tmp_path)
    assert main(["analyze", str(root)]) == 0
    out = tmp_path / "out"
    rc = main([
        "convert", str(root),
        "--from", "elza", "--to", "noir",
        "-o", str(out), "--folder", "--no-tag",
    ])
    assert rc == 0
    captured = capsys.readouterr()
    assert "Saved:" in captured.out
    assert list(out.iterdir())
