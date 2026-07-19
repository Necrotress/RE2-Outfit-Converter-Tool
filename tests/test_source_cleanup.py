"""Leftover source body / UI cleanup after conversion."""

from pathlib import Path

from re2_outfit_converter.analyzer import analyze
from re2_outfit_converter.converter import convert
from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
from re2_outfit_converter.paths import MESH_ROOTS, PARTS_DIR


def _nurse_style_mod(tmp_path: Path) -> Path:
    """Elza PFBs + Elza UI + pl1004 stub body + custom body under pl1000."""
    root = tmp_path / "NurseStyle"
    parts = root / PARTS_DIR
    parts.mkdir(parents=True)
    (parts / "pl1000_body_costume_c.pfb.16").write_bytes(b"body")
    (parts / "pl1000_face_costume_c.pfb.16").write_bytes(b"face")
    (parts / "pl1000_hair_costume_c.pfb.16").write_bytes(b"hair")

    mesh = root / MESH_ROOTS[0]
    (mesh / "pl1004").mkdir(parents=True)
    (mesh / "pl1004" / "pl1004.mdf2.10").write_bytes(b"elza-mdf")
    (mesh / "pl1004" / "pl1004.mesh.1808312334").write_bytes(b"elza-mesh")
    (mesh / "pl1000").mkdir(parents=True)
    (mesh / "pl1000" / "pl1008.mdf2.10").write_bytes(b"custom-mdf")
    (mesh / "pl1000" / "pl1008.mesh.1808312334").write_bytes(b"custom-mesh")

    ui = root / "natives/x64/sectionroot/ui/ui0600"
    (ui / "prefab").mkdir(parents=True)
    (ui / "tex").mkdir(parents=True)
    (ui / "prefab" / "ui0601_01_08.pfb.16").write_bytes(b"uipfb")
    (ui / "tex" / "ui0601_01_08_iam.tex.10").write_bytes(b"uitex")
    (ui / "tex" / "ui0601_01_08.uvs.7").write_bytes(b"uiuvs")

    (root / "modinfo.ini").write_text(
        "Name=NurseStyle\nDescription=Test\n", encoding="utf-8")
    return root


def test_analyze_does_not_treat_redirect_host_as_jacket(tmp_path: Path):
    root = _nurse_style_mod(tmp_path)
    analysis = analyze(root)
    keys = {o.key for o in analysis.claire_outfits}
    assert "elza" in keys
    assert "jacket" not in keys


def test_convert_remaps_ui_and_moves_elza_body(tmp_path: Path):
    root = _nurse_style_mod(tmp_path)
    analysis = analyze(root)
    elza = CLAIRE_OUTFIT_BY_KEY["elza"]
    military = CLAIRE_OUTFIT_BY_KEY["military"]
    out = tmp_path / "out"
    out.mkdir()

    report = convert(
        analysis, elza, military, out,
        tag_output=False, as_folder=True, folder_name="NurseStyle",
    )
    folder = report.output_folder
    assert folder is not None
    mesh = folder / MESH_ROOTS[0]
    assert not (mesh / "pl1004").exists()
    assert (mesh / "pl1006").is_dir()

    ui = folder / "natives/x64/sectionroot/ui/ui0600"
    assert list((ui / "prefab").glob("ui0601_01_06.pfb*"))
    assert list((ui / "tex").glob("ui0601_01_06_iam.tex*"))
    assert not list(ui.rglob("ui0601_01_08*"))
