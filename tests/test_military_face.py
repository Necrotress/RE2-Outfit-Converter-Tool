"""Military clean-face seed and Tank Top Military-face strip."""

from pathlib import Path

from re2_outfit_converter.analyzer import AnalysisResult, ModInfo, PfbSlot, analyze
from re2_outfit_converter.converter import convert_with_ops
from re2_outfit_converter.military_face import (
    analysis_has_custom_face,
    ensure_military_clean_face,
    staging_has_custom_face,
)
from re2_outfit_converter.outfit_ops import OutfitOp
from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
from re2_outfit_converter.paths import MESH_ROOTS, PARTS_DIR
from re2_outfit_converter.reports import ConversionReport


def test_detects_face_pfb():
    analysis = AnalysisResult(
        claire_pfbs=[PfbSlot("face", "costume_c", "natives/x64/x.pfb.16")],
    )
    assert analysis_has_custom_face(analysis)


def test_detects_military_pl1050_04():
    analysis = AnalysisResult(
        natives_files=[
            "natives/x64/sectionroot/character/player/pl1000/pl1050/"
            "pl1050_04/pl1050_04_face_albm.tex.10",
        ],
    )
    assert analysis_has_custom_face(analysis)


def test_ignores_partial_pl1050_without_04():
    analysis = AnalysisResult(
        natives_files=[
            "natives/x64/sectionroot/character/player/pl1000/pl1050/pl1050.mesh.1",
            "natives/x64/sectionroot/character/player/pl1000/pl1050/"
            "pl1050_01/pl1050_01_face_albm.tex.10",
        ],
    )
    assert not analysis_has_custom_face(analysis)


def test_seeds_clean_face_for_military_without_custom(tmp_path: Path):
    staging = tmp_path
    report = ConversionReport()
    analysis = AnalysisResult(modinfo=ModInfo(name="BodyOnly"))
    ensure_military_clean_face(
        staging, CLAIRE_OUTFIT_BY_KEY["military"], analysis, report)
    assert list(staging.rglob("pl1050_04_face_albm.tex*"))
    assert any("seeded Claire default face" in op for op in report.rename_ops)


def test_skips_seed_when_staging_has_face_pfb(tmp_path: Path):
    staging = tmp_path
    parts = staging / PARTS_DIR
    parts.mkdir(parents=True)
    (parts / "pl1000_face_costume_c.pfb.16").write_bytes(b"face")
    report = ConversionReport()
    analysis = AnalysisResult()  # empty analysis — staging still wins
    ensure_military_clean_face(
        staging, CLAIRE_OUTFIT_BY_KEY["military"], analysis, report)
    assert not list(staging.rglob("pl1050_04*"))
    assert any("kept mod face data" in op for op in report.rename_ops)
    assert staging_has_custom_face(staging)


def test_non_seed_target_is_noop(tmp_path: Path):
    staging = tmp_path
    report = ConversionReport()
    analysis = AnalysisResult()
    ensure_military_clean_face(
        staging, CLAIRE_OUTFIT_BY_KEY["noir"], analysis, report)
    assert not list(staging.rglob("pl1050_04*"))
    assert not report.rename_ops
    assert not report.removed_ops


def test_tanktop_strips_existing_pl1050_04(tmp_path: Path):
    """Tank Top removes Military *_04 face leftovers (does not re-seed them)."""
    staging = tmp_path
    dirty = (
        staging / "natives/x64/sectionroot/character/player/pl1000/"
        "pl1050/pl1050_04/pl1050_04_face_albm.tex.10"
    )
    dirty.parent.mkdir(parents=True)
    dirty.write_bytes(b"DIRTY-FACE")
    stream = (
        staging / "natives/x64/streaming/sectionroot/character/player/"
        "pl1000/pl1050/pl1050_04/pl1050_04_face_albm.tex.10"
    )
    stream.parent.mkdir(parents=True)
    stream.write_bytes(b"DIRTY-FACE")
    report = ConversionReport()
    ensure_military_clean_face(
        staging, CLAIRE_OUTFIT_BY_KEY["tanktop"], AnalysisResult(), report)
    assert not list(staging.rglob("pl1050_04*"))
    assert any("stripped Military *_04 face textures" in op
               for op in report.rename_ops)
    assert any("removed Military face textures" in op
               for op in report.removed_ops)


