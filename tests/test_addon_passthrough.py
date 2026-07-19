"""Claire face/hair addons without AddonFor stay in multi-mod batches."""

from pathlib import Path

from re2_outfit_converter.analyzer import AnalysisResult, ModInfo, analyze
from re2_outfit_converter.converter import convert_batch
from re2_outfit_converter.isolation import isolation_seed
from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
from re2_outfit_converter.reports import BatchItem


def _face_addon(tmp_path: Path, name: str = "Claire Ballgag Straps Addon") -> Path:
    root = tmp_path / "straps"
    face = root / "natives/x64/sectionroot/character/player/pl1000/pl1050"
    face.mkdir(parents=True)
    (face / "pl1050.mesh.1808312334").write_bytes(b"mesh")
    (root / "modinfo.ini").write_text(
        f"name={name}\nversion=V1.3\ndescription=Gag addon\n",
        encoding="utf-8",
    )
    return root


def _elza_main(tmp_path: Path) -> Path:
    root = tmp_path / "main"
    body = root / "natives/x64/sectionroot/character/player/pl1000/pl1004"
    body.mkdir(parents=True)
    (body / "pl1004.mesh.1808312334").write_bytes(b"mesh")
    parts = root / (
        "natives/x64/objectroot/prefab/character/survivor/parts/pl1000"
    )
    parts.mkdir(parents=True)
    (parts / "pl1000_body_costume_c.pfb.16").write_bytes(b"pfb")
    (root / "modinfo.ini").write_text(
        "name=CR-AW BDSM Underwear\nversion=1.0\n",
        encoding="utf-8",
    )
    return root


def test_face_addon_is_passthrough_candidate(tmp_path: Path):
    root = _face_addon(tmp_path)
    analysis = analyze(root)
    assert analysis.has_claire_files
    assert not analysis.claire_outfits
    assert not analysis.modinfo.addonfor
    assert analysis.is_passthrough_candidate


def test_batch_links_orphan_addon_seed(tmp_path: Path):
    main_root = _elza_main(tmp_path)
    addon_root = _face_addon(tmp_path)
    main = analyze(main_root)
    addon = analyze(addon_root)
    assert main.claire_outfits
    assert addon.is_passthrough_candidate

    elza = CLAIRE_OUTFIT_BY_KEY["elza"]
    out = tmp_path / "out"
    out.mkdir()
    report = convert_batch(
        [
            BatchItem(analysis=main, label="Main"),
            BatchItem(analysis=addon, label="Straps"),
        ],
        elza,
        CLAIRE_OUTFIT_BY_KEY["tanktop"],
        out,
        "Bundle",
        tag_output=False,
    )
    assert report.output_zip is not None
    assert len(report.items) == 2
    # After batch, orphan addon shares main isolation seed
    assert addon.modinfo.addonfor == "CR-AW BDSM Underwear"
    assert isolation_seed(addon) == isolation_seed(
        AnalysisResult(modinfo=ModInfo(name="CR-AW BDSM Underwear"))
    )
