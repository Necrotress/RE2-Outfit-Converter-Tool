"""Game build convert: direction text and a mod with no Claire or Leon outfit."""

from __future__ import annotations

import struct
import zipfile
from pathlib import Path

from re2_outfit_converter.analyzer import analyze, game_build_direction
from re2_outfit_converter.converter import convert_game_build


def _classic_tex() -> bytes:
    payload = b"PX"
    header = 48
    buf = bytearray(header + len(payload))
    buf[0:4] = b"TEX\x00"
    struct.pack_into("<I", buf, 4, 10)
    struct.pack_into("<HHH", buf, 8, 4, 4, 0)
    buf[14] = 1
    buf[15] = 1
    struct.pack_into("<IIII", buf, 16, 98, 0, 0, 0)
    struct.pack_into("<QII", buf, 32, header, 16, len(payload))
    buf[header:] = payload
    return bytes(buf)


def test_game_build_direction_text():
    assert game_build_direction("Classic", "Ray tracing") == (
        "Classic to ray tracing")
    assert game_build_direction("Ray tracing", "Classic") == (
        "Ray tracing to Classic")
    assert game_build_direction("Classic", "Classic") == "No build change"
    assert game_build_direction("Ray tracing", "Ray tracing") == (
        "No build change")


def test_a_mod_without_an_outfit_converts_to_stm(tmp_path: Path):
    root = tmp_path / "emily"
    rel = Path("natives/x64/sectionroot/character/player/pl2000")
    (root / rel).mkdir(parents=True)
    (root / rel / "note.tex.10").write_bytes(_classic_tex())
    (root / "modinfo.ini").write_text("name=Emily\n", encoding="utf-8")
    analysis = analyze(root)
    assert not (analysis.outfits or analysis.claire_outfits)
    assert analysis.game_label == "Classic"

    report = convert_game_build(
        analysis, tmp_path / "out",
        game_build="Ray tracing",
        source_name="Emily",
        write_log=False,
        settings={"use_blender": False, "blender_path": ""},
    )
    assert report.output_zip is not None
    assert report.output_zip.is_file()
    with zipfile.ZipFile(report.output_zip) as zf:
        names = zf.namelist()
    assert any(
        name.startswith("natives/stm/") and name.endswith("note.tex.34")
        for name in names)
    assert not any("/x64/" in name for name in names)
    assert not any("pl1000" in name.lower() for name in names)