def test_military_keeps_existing_pl1050_04(tmp_path: Path):
    staging = tmp_path
    dirty = (
        staging / "natives/x64/sectionroot/character/player/pl1000/"
        "pl1050/pl1050_04/pl1050_04_face_albm.tex.10"
    )
    dirty.parent.mkdir(parents=True)
    dirty.write_bytes(b"DIRTY-FACE")
    report = ConversionReport()
    ensure_military_clean_face(
        staging, CLAIRE_OUTFIT_BY_KEY["military"], AnalysisResult(), report)
    assert dirty.read_bytes() == b"DIRTY-FACE"
    assert any("kept mod face data" in op for op in report.rename_ops)


def test_delete_face_slot_still_seeds_military(tmp_path: Path):
    """Face PFB only on deleted Elza must not block Military clean-face seed."""
    root = tmp_path / "mod"
    parts = root / PARTS_DIR
    parts.mkdir(parents=True)
    (parts / "pl1000_body_default.pfb.16").write_bytes(b"jacket")
    (parts / "pl1000_body_costume_c.pfb.16").write_bytes(b"elza")
    (parts / "pl1000_face_costume_c.pfb.16").write_bytes(b"face-only-on-elza")
    mesh = root / MESH_ROOTS[0]
    jacket = mesh / "pl1000"
    jacket.mkdir(parents=True)
    (jacket / "pl1000.mesh.1").write_bytes(b"j-mesh")
    (jacket / "pl1000.mdf2.10").write_bytes(b"j-mdf")
    elza = mesh / "pl1004"
    elza.mkdir(parents=True)
    (elza / "pl1004.mesh.1").write_bytes(b"e-mesh")
    (root / "modinfo.ini").write_text("Name=FaceOnElza\n", encoding="utf-8")

    out = tmp_path / "out"
    out.mkdir()
    report = convert_with_ops(
        analyze(root),
        [
            OutfitOp(
                source=CLAIRE_OUTFIT_BY_KEY["jacket"],
                target=CLAIRE_OUTFIT_BY_KEY["military"],
            ),
            OutfitOp(source=CLAIRE_OUTFIT_BY_KEY["elza"], target=None),
        ],
        out,
        tag_output=False,
        as_folder=True,
        folder_name="MilFace",
    )
    folder = report.output_folder
    assert folder is not None
    assert list(folder.rglob("pl1050_04_face_albm.tex*")), (
        "Delete removed Elza face PFB; Military should still get clean face"
    )
    assert any("seeded Claire default face" in op for op in report.rename_ops)
    assert not list((folder / PARTS_DIR).glob("pl1000_face_*.pfb*"))


def test_tanktop_convert_strips_example_style_face04(tmp_path: Path):
    """E2E: Tank Top convert must not leave isolated pl18xx_04 dirt behind."""
    root = tmp_path / "mod"
    parts = root / PARTS_DIR
    parts.mkdir(parents=True)
    (parts / "pl1000_body_costume_3.pfb.16").write_bytes(b"tank")
    mesh = root / MESH_ROOTS[0]
    body = mesh / "pl1001"
    body.mkdir(parents=True)
    (body / "pl1001.mesh.1").write_bytes(b"m")
    (body / "pl1001.mdf2.10").write_bytes(b"d")
    face04 = mesh / "pl1050" / "pl1050_04"
    face04.mkdir(parents=True)
    (face04 / "pl1050_04_face_albm.tex.10").write_bytes(b"DIRTY")
    (face04 / "pl1050_04_face_nrmr.tex.10").write_bytes(b"DIRTY")
    (root / "modinfo.ini").write_text("Name=DirtyFaceTank\n", encoding="utf-8")

    out = tmp_path / "out"
    out.mkdir()
    report = convert_with_ops(
        analyze(root),
        [OutfitOp(
            source=CLAIRE_OUTFIT_BY_KEY["tanktop"],
            target=CLAIRE_OUTFIT_BY_KEY["tanktop"],
        )],
        out,
        tag_output=False,
        as_folder=True,
        folder_name="TankStrip",
    )
    folder = report.output_folder
    assert folder is not None
    assert not list(folder.rglob("*_04_face_*")), folder
    assert not list(folder.rglob("pl1050_04")), folder
    assert any("stripped Military *_04" in op for op in report.rename_ops)
