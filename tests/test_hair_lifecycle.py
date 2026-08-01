"""Hair lifecycle: multi-kit isolation, Delete exclusive, per-target redirects."""

from __future__ import annotations

from pathlib import Path

from re2_outfit_converter.analyzer import AnalysisResult, ModInfo, analyze
from re2_outfit_converter.converter import convert_with_ops
from re2_outfit_converter.isolation import (
    isolate_claire_face_hair,
    resolve_hair_id_for_target,
    staging_mesh_ids,
)
from re2_outfit_converter.outfit_ops import OutfitOp
from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
from re2_outfit_converter.paths import MESH_ROOTS, PARTS_DIR
from re2_outfit_converter.reports import ConversionReport
from re2_outfit_converter.strip_outfit import strip_outfit_slot

from tests.fixtures import build_elza_full


def _u16(s: str) -> bytes:
    return b"".join(bytes([ord(c), 0]) for c in s)


def test_isolate_shared_and_exclusive_together(tmp_path: Path):
    """Military→Elza with pl1071 + pl1070 must isolate BOTH kits."""
    staging = tmp_path
    mesh = staging / MESH_ROOTS[0]
    hat = mesh / "pl1071"
    hat.mkdir(parents=True)
    (hat / "pl1071.mesh.1").write_bytes(b"hdr\x00pl1071_Scarf_Mat\x00")
    (hat / "pl1071_scarf_albm.tex.10").write_bytes(b"tex")
    shared = mesh / "pl1070"
    shared.mkdir(parents=True)
    (shared / "pl1070.mesh.1").write_bytes(b"shared-hair")
    (shared / "pl1070.mdf2.10").write_bytes(b"shared-mdf")
    analysis = AnalysisResult(
        root=staging,
        modinfo=ModInfo(name="BothHair"),
        natives_files=[
            f"{MESH_ROOTS[0]}/pl1071/pl1071.mesh.1",
            f"{MESH_ROOTS[0]}/pl1070/pl1070.mesh.1",
        ],
    )
    report = ConversionReport()
    rename_map: dict[str, str] = {}
    _, primary = isolate_claire_face_hair(
        staging, analysis,
        CLAIRE_OUTFIT_BY_KEY["military"],
        CLAIRE_OUTFIT_BY_KEY["elza"],
        rename_map, report,
    )
    assert not (mesh / "pl1071").exists()
    assert not (mesh / "pl1070").exists()
    assert primary.startswith("pl18")
    assert (mesh / primary).is_dir()
    present = staging_mesh_ids(staging)
    privates = [p for p in present if p.startswith("pl18")]
    assert len(privates) >= 2 or (
        # exclusive + shared may share one private only if one was missing —
        # here both existed so expect two privates OR primary holds shared
        # and another folder exists
        any("isolated exclusive hair pl1071" in op for op in report.rename_ops)
        and any("isolated hair pl1070" in op for op in report.rename_ops)
    )


def test_resolve_hair_does_not_crosswire_exclusives(tmp_path: Path):
    staging = tmp_path
    hat = staging / MESH_ROOTS[0] / "pl1075"
    hat.mkdir(parents=True)
    (hat / "pl1075.mesh.1").write_bytes(b"noir-hat")
    assert resolve_hair_id_for_target(
        staging, CLAIRE_OUTFIT_BY_KEY["noir"], "pl1075") == "pl1075"
    assert resolve_hair_id_for_target(
        staging, CLAIRE_OUTFIT_BY_KEY["military"], "pl1075") == ""


def test_strip_delete_removes_exclusive_hair(tmp_path: Path):
    staging = tmp_path
    hat = staging / MESH_ROOTS[0] / "pl1075"
    hat.mkdir(parents=True)
    (hat / "pl1075.mesh.1").write_bytes(b"hat")
    body = staging / MESH_ROOTS[0] / "pl1005"
    body.mkdir(parents=True)
    (body / "pl1005.mesh.1").write_bytes(b"body")
    report = ConversionReport()
    strip_outfit_slot(staging, CLAIRE_OUTFIT_BY_KEY["noir"], report)
    assert not (staging / MESH_ROOTS[0] / "pl1075").exists()
    assert not (staging / MESH_ROOTS[0] / "pl1005").exists()


def test_strip_keeps_exclusive_when_convert_target_needs_it(tmp_path: Path):
    staging = tmp_path
    hat = staging / MESH_ROOTS[0] / "pl1075"
    hat.mkdir(parents=True)
    (hat / "pl1075.mesh.1").write_bytes(b"hat")
    report = ConversionReport()
    strip_outfit_slot(
        staging, CLAIRE_OUTFIT_BY_KEY["noir"], report,
        keep_exclusive_ids={"pl1075"},
    )
    assert (staging / MESH_ROOTS[0] / "pl1075" / "pl1075.mesh.1").is_file()


