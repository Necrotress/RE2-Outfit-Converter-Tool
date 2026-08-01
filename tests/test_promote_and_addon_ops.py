"""Promote-before-strip and AddonFor Delete→remap regressions."""

from __future__ import annotations

import zipfile
from pathlib import Path

from re2_outfit_converter.analyzer import analyze
from re2_outfit_converter.converter import convert_batch, convert_with_ops
from re2_outfit_converter.outfit_ops import OutfitOp, adapt_ops_for_package
from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
from re2_outfit_converter.paths import MESH_ROOTS
from re2_outfit_converter.reports import BatchItem

from tests.fixtures import (
    build_tank_dress_tex_addon,
    build_tifa_dual_slot_dress,
)


def test_adapt_ops_tank_addon_becomes_convert(tmp_path: Path):
    addon = analyze(build_tank_dress_tex_addon(tmp_path))
    jacket = CLAIRE_OUTFIT_BY_KEY["jacket"]
    tank = CLAIRE_OUTFIT_BY_KEY["tanktop"]
    noir = CLAIRE_OUTFIT_BY_KEY["noir"]
    adapted = adapt_ops_for_package(
        addon,
        [
            OutfitOp(source=jacket, target=noir),
            OutfitOp(source=tank, target=None),
        ],
    )
    assert len(adapted) == 1
    assert adapted[0].source.key == "tanktop"
    assert adapted[0].target is not None
    assert adapted[0].target.key == "noir"


def test_jacket_to_noir_delete_tank_keeps_dress_textures(tmp_path: Path):
    """Tifa-style: textures under Tank must survive Jacket→Noir + Delete Tank."""
    root = build_tifa_dual_slot_dress(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    jacket = CLAIRE_OUTFIT_BY_KEY["jacket"]
    tank = CLAIRE_OUTFIT_BY_KEY["tanktop"]
    noir = CLAIRE_OUTFIT_BY_KEY["noir"]
    report = convert_with_ops(
        analyze(root),
        [
            OutfitOp(source=jacket, target=noir),
            OutfitOp(source=tank, target=None),
        ],
        out,
        tag_output=False,
        as_folder=True,
        folder_name="TifaNoir",
    )
    folder = report.output_folder
    assert folder is not None
    mesh = folder / MESH_ROOTS[0]
    assert (mesh / "pl1005").is_dir()
    assert not (mesh / "pl1001").exists()
    assert not (mesh / "pl1000").exists()
    dress = list((mesh / "pl1005").glob("*dress*"))
    assert dress, "dress textures should be promoted onto Noir body"
    assert any("promote deleted" in op for op in report.rename_ops)


def test_batch_texture_addon_survives_delete_tank(tmp_path: Path):
    main = analyze(build_tifa_dual_slot_dress(tmp_path))
    addon = analyze(build_tank_dress_tex_addon(
        tmp_path, addon_for="Tifa Dual Dress"))
    out = tmp_path / "out"
    out.mkdir()
    jacket = CLAIRE_OUTFIT_BY_KEY["jacket"]
    tank = CLAIRE_OUTFIT_BY_KEY["tanktop"]
    noir = CLAIRE_OUTFIT_BY_KEY["noir"]
    report = convert_batch(
        [
            BatchItem(analysis=main, label="Main"),
            BatchItem(analysis=addon, label="Color"),
        ],
        jacket,
        noir,
        out,
        "TifaBundle",
        tag_output=False,
        ops=[
            OutfitOp(source=jacket, target=noir),
            OutfitOp(source=tank, target=None),
        ],
    )
    assert report.output_zip is not None
    assert len(report.items) == 2
    with zipfile.ZipFile(report.output_zip) as zf:
        names = zf.namelist()
    dress_on_noir = [
        n for n in names
        if "pl1005" in n.replace("\\", "/") and "dress" in n.lower()
    ]
    assert dress_on_noir, (
        "main and/or addon dress textures should land under pl1005"
    )
    assert not any(
        "/pl1001/" in n.replace("\\", "/") and "dress" in n.lower()
        for n in names
    )
