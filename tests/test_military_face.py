"""Military clean-face seed and Tank Top Military-face strip."""

from pathlib import Path

from re2_outfit_converter.analyzer import AnalysisResult, ModInfo, PfbSlot, analyze
from re2_outfit_converter.converter import convert_with_ops
from re2_outfit_converter.military_face import (
    analysis_has_custom_face,
    analysis_ships_slot_face,
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


def test_addon_without_face_does_not_seed(tmp_path: Path):
    staging = tmp_path
    report = ConversionReport()
    analysis = AnalysisResult(modinfo=ModInfo(name="Black", addonfor="Elite"))
    ensure_military_clean_face(
        staging, CLAIRE_OUTFIT_BY_KEY["military"], analysis, report)
    assert not list(staging.rglob("pl1050_04*"))
    assert any("addon has no face" in op for op in report.rename_ops)


def test_face_prefab_still_seeds_clean_military(tmp_path: Path):
    """A classic face prefab is not the texture set ray tracing loads."""
    staging = tmp_path
    parts = staging / PARTS_DIR
    parts.mkdir(parents=True)
    prefab = parts / "pl1000_face_costume_c.pfb.16"
    prefab.write_bytes(b"face")
    report = ConversionReport()
    analysis = AnalysisResult()
    ensure_military_clean_face(
        staging, CLAIRE_OUTFIT_BY_KEY["military"], analysis, report)
    assert list(staging.rglob("pl1050_04_face_albm.tex*"))
    assert prefab.read_bytes() == b"face"
    assert any("seeded Claire default face" in op for op in report.rename_ops)
    assert not analysis_ships_slot_face(analysis, "military")
    assert staging_has_custom_face(staging)


def test_custom_face_albedo_skips_the_clean_seed(tmp_path: Path):
    """pl1060_face_albm is the mod's face. Do not paint Claire's clean maps over it."""
    staging = tmp_path
    albedo = (
        staging / "natives/x64/sectionroot/character/player/pl1000/"
        "pl1050/pl1060_face_albm.tex.10"
    )
    albedo.parent.mkdir(parents=True)
    albedo.write_bytes(b"LIPS")
    report = ConversionReport()
    for key in ("tanktop", "military", "classic_tanktop"):
        ensure_military_clean_face(
            staging, CLAIRE_OUTFIT_BY_KEY[key], AnalysisResult(), report)
    assert albedo.read_bytes() == b"LIPS"
    assert not list(staging.rglob("pl1050_02*"))
    assert not list(staging.rglob("pl1050_03*"))
    assert not list(staging.rglob("pl1050_04*"))
    assert any("kept mod face data" in op for op in report.rename_ops)


def test_non_seed_target_is_noop(tmp_path: Path):
    staging = tmp_path
    report = ConversionReport()
    analysis = AnalysisResult()
    ensure_military_clean_face(
        staging, CLAIRE_OUTFIT_BY_KEY["noir"], analysis, report)
    assert not list(staging.rglob("pl1050_04*"))
    assert not report.rename_ops
    assert not report.removed_ops
    assert not list(staging.rglob("pl1050_02*"))
    assert not list(staging.rglob("pl1050_03*"))


def test_tanktop_strips_existing_pl1050_04(tmp_path: Path):
    """Tank Top drops leftover Military *_04 and writes the clean 02/03 set."""
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
    assert list(staging.rglob("pl1050_02_face_albm.tex*"))
    assert list(staging.rglob("pl1050_03_face_albm.tex*"))
    assert any("stripped Military *_04 face textures" in op
               for op in report.rename_ops)
    assert any("seeded Claire default face" in op for op in report.rename_ops)
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
    assert list(folder.rglob("pl1050_02_face_albm.tex*"))
    assert list(folder.rglob("pl1050_03_face_albm.tex*"))
    assert not list(folder.rglob("pl1050.mesh*"))


def test_clean_tank_renames_onto_02_and_03(tmp_path: Path):
    staging = tmp_path
    report = ConversionReport()
    ensure_military_clean_face(
        staging, CLAIRE_OUTFIT_BY_KEY["tanktop"], AnalysisResult(), report)
    for suffix in ("02", "03"):
        for kind in ("albm", "nrmr"):
            hits = list(staging.rglob(f"pl1050_{suffix}_face_{kind}.tex*"))
            assert len(hits) == 2, hits
            assert all(f"pl1050_{suffix}" in hit.as_posix() for hit in hits)
    assert not list(staging.rglob("pl1050_04*"))
    assert not list(staging.rglob("pl1050.mesh*"))
    assert not list(staging.rglob("pl1050.tex*"))


def test_authored_pl1050_04_is_left_alone(tmp_path: Path):
    staging = tmp_path
    parts = staging / PARTS_DIR
    parts.mkdir(parents=True)
    (parts / "pl1000_face_costume_b.pfb.16").write_bytes(b"face")
    dirty = (
        staging / "natives/x64/sectionroot/character/player/pl1000/"
        "pl1050/pl1050_04/pl1050_04_face_albm.tex.10"
    )
    dirty.parent.mkdir(parents=True)
    dirty.write_bytes(b"AUTHORED")
    report = ConversionReport()
    ensure_military_clean_face(
        staging, CLAIRE_OUTFIT_BY_KEY["military"], AnalysisResult(), report)
    assert dirty.read_bytes() == b"AUTHORED"
    assert any("kept mod face data" in op for op in report.rename_ops)
    assert analysis_ships_slot_face(
        AnalysisResult(natives_files=[dirty.relative_to(staging).as_posix()]),
        "military",
    )
    assert not analysis_ships_slot_face(
        AnalysisResult(natives_files=[dirty.relative_to(staging).as_posix()]),
        "tanktop",
    )


def _military_pack(root: Path, platform: str, mesh_suffix: str) -> None:
    body = (
        root / "natives" / platform / "sectionroot" / "character"
        / "player" / "pl1000" / "pl1006"
    )
    body.mkdir(parents=True)
    (body / f"pl1006.mesh.{mesh_suffix}").write_bytes(b"mesh")
    parts_rel = PARTS_DIR.replace("natives/x64/", f"natives/{platform}/", 1)
    parts = root.joinpath(*parts_rel.split("/"))
    parts.mkdir(parents=True)
    (parts / "pl1000_face_costume_b.pfb.16").write_bytes(b"face-prefab")
    (parts / "pl1000_body_costume_b.pfb.16").write_bytes(b"body")
    (root / "modinfo.ini").write_text("Name=BunnyStyle\n", encoding="utf-8")


def test_same_slot_ray_tracing_moves_clean_face(tmp_path: Path):
    """Already ray tracing, same slot: clean textures land on stm as .tex.34."""
    root = tmp_path / "mil"
    _military_pack(root, "stm", "2109108288")
    out = tmp_path / "out"
    out.mkdir()
    military = CLAIRE_OUTFIT_BY_KEY["military"]
    report = convert_with_ops(
        analyze(root),
        [OutfitOp(source=military, target=military)],
        out,
        tag_output=False,
        as_folder=True,
        folder_name="MilFace",
        write_log=False,
        game_build="Ray tracing",
    )
    folder = report.output_folder
    assert folder is not None
    tex = list(folder.rglob("pl1050_04_face_albm.tex*"))
    assert tex
    assert all(".tex.34" in path.name for path in tex)
    assert all("/stm/" in path.as_posix().replace("\\", "/") for path in tex)
    assert not list(folder.rglob("pl1050.mesh*"))
    prefabs = list(folder.rglob("pl1000_face_costume_b.pfb*"))
    assert prefabs
    assert prefabs[0].read_bytes() == b"face-prefab"


def test_same_slot_upgrade_picks_up_clean_face(tmp_path: Path, monkeypatch):
    from re2_outfit_converter.platform.path_remap import move_tree_to_rt
    from re2_outfit_converter.platform.reports import ConversionReport as Plat

    def _upgrade(staging, **_kwargs):
        plat = Plat()
        move_tree_to_rt(staging, plat)
        return plat

    monkeypatch.setattr(
        "re2_outfit_converter.converter.upgrade_to_rt", _upgrade)
    root = tmp_path / "mil"
    _military_pack(root, "x64", "1808312334")
    out = tmp_path / "out"
    out.mkdir()
    military = CLAIRE_OUTFIT_BY_KEY["military"]
    report = convert_with_ops(
        analyze(root),
        [OutfitOp(source=military, target=military)],
        out,
        tag_output=False,
        as_folder=True,
        folder_name="MilUpgrade",
        write_log=False,
        game_build="Ray tracing",
    )
    folder = report.output_folder
    assert folder is not None
    tex = list(folder.rglob("pl1050_04_face_nrmr.tex*"))
    assert tex
    assert all(".tex.34" in path.name for path in tex)
    assert all("/stm/" in path.as_posix().replace("\\", "/") for path in tex)
