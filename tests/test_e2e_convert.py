"""Full-pipeline end-to-end conversion tests on synthetic Fluffy trees."""

from __future__ import annotations

import zipfile
from pathlib import Path

from re2_outfit_converter.analyzer import analyze
from re2_outfit_converter.converter import convert, convert_batch
from re2_outfit_converter.isolation import isolation_seed
from re2_outfit_converter.msg_name import MSG_DIR_DLC, read_english_name
from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
from re2_outfit_converter.paths import MESH_ROOTS, PARTS_DIR
from re2_outfit_converter.reports import BatchItem

from tests.fixtures import (
    build_elza_full,
    build_elza_main,
    build_face_addon,
    build_nurse_style,
)


def test_e2e_elza_to_noir_full_pipeline(tmp_path: Path):
    root = build_elza_full(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    elza = CLAIRE_OUTFIT_BY_KEY["elza"]
    noir = CLAIRE_OUTFIT_BY_KEY["noir"]

    report = convert(
        analyze(root), elza, noir, out,
        tag_output=False, as_folder=True, folder_name="NoirE2E",
    )
    folder = report.output_folder
    assert folder is not None

    parts = folder / PARTS_DIR
    assert (parts / "pl1000_body_costume_a.pfb.16").is_file()
    assert not (parts / "pl1000_body_costume_c.pfb.16").exists()

    mesh = folder / MESH_ROOTS[0]
    assert (mesh / "pl1005").is_dir()
    assert not (mesh / "pl1004").exists()
    # Face/hair isolated off shared IDs
    assert not (mesh / "pl1050").exists()
    assert not (mesh / "pl1070").exists()
    private = [p for p in mesh.iterdir() if p.is_dir() and p.name.lower().startswith("pl18")]
    assert len(private) >= 1

    assert list(folder.rglob("ui0601_01_07_iam.tex*"))
    assert not list(folder.rglob("ui0601_01_08*"))

    msg = folder / MSG_DIR_DLC / "mes_sys_clairecos_noir.msg.14"
    assert msg.is_file()
    assert read_english_name(msg) == "E2E Rich Girl"
    assert not list(folder.rglob("mes_sys_clairecos_elza*"))
    assert not list(folder.rglob("contentsholder_dlc*"))

    # Planted binary path remapped pl1004 → pl1005
    planted = next(folder.rglob("ref_pl1004.mdf2*"))
    data = planted.read_bytes()
    assert b"pl1005" in data
    assert b"pl1004/pl1004" not in data
    assert "pl1005".encode("utf-16-le") in data

    assert report.pfb_ops
    assert report.patch_ops or any("path" in w.lower() for w in report.warnings)


def test_e2e_nurse_style_elza_to_military(tmp_path: Path):
    root = build_nurse_style(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    report = convert(
        analyze(root),
        CLAIRE_OUTFIT_BY_KEY["elza"],
        CLAIRE_OUTFIT_BY_KEY["military"],
        out,
        tag_output=False, as_folder=True, folder_name="MilNurse",
    )
    folder = report.output_folder
    assert folder is not None
    mesh = folder / MESH_ROOTS[0]
    assert not (mesh / "pl1004").exists()
    assert (mesh / "pl1006").is_dir()
    # Custom body retargeted onto military id
    custom_left = list((mesh / "pl1000").rglob("*pl1008*")) if (mesh / "pl1000").is_dir() else []
    assert not custom_left
    assert list(folder.rglob("ui0601_01_06*"))
    assert not list(folder.rglob("ui0601_01_08*"))


def test_e2e_classic_stash_round_trip(tmp_path: Path):
    root = build_elza_full(tmp_path)
    mid = tmp_path / "mid"
    mid.mkdir()
    classic = convert(
        analyze(root),
        CLAIRE_OUTFIT_BY_KEY["elza"],
        CLAIRE_OUTFIT_BY_KEY["classic_jacket"],
        mid,
        tag_output=False, as_folder=True, folder_name="ClassicMid",
    ).output_folder
    assert classic is not None
    assert list(classic.rglob("_re2oc_ui_stash/ui0601_01_08*"))

    out = tmp_path / "out"
    out.mkdir()
    back = convert(
        analyze(classic),
        CLAIRE_OUTFIT_BY_KEY["classic_jacket"],
        CLAIRE_OUTFIT_BY_KEY["elza"],
        out,
        tag_output=False, as_folder=True, folder_name="ElzaBack",
    ).output_folder
    assert back is not None
    assert list(back.rglob("ui0601_01_08_iam.tex*"))
    assert not list(back.rglob("_re2oc_ui_stash/**"))


def test_e2e_batch_main_plus_orphan_addon(tmp_path: Path):
    main_root = build_elza_main(tmp_path)
    addon_root = build_face_addon(tmp_path)
    main = analyze(main_root)
    addon = analyze(addon_root)
    out = tmp_path / "out"
    out.mkdir()

    report = convert_batch(
        [
            BatchItem(analysis=main, label="Main"),
            BatchItem(analysis=addon, label="Addon"),
        ],
        CLAIRE_OUTFIT_BY_KEY["elza"],
        CLAIRE_OUTFIT_BY_KEY["noir"],
        out,
        "E2E Bundle",
        tag_output=False,
    )
    assert report.output_zip is not None
    assert report.output_zip.is_file()
    assert len(report.items) == 2
    assert addon.modinfo.addonfor == "E2E Main Elza"
    assert isolation_seed(addon) == isolation_seed(main)

    with zipfile.ZipFile(report.output_zip) as zf:
        names = zf.namelist()
    assert any("natives/" in n for n in names)
    assert any(n.lower().endswith("modinfo.ini") for n in names)
