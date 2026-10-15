"""Hair redirect decisions and batch NothingToConvertError handling."""

from pathlib import Path

from re2_outfit_converter.analyzer import AnalysisResult, ModInfo
from re2_outfit_converter.converter import NothingToConvertError, convert, convert_batch
from re2_outfit_converter.exclusive_meshes import ensure_exclusive_part_mesh_hide
from re2_outfit_converter.hair_prefabs import (
    detect_hair_asset_stems,
    drop_mesh_only_hair_pfbs,
    ensure_isolated_hair_redirect,
    resolve_hair_chain_id,
)
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
    data = hair_files[0].read_bytes()
    assert "pl1070/pl1070.mesh".encode("utf-16le") in data
    assert "pl1800/pl1800.mdf2".encode("utf-16le") in data
    assert "pl1070.chain".encode("utf-16le") in data
    assert "pl1800/pl1800.mesh".encode("utf-16le") not in data
    assert "pl1800.chain".encode("utf-16le") not in data


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


def test_shared_hair_redirect_ignores_other_exclusive_rename(tmp_path: Path):
    """Hat isolation in the same map must not retarget shared-hair materials."""
    staging = tmp_path
    mesh = staging / MESH_ROOTS[0] / "pl1890"
    mesh.mkdir(parents=True)
    (mesh / "pl1890.mesh.1").write_bytes(b"shared")
    (mesh / "pl1890.mdf2.10").write_bytes(b"mdf")
    (staging / PARTS_DIR).mkdir(parents=True)
    analysis = AnalysisResult(root=staging)
    report = ConversionReport()
    rename_map = {
        "sectionroot/character/player/pl1000/pl1071/pl1071.mesh":
        "sectionroot/character/player/pl1000/pl1898/pl1898.mesh",
        "sectionroot/character/player/pl1000/pl1070/pl1070.mesh":
        "sectionroot/character/player/pl1000/pl1890/pl1890.mesh",
    }
    ensure_isolated_hair_redirect(
        staging, analysis, CLAIRE_OUTFIT_BY_KEY["jacket"],
        "pl1890", rename_map, report)
    pfb = next((staging / PARTS_DIR).glob("pl1000_hair_*.pfb*"))
    data = pfb.read_bytes()
    u16 = lambda s: b"".join(bytes([ord(c), 0]) for c in s)
    assert u16("pl1071_Hair_Mat") not in data
    assert u16("pl1071.chain") not in data
    assert u16("pl1890/pl1890.mesh") in data
    assert not any("mats/chain pl1071" in op for op in report.pfb_ops)


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


def test_claire_noir_hide_redirect_still_uses_pl1070(tmp_path: Path):
    """Claire exclusive hide must keep shared pl1070 mesh+chain (not Leon ids)."""
    from re2_outfit_converter.hair_prefabs import ensure_exclusive_hair_override

    staging = tmp_path
    (staging / PARTS_DIR).mkdir(parents=True)
    analysis = AnalysisResult(root=staging)
    report = ConversionReport()
    ensure_exclusive_hair_override(
        staging, analysis,
        CLAIRE_OUTFIT_BY_KEY["jacket"],
        CLAIRE_OUTFIT_BY_KEY["noir"],
        [], report,
    )
    pfb = next((staging / PARTS_DIR).glob("pl1000_hair_costume_a.pfb*"))
    data = pfb.read_bytes()
    pl1070 = b"".join(bytes([ord(c), 0]) for c in "pl1070")
    pl0070 = b"".join(bytes([ord(c), 0]) for c in "pl0070")
    assert b"".join(bytes([ord(c), 0]) for c in "pl1000/pl1070/pl1070.mesh") in data
    assert b"".join(bytes([ord(c), 0]) for c in "pl1000/pl1070.chain") in data
    assert pl1070 in data
    assert pl0070 not in data


