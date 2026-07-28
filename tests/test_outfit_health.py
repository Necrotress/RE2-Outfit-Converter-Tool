"""Load-set incomplete outfit filtering (main vs AddonFor)."""

from __future__ import annotations

from pathlib import Path

from re2_outfit_converter.analyzer import analyze
from re2_outfit_converter.outfit_health import (
    incomplete_outfits,
    incomplete_outfits_for_load,
    outfit_has_body_mesh,
)
from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY

from tests.fixtures import (
    MESH,
    build_casual_claire_style,
    build_elza_body_tex_addon,
    build_elza_main,
    write_modinfo,
)


def test_main_plus_body_tex_addon_suppresses_incomplete(tmp_path: Path):
    main = analyze(build_elza_main(tmp_path))
    addon = analyze(build_elza_body_tex_addon(tmp_path))
    assert "elza" in incomplete_outfits(addon)
    assert "elza" not in incomplete_outfits(main)
    merged = incomplete_outfits_for_load([main, addon])
    assert "elza" not in merged


def test_standalone_body_tex_addon_still_incomplete(tmp_path: Path):
    addon = analyze(build_elza_body_tex_addon(tmp_path))
    assert "elza" in incomplete_outfits(addon)
    assert "elza" in incomplete_outfits_for_load([addon])


def test_casual_claire_alone_still_flags_jacket(tmp_path: Path):
    analysis = analyze(build_casual_claire_style(tmp_path))
    reasons = incomplete_outfits_for_load([analysis])
    assert "jacket" in reasons
    assert "tanktop" not in reasons


def test_incomplete_main_wins_over_addon(tmp_path: Path):
    """Main missing jacket mesh stays flagged even if an addon also lacks it."""
    main = analyze(build_casual_claire_style(tmp_path))
    addon_root = tmp_path / "jacket_tex_addon"
    body = addon_root / MESH / "pl1000"
    body.mkdir(parents=True)
    (body / "pl1000.mdf2.10").write_bytes(b"mdf")
    (body / "pl1000_alb.tex.10").write_bytes(b"tex")
    write_modinfo(
        addon_root,
        name="Jacket Tex Addon",
        AddonFor="Casual Claire",
    )
    addon = analyze(addon_root)
    assert "jacket" in incomplete_outfits(main)
    assert "jacket" in incomplete_outfits(addon)
    merged = incomplete_outfits_for_load([main, addon])
    assert "jacket" in merged
    assert "mesh" in merged["jacket"].lower()
    assert merged["jacket"] == incomplete_outfits(main)["jacket"]


def test_outfit_has_body_mesh_on_elza_main(tmp_path: Path):
    main = analyze(build_elza_main(tmp_path))
    elza = CLAIRE_OUTFIT_BY_KEY["elza"]
    assert outfit_has_body_mesh(main, elza)
