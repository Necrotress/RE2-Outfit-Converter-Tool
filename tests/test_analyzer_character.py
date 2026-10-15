"""Primary-character pick when a pack has leftover files from the other hero."""

from pathlib import Path

from re2_outfit_converter.analyzer import analyze
from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY, LEON_OUTFIT_BY_KEY

from tests.fixtures import LEON_MESH, MESH, write_modinfo


def test_leon_sheriff_mesh_beats_leftover_claire_jacket_textures(tmp_path: Path):
    """Marston-style: Sheriff body mesh + leftover Jacket textures → Leon."""
    root = tmp_path / "marston"
    sheriff = root / LEON_MESH / "pl0005"
    sheriff.mkdir(parents=True)
    (sheriff / "pl0005.mesh.1").write_bytes(b"leon-mesh")
    (sheriff / "pl0005.mdf2.10").write_bytes(b"leon-mdf")
    jacket = root / MESH / "pl1000"
    jacket.mkdir(parents=True)
    (jacket / "pl1000_chain_albm.tex.10").write_bytes(b"claire-tex")
    write_modinfo(root, Name="Leon Marston")
    analysis = analyze(root)
    assert analysis.character_key == "leon"
    keys = {o.key for o in analysis.outfits}
    assert "leon_sheriff" in keys
    assert "jacket" not in keys


def test_claire_jacket_mesh_beats_leftover_leon_sheriff_textures(tmp_path: Path):
    root = tmp_path / "jacket"
    body = root / MESH / "pl1000"
    body.mkdir(parents=True)
    (body / "pl1000.mesh.1").write_bytes(b"claire-mesh")
    leftover = root / LEON_MESH / "pl0005"
    leftover.mkdir(parents=True)
    (leftover / "pl0005_arm_albm.tex.10").write_bytes(b"leon-tex")
    write_modinfo(root, Name="Claire Jacket")
    analysis = analyze(root)
    assert analysis.character_key == "claire"
    keys = {o.key for o in analysis.outfits}
    assert "jacket" in keys
    assert "leon_sheriff" not in keys


def test_texture_only_elza_addon_still_detects_claire(tmp_path: Path):
    """AddonFor overlays have no mesh — must still detect the slot."""
    root = tmp_path / "elza_tex"
    body = root / MESH / "pl1004"
    body.mkdir(parents=True)
    (body / "pl1004.mdf2.10").write_bytes(b"mdf")
    (body / "pl1004_alb.tex.10").write_bytes(b"tex")
    write_modinfo(root, Name="Elza Tex", AddonFor="Main")
    analysis = analyze(root)
    assert analysis.character_key == "claire"
    assert CLAIRE_OUTFIT_BY_KEY["elza"] in analysis.outfits


def test_claire_pfbs_still_win_over_leon_body_mesh(tmp_path: Path):
    """PFB evidence outranks a leftover Sheriff mesh folder."""
    from tests.fixtures import PARTS

    root = tmp_path / "elza_plus_junk"
    parts = root / PARTS
    parts.mkdir(parents=True)
    (parts / "pl1000_body_costume_c.pfb.16").write_bytes(b"elza")
    sheriff = root / LEON_MESH / "pl0005"
    sheriff.mkdir(parents=True)
    (sheriff / "pl0005.mesh.1").write_bytes(b"junk")
    write_modinfo(root, Name="Elza")
    analysis = analyze(root)
    assert analysis.character_key == "claire"
    keys = {o.key for o in analysis.outfits}
    assert "elza" in keys
    assert "leon_sheriff" not in keys


def test_file_count_tiebreak_when_both_have_meshes(tmp_path: Path):
    """Equal outfit scores with meshes on both → more path hits win."""
    root = tmp_path / "both_mesh"
    jacket = root / MESH / "pl1000"
    jacket.mkdir(parents=True)
    (jacket / "pl1000.mesh.1").write_bytes(b"c-mesh")
    (jacket / "pl1000.mdf2.10").write_bytes(b"c-mdf")
    (jacket / "pl1000_alb.tex.10").write_bytes(b"c-tex")
    (jacket / "pl1000_nrm.tex.10").write_bytes(b"c-nrm")
    sheriff = root / LEON_MESH / "pl0005"
    sheriff.mkdir(parents=True)
    (sheriff / "pl0005.mesh.1").write_bytes(b"l-mesh")
    write_modinfo(root, Name="Ambiguous")
    analysis = analyze(root)
    assert analysis.character_key == "claire"
    assert CLAIRE_OUTFIT_BY_KEY["jacket"].key in {o.key for o in analysis.outfits}
    assert LEON_OUTFIT_BY_KEY["leon_sheriff"].key not in {
        o.key for o in analysis.outfits
    }


def test_read_modinfo_strips_utf8_bom(tmp_path: Path):
    from re2_outfit_converter.analyzer import _read_modinfo

    ini = tmp_path / "modinfo.ini"
    ini.write_bytes(b"\xef\xbb\xbfName=Leon Marston\nDescription=Hi\n")
    info, warn = _read_modinfo(ini)
    assert warn is None
    assert info.name == "Leon Marston"
    assert info.description == "Hi"