def test_color_addon_does_not_inject_a_hair_redirect(tmp_path: Path):
    from re2_outfit_converter.hair_prefabs import ensure_exclusive_hair_override

    staging = tmp_path
    (staging / PARTS_DIR).mkdir(parents=True)
    analysis = AnalysisResult(modinfo=ModInfo(name="Gold", addonfor="Bunny"))
    report = ConversionReport()
    ensure_exclusive_hair_override(
        staging, analysis,
        CLAIRE_OUTFIT_BY_KEY["elza"],
        CLAIRE_OUTFIT_BY_KEY["noir"],
        [], report,
    )
    assert not list((staging / PARTS_DIR).glob("pl1000_hair_*.pfb*"))
    assert any("addon has no hair" in op for op in report.pfb_ops)


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


def test_detect_alphanumeric_hair_stem_pl107t(tmp_path: Path):
    """Robin-style kits use pl107t stems (letter suffix), not digits only."""
    staging = tmp_path
    hair = staging / MESH_ROOTS[0] / "pl1816"
    hair.mkdir(parents=True)
    (hair / "pl107t.mesh.1808312334").write_bytes(b"mesh")
    (hair / "pl107t.mdf2.10").write_bytes(b"mdf")
    (staging / MESH_ROOTS[0] / "pl107t.chain.21").write_bytes(b"chain")
    assert detect_hair_asset_stems(staging, "pl1816") == ("pl107t", "pl107t")
    assert resolve_hair_chain_id(staging, "pl1816", "pl107t") == "pl107t"


def test_chain_beside_the_mesh_is_not_the_folder_id(tmp_path: Path):
    """pl1816/pl107t.chain must not be reported as pl1816.chain."""
    staging = tmp_path
    hair = staging / MESH_ROOTS[0] / "pl1816"
    hair.mkdir(parents=True)
    (hair / "pl107t.mesh.1808312334").write_bytes(b"mesh")
    (hair / "pl107t.chain.21").write_bytes(b"chain")
    assert resolve_hair_chain_id(staging, "pl1816", "pl107t") == "pl107t"


def test_isolated_hair_redirect_alphanumeric_stem_and_chain(tmp_path: Path):
    """Redirect must load pl1816/pl107t.* + pl107t.chain (not pl1816.mesh)."""
    staging = tmp_path
    hair = staging / MESH_ROOTS[0] / "pl1816"
    hair.mkdir(parents=True)
    (hair / "pl107t.mesh.1808312334").write_bytes(b"mesh")
    (hair / "pl107t.mdf2.10").write_bytes(b"mdf")
    (staging / MESH_ROOTS[0] / "pl107t.chain.21").write_bytes(b"chain")
    (staging / PARTS_DIR).mkdir(parents=True)
    analysis = AnalysisResult(root=staging)
    report = ConversionReport()
    ensure_isolated_hair_redirect(
        staging, analysis, CLAIRE_OUTFIT_BY_KEY["tanktop"], "pl1816",
        {}, report)
    pfb = next((staging / PARTS_DIR).glob("pl1000_hair_*.pfb*"))
    data = pfb.read_bytes()
    u16 = lambda s: b"".join(bytes([ord(c), 0]) for c in s)
    assert u16("pl1816/pl107t.mesh") in data
    assert u16("pl1816/pl107t.mdf2") in data
    assert u16("pl107t.chain") in data
    assert u16("pl1816/pl1816.mesh") not in data
    assert u16("pl1070.chain") not in data
    assert any("chain pl107t" in op for op in report.pfb_ops)


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


def test_exclusive_mesh_hide_does_not_copy_a_face_onto_the_hair_slot(tmp_path: Path):
    staging = tmp_path
    face = staging / MESH_ROOTS[0] / "pl1813"
    face.mkdir(parents=True)
    (face / "pl1060.mesh.1").write_bytes(b"FACE")
    (face / "pl1060.mdf2.10").write_bytes(b"FACE-MDF")
    report = ConversionReport()
    ensure_exclusive_part_mesh_hide(
        staging, CLAIRE_OUTFIT_BY_KEY["military"], "", report,
        allow_template=False,
    )
    assert not (staging / MESH_ROOTS[0] / "pl1071").exists()
    assert any("left pl1071 alone" in op for op in report.rename_ops)
    assert not any("pl1813" in op for op in report.rename_ops)


