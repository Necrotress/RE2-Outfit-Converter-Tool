"""Hair redirect decisions and batch NothingToConvertError handling."""

from pathlib import Path

from re2_outfit_converter.analyzer import AnalysisResult, ModInfo
from re2_outfit_converter.converter import NothingToConvertError, convert, convert_batch
from re2_outfit_converter.hair_prefabs import ensure_isolated_hair_redirect
from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
from re2_outfit_converter.paths import MESH_ROOTS, PARTS_DIR
from re2_outfit_converter.reports import BatchItem, ConversionReport


def _staging_with_private_hair(tmp_path: Path, hair_id: str = "pl1800") -> Path:
    mesh = tmp_path / MESH_ROOTS[0] / hair_id
    mesh.mkdir(parents=True)
    (mesh / f"{hair_id}.mdf2.10").write_bytes(b"mdf")
    (tmp_path / PARTS_DIR).mkdir(parents=True)
    return tmp_path


def test_isolated_hair_injects_when_no_pfb(tmp_path: Path):
    staging = _staging_with_private_hair(tmp_path)
    analysis = AnalysisResult(root=staging)
    target = CLAIRE_OUTFIT_BY_KEY["elza"]
    report = ConversionReport()
    rename_map: dict[str, str] = {}
    ensure_isolated_hair_redirect(
        staging, analysis, target, "pl1800", rename_map, report)
    assert any("injected hair redirect" in op for op in report.pfb_ops)
    hair_files = list((staging / PARTS_DIR).glob("pl1000_hair_*.pfb*"))
    assert hair_files


def test_isolated_hair_skips_when_pfb_exists(tmp_path: Path):
    staging = _staging_with_private_hair(tmp_path)
    parts = staging / PARTS_DIR
    (parts / "pl1000_hair_costume_c.pfb.16").write_bytes(b"pfb")
    analysis = AnalysisResult(root=staging)
    target = CLAIRE_OUTFIT_BY_KEY["elza"]
    report = ConversionReport()
    ensure_isolated_hair_redirect(
        staging, analysis, target, "pl1800", {}, report)
    assert not report.pfb_ops


def test_nothing_to_convert_error(tmp_path: Path):
    root = tmp_path / "mod"
    (root / "natives").mkdir(parents=True)
    (root / "modinfo.ini").write_text("Name=Empty\n", encoding="utf-8")
    analysis = AnalysisResult(
        root=root,
        modinfo=ModInfo(name="Empty"),
        natives_files=[],
    )
    elza = CLAIRE_OUTFIT_BY_KEY["elza"]
    try:
        convert(analysis, elza, elza, tmp_path / "out")
        assert False, "expected NothingToConvertError"
    except NothingToConvertError:
        pass


def test_batch_passthrough_only_on_nothing_to_convert(tmp_path: Path):
    root = tmp_path / "addon"
    (root / "natives" / "x64").mkdir(parents=True)
    (root / "modinfo.ini").write_text(
        "Name=Addon\nAddonFor=Main\n", encoding="utf-8")
    analysis = AnalysisResult(
        root=root,
        modinfo=ModInfo(name="Addon", addonfor="Main"),
        natives_files=["natives/x64/.keep"],
    )
    (root / "natives" / "x64" / ".keep").write_text("", encoding="utf-8")
    elza = CLAIRE_OUTFIT_BY_KEY["elza"]
    out = tmp_path / "out"
    out.mkdir()
    report = convert_batch(
        [BatchItem(analysis=analysis, label="Addon")],
        elza, elza, out, "Bundle",
        tag_output=False,
    )
    assert report.output_zip is not None
    assert report.items
    assert any("no Elza Walker assets" in w for w in report.items[0].warnings)
