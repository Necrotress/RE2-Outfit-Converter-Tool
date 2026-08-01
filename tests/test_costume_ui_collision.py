"""Costume-select preview remaps when both Jacket and Tank UI ship."""

from pathlib import Path

from re2_outfit_converter.analyzer import analyze
from re2_outfit_converter.converter import convert_with_ops
from re2_outfit_converter.costume_ui import convert_costume_ui
from re2_outfit_converter.outfit_ops import OutfitOp
from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
from re2_outfit_converter.paths import MESH_ROOTS, PARTS_DIR
from re2_outfit_converter.reports import ConversionReport
from tests.fixtures import UI_ROOT, write_modinfo


def _dual_preview_mod(tmp_path: Path) -> Path:
    root = tmp_path / "dual_ui"
    parts = root / PARTS_DIR
    parts.mkdir(parents=True)
    (parts / "pl1000_body_default.pfb.16").write_bytes(b"jacket")
    (parts / "pl1000_body_costume_3.pfb.16").write_bytes(b"tank")
    mesh = root / MESH_ROOTS[0]
    for pid, payload in (("pl1000", b"j"), ("pl1001", b"t")):
        d = mesh / pid
        d.mkdir(parents=True)
        (d / f"{pid}.mesh.1").write_bytes(payload)
        (d / f"{pid}.mdf2.10").write_bytes(payload + b"-mdf")
    ui = root / UI_ROOT
    (ui / "prefab").mkdir(parents=True)
    (ui / "tex").mkdir(parents=True)
    (ui / "prefab" / "ui0601_01_00.pfb.16").write_bytes(b"jacket-preview")
    (ui / "tex" / "ui0601_01_00_iam.tex.10").write_bytes(b"jacket-tex")
    (ui / "prefab" / "ui0601_01_02.pfb.16").write_bytes(b"tank-preview")
    (ui / "tex" / "ui0601_01_02_iam.tex.10").write_bytes(b"tank-tex")
    write_modinfo(root, Name="Dual Preview")
    return root


def test_remap_prefers_incoming_when_target_preview_exists(tmp_path: Path):
    staging = tmp_path / "stage"
    ui = staging / UI_ROOT
    (ui / "tex").mkdir(parents=True)
    (ui / "tex" / "ui0601_01_00_iam.tex.10").write_bytes(b"jacket-tex")
    (ui / "tex" / "ui0601_01_02_iam.tex.10").write_bytes(b"tank-tex")
    report = ConversionReport()
    convert_costume_ui(
        staging,
        [CLAIRE_OUTFIT_BY_KEY["jacket"]],
        CLAIRE_OUTFIT_BY_KEY["tanktop"],
        {},
        report,
    )
    tex = ui / "tex" / "ui0601_01_02_iam.tex.10"
    assert tex.read_bytes() == b"jacket-tex"
    assert not (ui / "tex" / "ui0601_01_00_iam.tex.10").exists()
    assert any("Replaced existing costume preview" in w for w in report.warnings)


def test_jacket_to_tank_delete_tank_keeps_jacket_preview(tmp_path: Path):
    """End-to-end: Jacket→Tank + Delete Tank ships Jacket preview on Tank id."""
    root = _dual_preview_mod(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    report = convert_with_ops(
        analyze(root),
        [
            OutfitOp(
                source=CLAIRE_OUTFIT_BY_KEY["jacket"],
                target=CLAIRE_OUTFIT_BY_KEY["tanktop"],
            ),
            OutfitOp(source=CLAIRE_OUTFIT_BY_KEY["tanktop"], target=None),
        ],
        out,
        tag_output=False,
        as_folder=True,
        folder_name="J2T",
    )
    folder = report.output_folder
    assert folder is not None
    tex = folder / UI_ROOT / "tex" / "ui0601_01_02_iam.tex.10"
    assert tex.is_file()
    assert tex.read_bytes() == b"jacket-tex"
    assert not list(folder.rglob("ui0601_01_00*"))
