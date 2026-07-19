"""Unit tests for same-length binary path overlays."""

from pathlib import Path

from re2_outfit_converter.path_patch import (
    overlay,
    patch_ascii_ci,
    patch_binaries,
    patch_utf16_ci,
    utf16_ascii_lower,
)
from re2_outfit_converter.reports import ConversionReport


def test_overlay_preserves_case_of_unchanged_chars():
    # Unchanged letters keep matched casing; replacements use `new` as written.
    assert overlay(b"AbCd", "abcd", "abXd", 1) == b"AbXd"


def test_patch_ascii_ci():
    data = b"xxxSECTIONROOT/pl1070/pl1070.mdf2yyy"
    lower = data.lower()
    old = "sectionroot/pl1070/pl1070.mdf2"
    new = "sectionroot/pl1800/pl1800.mdf2"
    needle = old.lower().encode("ascii")
    out, n = patch_ascii_ci(data, lower, old, new, needle)
    assert n == 1
    assert b"pl1800" in out
    assert b"pl1070" not in out


def test_patch_utf16_ci():
    old = "pl1070"
    new = "pl1800"
    u16 = b"".join(bytes([ord(c), 0]) for c in old)
    data = b"xx" + u16 + b"yy"
    view = utf16_ascii_lower(data)
    needle = b"".join(bytes([ord(c), 0]) for c in old.lower())
    out, n = patch_utf16_ci(data, view, old, new, needle)
    assert n == 1
    assert b"p\x00l\x001\x008\x000\x000" in out


def test_patch_binaries_warns_on_length_mismatch(tmp_path: Path):
    report = ConversionReport()
    f = tmp_path / "x.mdf2"
    f.write_bytes(b"sectionroot/pl1070/pl1070.mdf2")
    patch_binaries(tmp_path, {"short": "toolong"}, report)
    assert any("length mismatch" in w for w in report.warnings)
    assert any("Binary path patch:" in w for w in report.warnings)


def test_patchable_allowlist():
    from re2_outfit_converter.outfits import patchable

    assert patchable("pl1000.mdf2.10")
    assert patchable("thing.pfb.16")
    assert patchable("holder.scn.19")
    assert not patchable("skin.tex.10")
    assert not patchable("modinfo.ini")
    assert not patchable("readme.txt")


def test_patch_binaries_skips_oversized(tmp_path: Path, monkeypatch):
    import re2_outfit_converter.path_patch as pp

    monkeypatch.setattr(pp, "MAX_PATCH_FILE_BYTES", 8)
    report = ConversionReport()
    f = tmp_path / "big.mdf2"
    f.write_bytes(b"sectionroot/pl1070/pl1070.mdf2")
    patch_binaries(
        tmp_path,
        {"sectionroot/pl1070/pl1070.mdf2": "sectionroot/pl1800/pl1800.mdf2"},
        report,
    )
    assert any("too large" in w for w in report.warnings)
    assert b"pl1070" in f.read_bytes()
