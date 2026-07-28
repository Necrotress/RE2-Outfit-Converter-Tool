"""Multi-outfit map/delete ops and incomplete-slot detection."""

from __future__ import annotations

from pathlib import Path

from re2_outfit_converter.analyzer import analyze
from re2_outfit_converter.cli import main
from re2_outfit_converter.converter import convert_with_ops
from re2_outfit_converter.outfit_health import incomplete_outfits
from re2_outfit_converter.outfit_ops import OutfitOp
from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
from re2_outfit_converter.paths import MESH_ROOTS, PARTS_DIR

from tests.fixtures import build_casual_claire_style, build_elza_full


def test_incomplete_jacket_flagged_tank_ok(tmp_path: Path):
    root = build_casual_claire_style(tmp_path)
    analysis = analyze(root)
    reasons = incomplete_outfits(analysis)
    assert "jacket" in reasons
    assert "mesh" in reasons["jacket"].lower()
    assert "tanktop" not in reasons


def test_strip_jacket_leaves_tank(tmp_path: Path):
    root = build_casual_claire_style(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    jacket = CLAIRE_OUTFIT_BY_KEY["jacket"]
    tank = CLAIRE_OUTFIT_BY_KEY["tanktop"]
    report = convert_with_ops(
        analyze(root),
        [
            OutfitOp(source=jacket, target=None),
            OutfitOp(source=tank, target=tank),
        ],
        out,
        tag_output=False,
        as_folder=True,
        folder_name="KeepTank",
    )
    folder = report.output_folder
    assert folder is not None
    parts = folder / PARTS_DIR
    assert not (parts / "pl1000_body_default.pfb.16").exists()
    assert (parts / "pl1000_body_costume_3.pfb.16").is_file()
    mesh = folder / MESH_ROOTS[0]
    assert not (mesh / "pl1000").exists()
    assert (mesh / "pl1001").is_dir()
    assert any("stripped outfit slot jacket" in x for x in report.removed_ops)


def test_map_and_delete(tmp_path: Path):
    root = build_casual_claire_style(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    jacket = CLAIRE_OUTFIT_BY_KEY["jacket"]
    tank = CLAIRE_OUTFIT_BY_KEY["tanktop"]
    noir = CLAIRE_OUTFIT_BY_KEY["noir"]
    report = convert_with_ops(
        analyze(root),
        [
            OutfitOp(source=jacket, target=None),
            OutfitOp(source=tank, target=noir),
        ],
        out,
        tag_output=False,
        as_folder=True,
        folder_name="TankToNoir",
    )
    folder = report.output_folder
    assert folder is not None
    parts = folder / PARTS_DIR
    assert not (parts / "pl1000_body_default.pfb.16").exists()
    assert (parts / "pl1000_body_costume_a.pfb.16").is_file()
    mesh = folder / MESH_ROOTS[0]
    assert (mesh / "pl1005").is_dir()
    assert not (mesh / "pl1001").exists()


def test_two_maps_different_targets(tmp_path: Path):
    root = build_elza_full(tmp_path)
    # Add a Tank slot alongside Elza so we have two convert sources.
    parts = root / PARTS_DIR
    (parts / "pl1000_body_costume_3.pfb.16").write_bytes(b"tank")
    mesh = root / MESH_ROOTS[0]
    tank = mesh / "pl1001"
    tank.mkdir(parents=True)
    (tank / "pl1001.mesh.1").write_bytes(b"tank-mesh")

    out = tmp_path / "out"
    out.mkdir()
    elza = CLAIRE_OUTFIT_BY_KEY["elza"]
    tanktop = CLAIRE_OUTFIT_BY_KEY["tanktop"]
    noir = CLAIRE_OUTFIT_BY_KEY["noir"]
    military = CLAIRE_OUTFIT_BY_KEY["military"]
    report = convert_with_ops(
        analyze(root),
        [
            OutfitOp(source=elza, target=noir),
            OutfitOp(source=tanktop, target=military),
        ],
        out,
        tag_output=False,
        as_folder=True,
        folder_name="DualMap",
    )
    folder = report.output_folder
    assert folder is not None
    parts = folder / PARTS_DIR
    assert (parts / "pl1000_body_costume_a.pfb.16").is_file()
    assert (parts / "pl1000_body_costume_b.pfb.16").is_file()
    mesh = folder / MESH_ROOTS[0]
    assert (mesh / "pl1005").is_dir()
    assert (mesh / "pl1006").is_dir()
    # Per-target exclusive hair hide must inject redirects for both slots.
    assert (parts / "pl1000_hair_costume_a.pfb.16").is_file()
    assert (parts / "pl1000_hair_costume_b.pfb.16").is_file()
    # Multi-target MSG sync must keep both clairecos files (not last-wins).
    from re2_outfit_converter.msg_name import MSG_DIR_DLC
    msg = folder / MSG_DIR_DLC
    assert (msg / "mes_sys_clairecos_noir.msg.14").is_file()
    assert (msg / "mes_sys_clairecos_military.msg.14").is_file()


def test_cli_map_delete(tmp_path: Path, capsys):
    root = build_casual_claire_style(tmp_path)
    out = tmp_path / "out"
    rc = main([
        "convert", str(root),
        "--delete", "jacket",
        "--map", "tanktop:tanktop",
        "-o", str(out), "--folder", "--no-tag",
    ])
    assert rc == 0
    captured = capsys.readouterr()
    assert "Saved:" in captured.out


def test_cli_analyze_incomplete_warning(tmp_path: Path, capsys):
    root = build_casual_claire_style(tmp_path)
    assert main(["analyze", str(root)]) == 0
    captured = capsys.readouterr()
    assert "incomplete" in captured.out.lower()
    assert "Jacket" in captured.out or "jacket" in captured.out.lower()
