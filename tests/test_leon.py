"""Leon detect / remap / isolation / figure smoke tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from re2_outfit_converter.analyzer import AnalysisResult, analyze
from re2_outfit_converter.character import LEON_PROFILE
from re2_outfit_converter.converter import convert, convert_with_ops
from re2_outfit_converter.figure_scenes import strip_claire_extra_figures
from re2_outfit_converter.isolation import isolate_claire_face_hair, resolve_hair_id_for_target
from re2_outfit_converter.outfit_ops import OutfitOp
from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY, LEON_OUTFIT_BY_KEY
from re2_outfit_converter.paths import mesh_roots, parts_dir
from re2_outfit_converter.reports import ConversionError, ConversionReport

from tests.fixtures import build_leon_police_full


def test_leon_body_material_name_is_recognized():
    from re2_outfit_converter.material_hash import is_material_name

    assert is_material_name("pl0000_Body_Mat")
    assert not is_material_name("pl2000_Body_Mat")


def test_leon_prefab_keeps_the_convert_op():
    from re2_outfit_converter.analyzer import PfbSlot
    from re2_outfit_converter.outfit_ops import adapt_ops_for_package, package_has_outfit_assets

    police = LEON_OUTFIT_BY_KEY["leon_police"]
    noir = LEON_OUTFIT_BY_KEY["leon_noir"]
    analysis = AnalysisResult(
        pfbs=[PfbSlot("hair", "costume_a", "natives/x64/pl0000_hair_costume_a.pfb.16")],
        claire_pfbs=[],
    )
    assert package_has_outfit_assets(analysis, noir)
    ops = adapt_ops_for_package(
        analysis,
        [
            OutfitOp(source=police, target=LEON_OUTFIT_BY_KEY["leon_casual"]),
            OutfitOp(source=noir, target=LEON_OUTFIT_BY_KEY["leon_sheriff"]),
        ],
    )
    assert any(op.source.key == "leon_noir" for op in ops)


def test_detect_leon_police(tmp_path: Path):
    root = build_leon_police_full(tmp_path)
    analysis = analyze(root)
    assert analysis.character_key == "leon"
    assert analysis.profile is LEON_PROFILE
    keys = {o.key for o in analysis.outfits}
    assert "leon_police" in keys
    assert analysis.claire_outfits == []
    assert any(p.part == "body" for p in analysis.pfbs)


def test_leon_police_to_casual_remap(tmp_path: Path):
    root = build_leon_police_full(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    police = LEON_OUTFIT_BY_KEY["leon_police"]
    casual = LEON_OUTFIT_BY_KEY["leon_casual"]
    report = convert(
        analyze(root), police, casual, out,
        tag_output=False, as_folder=True, folder_name="LeonCasual",
    )
    folder = report.output_folder
    assert folder is not None

    parts = folder / parts_dir(LEON_PROFILE)
    assert (parts / "pl0000_body_default.pfb.16").is_file()
    assert not (parts / "pl0000_body_costume_1.pfb.16").exists()

    mesh = folder / mesh_roots(LEON_PROFILE)[0]
    assert (mesh / "pl0002").is_dir()
    assert not (mesh / "pl0000").exists()

    assert list(folder.rglob("ui0601_00_00_iam.tex*"))
    assert not list(folder.rglob("ui0601_00_01_iam.tex*"))

    planted = next(folder.rglob("ref_pl0000.mdf2*"))
    data = planted.read_bytes()
    assert b"pl0002" in data
    assert b"pl0000/pl0000" not in data


def test_leon_face_hair_isolation(tmp_path: Path):
    root = build_leon_police_full(tmp_path)
    staging = tmp_path / "stage"
    shutil.copytree(root, staging)
    analysis = analyze(staging)
    police = LEON_OUTFIT_BY_KEY["leon_police"]
    casual = LEON_OUTFIT_BY_KEY["leon_casual"]
    rename_map: dict[str, str] = {}
    report = ConversionReport()
    face_id, hair_id = isolate_claire_face_hair(
        staging, analysis, police, casual, rename_map, report,
    )
    mesh = staging / mesh_roots(LEON_PROFILE)[0]
    assert face_id.startswith("pl18")
    assert hair_id.startswith("pl18")
    assert not (mesh / "pl0050").exists()
    assert not (mesh / "pl0070").exists()
    assert (mesh / face_id).is_dir()
    assert (mesh / hair_id).is_dir()


def test_leon_figure_strip(tmp_path: Path):
    staging = tmp_path
    scene = (
        staging
        / "natives/x64/objectroot/scene/ui/figure/extra"
        / "figurescene_pl0000_10.scn.19"
    )
    scene.parent.mkdir(parents=True)
    scene.write_bytes(b"leon-fig")
    report = ConversionReport()
    n = strip_claire_extra_figures(
        staging, report,
        figure_prefix=LEON_PROFILE.figure_prefix,
        extra_ids=LEON_PROFILE.extra_figure_ids,
    )
    assert n == 1
    assert not scene.exists()


def test_reject_mixed_claire_leon_ops(tmp_path: Path):
    root = build_leon_police_full(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    ops = [
        OutfitOp(
            LEON_OUTFIT_BY_KEY["leon_police"],
            CLAIRE_OUTFIT_BY_KEY["jacket"],
        ),
    ]
    with pytest.raises(ConversionError, match="mix"):
        convert_with_ops(analyze(root), ops, out, as_folder=True)


def _u16(s: str) -> bytes:
    return b"".join(bytes([ord(c), 0]) for c in s)


def test_leon_sheriff_hide_redirect_uses_shared_hair(tmp_path: Path):
    """PFB-only Noir→Sheriff must hide pl0075 via pl0070, not Claire pl1070.

    Vanilla Leon shared hair is ``pl0000/pl0070`` + sidecar ``pl0070.chain``.
    Pointing the inject at ``pl0000/pl1070.chain`` freezes on outfit switch
    and cutscenes (Hunk Noir example).
    """
    from re2_outfit_converter.hair_prefabs import ensure_exclusive_hair_override

    parts = tmp_path / parts_dir(LEON_PROFILE)
    parts.mkdir(parents=True)
    analysis = AnalysisResult(root=tmp_path)
    report = ConversionReport()
    ensure_exclusive_hair_override(
        tmp_path, analysis,
        LEON_OUTFIT_BY_KEY["leon_noir"],
        LEON_OUTFIT_BY_KEY["leon_sheriff"],
        [], report,
    )
    pfb = parts / "pl0000_hair_costume_b.pfb.16"
    assert pfb.is_file()
    data = pfb.read_bytes()
    assert _u16("pl0000/pl0070/pl0070.mesh") in data
    assert _u16("pl0000/pl0070.chain") in data
    assert _u16("pl0070_Hair_Mat") in data
    assert _u16("pl1070") not in data
    assert any("hides pl0075" in op for op in report.pfb_ops)


def test_leon_noir_hide_redirect_uses_shared_hair(tmp_path: Path):
    """Casual→Noir hide of pl0074 also stays on Leon shared hair."""
    from re2_outfit_converter.hair_prefabs import ensure_exclusive_hair_override

    parts = tmp_path / parts_dir(LEON_PROFILE)
    parts.mkdir(parents=True)
    analysis = AnalysisResult(root=tmp_path)
    report = ConversionReport()
    ensure_exclusive_hair_override(
        tmp_path, analysis,
        LEON_OUTFIT_BY_KEY["leon_casual"],
        LEON_OUTFIT_BY_KEY["leon_noir"],
        [], report,
    )
    pfb = parts / "pl0000_hair_costume_a.pfb.16"
    data = pfb.read_bytes()
    assert _u16("pl0000/pl0070/pl0070.mesh") in data
    assert _u16("pl0000/pl0070.chain") in data
    assert _u16("pl1070") not in data


def test_resolve_hair_sees_leon_exclusive(tmp_path: Path):
    """Leon exclusive meshes live under pl0000, not Claire pl1000 roots."""
    mesh = tmp_path / mesh_roots(LEON_PROFILE)[0] / "pl0075"
    mesh.mkdir(parents=True)
    (mesh / "pl0075.mesh.1").write_bytes(b"sheriff-hat")
    assert resolve_hair_id_for_target(
        tmp_path, LEON_OUTFIT_BY_KEY["leon_sheriff"], "pl0075") == "pl0075"
    assert resolve_hair_id_for_target(
        tmp_path, LEON_OUTFIT_BY_KEY["leon_noir"], "pl0075") == ""


def test_leon_skip_hide_when_source_exclusive_mesh_present(tmp_path: Path):
    from re2_outfit_converter.hair_prefabs import ensure_exclusive_hair_override

    hat = tmp_path / mesh_roots(LEON_PROFILE)[0] / "pl0074"
    hat.mkdir(parents=True)
    (hat / "pl0074.mesh.1").write_bytes(b"noir-hat")
    parts = tmp_path / parts_dir(LEON_PROFILE)
    parts.mkdir(parents=True)
    analysis = AnalysisResult(root=tmp_path)
    report = ConversionReport()
    ensure_exclusive_hair_override(
        tmp_path, analysis,
        LEON_OUTFIT_BY_KEY["leon_noir"],
        LEON_OUTFIT_BY_KEY["leon_sheriff"],
        [], report,
    )
    assert any(
        "keeping source exclusive pl0074" in op for op in report.pfb_ops)
    assert not (parts / "pl0000_hair_costume_b.pfb.16").exists()


def test_leon_noir_preview_hide_copies_shared_hair(tmp_path: Path):
    """Costume-select preview loads pl0074; seed it from Leon pl0070, not pl1000."""
    from re2_outfit_converter.exclusive_meshes import ensure_exclusive_part_mesh_hide
    from re2_outfit_converter.paths import MESH_ROOTS

    root = mesh_roots(LEON_PROFILE)[0]
    hair = tmp_path / root / "pl0070"
    hair.mkdir(parents=True)
    (hair / "pl0070.mesh.1").write_bytes(b"shared-hair")
    report = ConversionReport()
    ensure_exclusive_part_mesh_hide(
        tmp_path, LEON_OUTFIT_BY_KEY["leon_noir"], "pl0070", report)
    dest = tmp_path / root / "pl0074"
    assert (dest / "pl0074.mesh.1").is_file()
    assert not (tmp_path / MESH_ROOTS[0] / "pl0074").exists()
    assert any("from isolated pl0070" in op or "from mod pl0070" in op
               for op in report.rename_ops)
