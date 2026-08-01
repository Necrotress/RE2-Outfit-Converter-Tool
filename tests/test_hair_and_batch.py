"""Hair redirect decisions and batch NothingToConvertError handling."""

from pathlib import Path

from re2_outfit_converter.analyzer import AnalysisResult, ModInfo
from re2_outfit_converter.converter import NothingToConvertError, convert, convert_batch
from re2_outfit_converter.exclusive_meshes import ensure_exclusive_part_mesh_hide
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


def test_isolated_shared_hair_keeps_vanilla_chain(tmp_path: Path):
    """Beach Girl–style: private mesh/mdf, no .chain — must not freeze."""
    staging = tmp_path
    hair = staging / MESH_ROOTS[0] / "pl1891"
    hair.mkdir(parents=True)
    (hair / "pl1891.mesh.1").write_bytes(b"mesh")
    (hair / "pl1891.mdf2.10").write_bytes(b"mdf")
    (staging / PARTS_DIR).mkdir(parents=True)
    analysis = AnalysisResult(root=staging)
    report = ConversionReport()
    ensure_isolated_hair_redirect(
        staging, analysis, CLAIRE_OUTFIT_BY_KEY["military"], "pl1891",
        {}, report)
    pfb = next((staging / PARTS_DIR).glob("pl1000_hair_*.pfb*"))
    data = pfb.read_bytes()
    u16 = lambda s: b"".join(bytes([ord(c), 0]) for c in s)
    assert u16("pl1891/pl1891.mesh") in data
    assert u16("pl1891/pl1891.mdf2") in data
    assert u16("pl1891_Hair_Mat") in data
    assert u16("pl1070.chain") in data
    assert u16("pl1891.chain") not in data
    assert any("chain pl1070" in op for op in report.pfb_ops)


def test_exclusive_hair_redirect_retargets_pl1071(tmp_path: Path):
    """Military hat kit kept on pl1071 needs a PFB that loads pl1071 + mdf2."""
    staging = tmp_path
    hat = staging / MESH_ROOTS[0] / "pl1071"
    hat.mkdir(parents=True)
    (hat / "pl1071.mesh.1").write_bytes(b"mesh")
    (staging / PARTS_DIR).mkdir(parents=True)
    analysis = AnalysisResult(root=staging)
    report = ConversionReport()
    ensure_isolated_hair_redirect(
        staging, analysis, CLAIRE_OUTFIT_BY_KEY["elza"], "pl1071", {}, report)
    assert any("loads exclusive pl1071" in op for op in report.pfb_ops)
    pfb = next((staging / PARTS_DIR).glob("pl1000_hair_*.pfb*"))
    data = pfb.read_bytes()
    pl1071_u16 = b"".join(bytes([ord(c), 0]) for c in "pl1071")
    pl1070_u16 = b"".join(bytes([ord(c), 0]) for c in "pl1070")
    assert pl1071_u16 in data
    assert pl1070_u16 not in data
    assert b"".join(bytes([ord(c), 0]) for c in "pl1071.mdf2") in data


def test_exclusive_hat_redirect_wins_on_noir_over_hide(tmp_path: Path):
    """STARS→Noir must load pl1071 kit, not the pl1070 hide-vanilla-hat inject."""
    from re2_outfit_converter.hair_prefabs import ensure_exclusive_hair_override
    from re2_outfit_converter.exclusive_mdf import ensure_private_exclusive_mdf

    staging = tmp_path
    hat = staging / MESH_ROOTS[0] / "pl1071"
    hat.mkdir(parents=True)
    (hat / "pl1071.mesh.1").write_bytes(b"mesh")
    (staging / PARTS_DIR).mkdir(parents=True)
    analysis = AnalysisResult(root=staging)
    report = ConversionReport()
    src = CLAIRE_OUTFIT_BY_KEY["military"]
    tgt = CLAIRE_OUTFIT_BY_KEY["noir"]

    ensure_exclusive_hair_override(
        staging, analysis, src, tgt, [], report)
    assert any("keeping source exclusive pl1071" in op for op in report.pfb_ops)

    # After isolation away: private mesh + bundled private mdf.
    priv = staging / MESH_ROOTS[0] / "pl1897"
    priv.mkdir(parents=True)
    (priv / "pl1897.mesh.1").write_bytes(b"mesh")
    (priv / "pl1897_scarf_albm.tex.10").write_bytes(b"tex")
    rename_map = {
        "sectionroot/character/player/pl1000/pl1071/pl1071.mesh":
        "sectionroot/character/player/pl1000/pl1897/pl1897.mesh",
        "sectionroot/character/player/pl1000/pl1071/pl1071_scarf_albm.tex":
        "sectionroot/character/player/pl1000/pl1897/pl1897_scarf_albm.tex",
    }
    assert ensure_private_exclusive_mdf(
        staging, "pl1897", "pl1071", rename_map, report)
    ensure_isolated_hair_redirect(
        staging, analysis, tgt, "pl1897", rename_map, report)
    pfb = next((staging / PARTS_DIR).glob("pl1000_hair_*.pfb*"))
    data = pfb.read_bytes()
    assert b"".join(bytes([ord(c), 0]) for c in "pl1897/pl1897.mesh") in data
    assert b"".join(bytes([ord(c), 0]) for c in "pl1897/pl1897.mdf2") in data
    # Material / chain tokens stay on exclusive ID (mesh mats are pl1071_*).
    assert b"".join(bytes([ord(c), 0]) for c in "pl1071_Hair_Mat") in data
    assert b"".join(bytes([ord(c), 0]) for c in "pl1071.chain") in data
    assert b"".join(bytes([ord(c), 0]) for c in "pl1897.chain") not in data
    assert any("mats/chain pl1071" in op for op in report.pfb_ops)


