"""'98 Classic is detected but not offered as a conversion target."""

import pytest

from re2_outfit_converter.analyzer import analyze
from re2_outfit_converter.converter import ConversionError, convert
from re2_outfit_converter.msg_name import MSG_DIR_DLC, apply_outfit_display_name
from re2_outfit_converter.outfits import (
    CLAIRE_OUTFIT_BY_KEY,
    CONVERTIBLE_OUTFITS,
    EXCLUSIVE_PART_IDS,
    UNSUPPORTED_CONVERT_KEYS,
    is_convertible_outfit,
)
from re2_outfit_converter.paths import MESH_ROOTS, PARTS_DIR
from pathlib import Path


def test_98_excluded_from_convertible_outfits():
    assert "98" in UNSUPPORTED_CONVERT_KEYS
    assert all(o.key != "98" for o in CONVERTIBLE_OUTFITS)
    assert not is_convertible_outfit(CLAIRE_OUTFIT_BY_KEY["98"])
    assert "pl1057" not in EXCLUSIVE_PART_IDS


def test_convert_to_98_raises(tmp_path: Path):
    root = tmp_path / "ElzaMod"
    parts = root / PARTS_DIR
    parts.mkdir(parents=True)
    (parts / "pl1000_body_costume_c.pfb.16").write_bytes(b"body")
    mesh = root / MESH_ROOTS[0]
    (mesh / "pl1004").mkdir(parents=True)
    (mesh / "pl1004" / "pl1004.mesh.1").write_bytes(b"mesh")
    (root / "modinfo.ini").write_text("Name=ElzaMod\n", encoding="utf-8")

    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(ConversionError, match="not supported"):
        convert(
            analyze(root),
            CLAIRE_OUTFIT_BY_KEY["elza"],
            CLAIRE_OUTFIT_BY_KEY["98"],
            out,
            tag_output=False,
            as_folder=True,
            folder_name="Nope",
        )


def test_98_display_name_writes_original_msg(tmp_path: Path):
    ops = apply_outfit_display_name(tmp_path, "original", "Nurse Claire")
    dest = tmp_path / MSG_DIR_DLC / "mes_sys_clairecos_original.msg.14"
    assert dest.is_file()
    assert any("mes_sys_clairecos_original.msg.14" in op for op in ops)
