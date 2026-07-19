"""Archive zip-slip and containment checks."""

import zipfile
from pathlib import Path

import pytest

from re2_outfit_converter.archive import ExtractError, _assert_extract_contained, _safe_extract_zip


def test_safe_extract_rejects_zip_slip(tmp_path: Path):
    zpath = tmp_path / "bad.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("../evil.txt", "nope")
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(ExtractError, match="Unsafe path"):
        _safe_extract_zip(zpath, dest)


def test_assert_extract_contained_ok(tmp_path: Path):
    (tmp_path / "ok.txt").write_text("x", encoding="utf-8")
    _assert_extract_contained(tmp_path, "x.zip")