def test_isolated_hair_skips_when_pfb_exists(tmp_path: Path):
    # No local mdf → only inject when hair PFB slots are missing.
    staging = tmp_path
    mesh = staging / MESH_ROOTS[0] / "pl1800"
    mesh.mkdir(parents=True)
    (mesh / "pl1800.mesh.1").write_bytes(b"mesh")
    parts = staging / PARTS_DIR
    parts.mkdir(parents=True)
    (parts / "pl1000_hair_costume_c.pfb.16").write_bytes(b"pfb")
    analysis = AnalysisResult(root=staging)
    target = CLAIRE_OUTFIT_BY_KEY["elza"]
    report = ConversionReport()
    ensure_isolated_hair_redirect(
        staging, analysis, target, "pl1800", {}, report)
    assert not report.pfb_ops
    assert (parts / "pl1000_hair_costume_c.pfb.16").read_bytes() == b"pfb"


def test_exclusive_mesh_hide_seeds_noir_from_private_hair(tmp_path: Path):
    staging = _staging_with_private_hair(tmp_path, "pl1800")
    # Private hair mesh file required (mdf alone is not enough).
    mesh = staging / MESH_ROOTS[0] / "pl1800"
    (mesh / "pl1800.mesh.1808312334").write_bytes(b"mesh")
    report = ConversionReport()
    ensure_exclusive_part_mesh_hide(
        staging, CLAIRE_OUTFIT_BY_KEY["noir"], "pl1800", report)
    seeded = list((staging / MESH_ROOTS[0] / "pl1075").glob("pl1075.mesh*"))
    assert seeded
    assert any("exclusive preview hide" in op for op in report.rename_ops)


def test_isolated_hair_redirect_mismatched_stem(tmp_path: Path):
    """Gameplay hair PFB must load pl1605/pl1678.mesh, not pl1605/pl1605.mesh."""
    staging = tmp_path
    hair = staging / MESH_ROOTS[0] / "pl1605"
    hair.mkdir(parents=True)
    (hair / "pl1678.mesh.1808312334").write_bytes(b"mesh")
    (hair / "pl1678.mdf2.10").write_bytes(b"mdf")
    (staging / PARTS_DIR).mkdir(parents=True)
    analysis = AnalysisResult(root=staging)
    report = ConversionReport()
    ensure_isolated_hair_redirect(
        staging, analysis, CLAIRE_OUTFIT_BY_KEY["noir"], "pl1605", {}, report)
    pfb = next((staging / PARTS_DIR).glob("pl1000_hair_*.pfb*"))
    data = pfb.read_bytes()
    u16 = lambda s: b"".join(bytes([ord(c), 0]) for c in s)
    assert u16("pl1605/pl1678.mesh") in data
    assert u16("pl1605/pl1678.mdf2") in data
    assert u16("pl1605/pl1605.mesh") not in data
    assert any("pl1678.mesh" in op for op in report.pfb_ops)


def test_exclusive_mesh_hide_from_custom_hair_mismatched_stem(tmp_path: Path):
    """pl1605/pl1678.mesh must become pl1075.mesh for Noir costume preview."""
    staging = tmp_path
    hair = staging / MESH_ROOTS[0] / "pl1605"
    hair.mkdir(parents=True)
    (hair / "pl1678.mesh.1808312334").write_bytes(b"mesh")
    (hair / "pl1678.mdf2.10").write_bytes(b"mdf")
    (hair / "pl1678_hair_alba.tex.10").write_bytes(b"tex")
    report = ConversionReport()
    ensure_exclusive_part_mesh_hide(
        staging, CLAIRE_OUTFIT_BY_KEY["noir"], "pl1605", report)
    dest = staging / MESH_ROOTS[0] / "pl1075"
    assert (dest / "pl1075.mesh.1808312334").is_file()
    assert (dest / "pl1075.mdf2.10").is_file()
    assert (dest / "pl1678_hair_alba.tex.10").is_file()
    assert any("from isolated pl1605" in op or "from custom pl1605" in op
               for op in report.rename_ops)


def test_exclusive_mesh_hide_seeds_military_from_template(tmp_path: Path):
    staging = tmp_path
    (staging / PARTS_DIR).mkdir(parents=True)
    report = ConversionReport()
    ensure_exclusive_part_mesh_hide(
        staging, CLAIRE_OUTFIT_BY_KEY["military"], "", report)
    seeded = list((staging / MESH_ROOTS[0] / "pl1071").glob("pl1071.mesh*"))
    assert seeded, "bundled pl1070_hair template should seed Military pl1071"


def test_exclusive_mesh_hide_keeps_existing_exclusive_mesh(tmp_path: Path):
    staging = tmp_path
    existing = staging / MESH_ROOTS[0] / "pl1075"
    existing.mkdir(parents=True)
    (existing / "pl1075.mesh.1808312334").write_bytes(b"custom")
    report = ConversionReport()
    ensure_exclusive_part_mesh_hide(
        staging, CLAIRE_OUTFIT_BY_KEY["noir"], "pl1800", report)
    assert (existing / "pl1075.mesh.1808312334").read_bytes() == b"custom"
    assert any("kept existing" in op for op in report.rename_ops)


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