def test_exclusive_mesh_hide_seeds_military_from_template(tmp_path: Path):
    staging = tmp_path
    (staging / PARTS_DIR).mkdir(parents=True)
    report = ConversionReport()
    ensure_exclusive_part_mesh_hide(
        staging, CLAIRE_OUTFIT_BY_KEY["military"], "", report)
    seeded = list((staging / MESH_ROOTS[0] / "pl1071").glob("pl1071.mesh*"))
    assert seeded, "bundled pl1070_hair template should seed Military pl1071"


def test_exclusive_mesh_hide_skips_template_for_addon(tmp_path: Path):
    staging = tmp_path
    report = ConversionReport()
    ensure_exclusive_part_mesh_hide(
        staging, CLAIRE_OUTFIT_BY_KEY["military"], "", report,
        allow_template=False,
    )
    assert not (staging / MESH_ROOTS[0] / "pl1071").exists()
    assert any("left pl1071 alone" in op for op in report.rename_ops)


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


def test_drop_mesh_only_hair_pfbs_no_hat_addon(tmp_path: Path):
    """No Hat–style: private mesh only — drop hair PFBs so Main's stay."""
    staging = tmp_path
    hair = staging / MESH_ROOTS[0] / "pl1880"
    hair.mkdir(parents=True)
    (hair / "pl1880.mesh.1").write_bytes(b"mesh")
    parts = staging / PARTS_DIR
    parts.mkdir(parents=True)
    pfb = parts / "pl1000_hair_costume_b.pfb.16"
    pfb.write_bytes(b"bad-redirect")
    report = ConversionReport()
    n = drop_mesh_only_hair_pfbs(staging, report, is_addon=True)
    assert n == 1
    assert not pfb.exists()
    assert any("mesh-only hair" in w for w in report.warnings)


def test_drop_mesh_only_hair_pfbs_keeps_when_mdf_present(tmp_path: Path):
    staging = _staging_with_private_hair(tmp_path, "pl1880")
    parts = staging / PARTS_DIR
    pfb = parts / "pl1000_hair_default.pfb.16"
    pfb.write_bytes(b"keep")
    report = ConversionReport()
    assert drop_mesh_only_hair_pfbs(staging, report) == 0
    assert pfb.exists()


def test_drop_addon_chainless_hair_pfbs_apocalypse(tmp_path: Path):
    """Apocalypse NSFW–style: AddonFor mesh+mdf, no .chain — drop PFBs."""
    staging = _staging_with_private_hair(tmp_path, "pl1880")
    parts = staging / PARTS_DIR
    pfb = parts / "pl1000_hair_costume_b.pfb.16"
    pfb.write_bytes(b"vanilla-chain-redirect")
    report = ConversionReport()
    n = drop_mesh_only_hair_pfbs(staging, report, is_addon=True)
    assert n == 1
    assert not pfb.exists()
    assert any("no local .chain" in w for w in report.warnings)


def test_drop_addon_chainless_keeps_standalone_beach_girl(tmp_path: Path):
    """Standalone (not AddonFor) mesh+mdf without chain keeps redirect."""
    staging = _staging_with_private_hair(tmp_path, "pl1891")
    parts = staging / PARTS_DIR
    pfb = parts / "pl1000_hair_default.pfb.16"
    pfb.write_bytes(b"keep")
    report = ConversionReport()
    assert drop_mesh_only_hair_pfbs(staging, report, is_addon=False) == 0
    assert pfb.exists()


def test_addon_chainless_skips_hair_redirect_inject(tmp_path: Path):
    """AddonFor with mdf but no chain must not inject vanilla-chain PFB."""
    staging = _staging_with_private_hair(tmp_path, "pl1880")
    analysis = AnalysisResult(
        root=staging,
        modinfo=ModInfo(name="Apoc", addonfor="Main"),
    )
    report = ConversionReport()
    ensure_isolated_hair_redirect(
        staging, analysis, CLAIRE_OUTFIT_BY_KEY["military"], "pl1880",
        {}, report)
    hair_files = list((staging / PARTS_DIR).glob("pl1000_hair_*.pfb*"))
    assert not hair_files
    assert any("skipped hair redirect for AddonFor" in op for op in report.pfb_ops)
