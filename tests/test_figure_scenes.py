"""Figure gallery isolation — strip author scenes to prevent bleed."""

from pathlib import Path

from re2_outfit_converter.figure_scenes import (
    convert_figure_scenes,
    strip_claire_extra_figures,
)
from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
from re2_outfit_converter.reports import ConversionReport

FIGURE_SCENE_12 = (
    "natives/x64/objectroot/scene/ui/figure/extra/figurescene_pl1000_12.scn.19"
)
FIGURE_PFB_12 = (
    "natives/x64/objectroot/prefab/ui/figure/extra/figure_pl1000_12.pfb.16"
)
FIGURE_SCENE_11 = (
    "natives/x64/objectroot/scene/ui/figure/extra/figurescene_pl1000_11.scn.19"
)
FIGURE_SCENE_10 = (
    "natives/x64/objectroot/scene/ui/figure/extra/figurescene_pl1000_10.scn.19"
)


def _plant(staging: Path, rel: str, data: bytes = b"x") -> Path:
    path = staging / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_elza_to_noir_strips_figure_not_retargets(tmp_path: Path):
    staging = tmp_path
    scene = _plant(staging, FIGURE_SCENE_12)
    pfb = _plant(staging, FIGURE_PFB_12)
    rename_map: dict[str, str] = {}
    report = ConversionReport()
    convert_figure_scenes(
        staging,
        CLAIRE_OUTFIT_BY_KEY["elza"],
        CLAIRE_OUTFIT_BY_KEY["noir"],
        rename_map,
        report,
    )
    assert not scene.exists()
    assert not pfb.exists()
    assert not (
        staging / "natives/x64/objectroot/scene/ui/figure/extra"
        / "figurescene_pl1000_11.scn.19"
    ).exists()
    assert not rename_map
    assert any("figurescene_pl1000_12" in op for op in report.removed_ops)
    assert any("bleed" in w.lower() for w in report.warnings)


def test_figure_removed_when_target_has_no_extra(tmp_path: Path):
    staging = tmp_path
    scene = _plant(staging, FIGURE_SCENE_12)
    report = ConversionReport()
    convert_figure_scenes(
        staging,
        CLAIRE_OUTFIT_BY_KEY["elza"],
        CLAIRE_OUTFIT_BY_KEY["jacket"],
        {},
        report,
    )
    assert not scene.exists()
    assert any("figurescene_pl1000_12" in op for op in report.removed_ops)


def test_strip_removes_all_claire_extra_ids(tmp_path: Path):
    staging = tmp_path
    s11 = _plant(staging, FIGURE_SCENE_11)
    s10 = _plant(staging, FIGURE_SCENE_10)
    rename_map: dict[str, str] = {}
    report = ConversionReport()
    convert_figure_scenes(
        staging,
        CLAIRE_OUTFIT_BY_KEY["elza"],
        CLAIRE_OUTFIT_BY_KEY["noir"],
        rename_map,
        report,
    )
    assert not s11.exists()
    assert not s10.exists()
    assert any("figurescene_pl1000_11" in op for op in report.removed_ops)
    assert any("figurescene_pl1000_10" in op for op in report.removed_ops)


def test_noir_to_noir_still_strips_author_scene(tmp_path: Path):
    """Identity convert must not keep a leaky Noir figurescene."""
    staging = tmp_path
    scene = _plant(staging, FIGURE_SCENE_11)
    report = ConversionReport()
    convert_figure_scenes(
        staging,
        CLAIRE_OUTFIT_BY_KEY["noir"],
        CLAIRE_OUTFIT_BY_KEY["noir"],
        {},
        report,
    )
    assert not scene.exists()
    assert any("bleed" in w.lower() for w in report.warnings)


def test_strip_claire_extra_figures_helper(tmp_path: Path):
    staging = tmp_path
    _plant(staging, FIGURE_SCENE_12)
    _plant(staging, FIGURE_PFB_12)
    report = ConversionReport()
    n = strip_claire_extra_figures(staging, report)
    assert n == 2
    assert len(report.removed_ops) == 2