def test_dual_map_noir_hat_not_forced_onto_military(tmp_path: Path):
    """Jacket→Noir + Tank→Military with only pl1075 must not load Noir hat on Military."""
    root = build_elza_full(tmp_path)
    # Retarget fixture: Jacket + Tank sources, ship Noir hat only.
    parts = root / PARTS_DIR
    (parts / "pl1000_body_default.pfb.16").write_bytes(b"jacket")
    (parts / "pl1000_body_costume_3.pfb.16").write_bytes(b"tank")
    (parts / "pl1000_body_costume_c.pfb.16").unlink(missing_ok=True)
    mesh = root / MESH_ROOTS[0]
    # Move elza body to jacket; add tank body; add Noir exclusive hat.
    elza_body = mesh / "pl1004"
    if elza_body.exists():
        elza_body.rename(mesh / "pl1000")
    tank = mesh / "pl1001"
    tank.mkdir(parents=True)
    (tank / "pl1001.mesh.1").write_bytes(b"tank-mesh")
    # Drop shared hair so primary becomes kept exclusive.
    shared = mesh / "pl1070"
    if shared.exists():
        import shutil
        shutil.rmtree(shared)
    hat = mesh / "pl1075"
    hat.mkdir(parents=True)
    (hat / "pl1075.mesh.1").write_bytes(b"noir-hat")

    out = tmp_path / "out"
    out.mkdir()
    report = convert_with_ops(
        analyze(root),
        [
            OutfitOp(
                source=CLAIRE_OUTFIT_BY_KEY["jacket"],
                target=CLAIRE_OUTFIT_BY_KEY["noir"],
            ),
            OutfitOp(
                source=CLAIRE_OUTFIT_BY_KEY["tanktop"],
                target=CLAIRE_OUTFIT_BY_KEY["military"],
            ),
        ],
        out,
        tag_output=False,
        as_folder=True,
        folder_name="DualExcl",
    )
    folder = report.output_folder
    assert folder is not None
    parts = folder / PARTS_DIR
    noir_hair = parts / "pl1000_hair_costume_a.pfb.16"
    mil_hair = parts / "pl1000_hair_costume_b.pfb.16"
    assert noir_hair.is_file() and mil_hair.is_file()
    noir_data = noir_hair.read_bytes()
    mil_data = mil_hair.read_bytes()
    assert _u16("pl1075") in noir_data
    # Military must not be pointed at the Noir exclusive hat.
    assert _u16("pl1075") not in mil_data


def test_delete_only_injects_hair_redirect(tmp_path: Path):
    root = build_elza_full(tmp_path)
    # Keep Elza + Jacket-like second outfit via tank, delete Elza only.
    parts = root / PARTS_DIR
    (parts / "pl1000_body_costume_3.pfb.16").write_bytes(b"tank")
    mesh = root / MESH_ROOTS[0]
    tank = mesh / "pl1001"
    tank.mkdir(parents=True)
    (tank / "pl1001.mesh.1").write_bytes(b"tank")

    out = tmp_path / "out"
    out.mkdir()
    report = convert_with_ops(
        analyze(root),
        [
            OutfitOp(source=CLAIRE_OUTFIT_BY_KEY["elza"], target=None),
            OutfitOp(
                source=CLAIRE_OUTFIT_BY_KEY["tanktop"],
                target=CLAIRE_OUTFIT_BY_KEY["tanktop"],
            ),
        ],
        out,
        tag_output=False,
        as_folder=True,
        folder_name="DelElza",
    )
    # Actually delete-only means NO converts — use pure deletes with remaining.
    # Re-run with only delete when mod has jacket+elza; build simpler:
    _ = report
    root2 = tmp_path / "del_only"
    parts2 = root2 / PARTS_DIR
    parts2.mkdir(parents=True)
    (parts2 / "pl1000_body_costume_c.pfb.16").write_bytes(b"elza")
    (parts2 / "pl1000_body_default.pfb.16").write_bytes(b"jacket")
    mesh2 = root2 / MESH_ROOTS[0]
    for pid, payload in (("pl1004", b"e"), ("pl1000", b"j"), ("pl1070", b"h")):
        d = mesh2 / pid
        d.mkdir(parents=True)
        (d / f"{pid}.mesh.1").write_bytes(payload)
        (d / f"{pid}.mdf2.10").write_bytes(payload + b"-mdf")
    (root2 / "modinfo.ini").write_text("Name=DelOnly\n", encoding="utf-8")
    out2 = tmp_path / "out2"
    out2.mkdir()
    report2 = convert_with_ops(
        analyze(root2),
        [OutfitOp(source=CLAIRE_OUTFIT_BY_KEY["elza"], target=None)],
        out2,
        tag_output=False,
        as_folder=True,
        folder_name="DelOnlyOut",
    )
    folder = report2.output_folder
    assert folder is not None
    hair_pfbs = list((folder / PARTS_DIR).glob("pl1000_hair_*.pfb*"))
    assert hair_pfbs, "delete-only should inject hair redirect for remaining slots"
    assert any("injected hair redirect" in op or "replaced hair redirect" in op
               for op in report2.pfb_ops)
