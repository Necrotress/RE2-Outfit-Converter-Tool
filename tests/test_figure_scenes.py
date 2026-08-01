"""Figure gallery isolation — strip author scenes to prevent bleed."""

from pathlib import Path

from re2_outfit_converter.figure_scenes import strip_claire_extra_figures
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


def test_strip_removes_author_elza_figure(tmp_path: Path):
    staging = tmp_path
    scene = _plant(staging, FIGURE_SCENE_12)
    pfb = _plant(staging, FIGURE_PFB_12)
    report = ConversionReport()
    n = strip_claire_extra_figures(staging, report)
    assert n == 2
    assert not scene.exists()
    assert not pfb.exists()
    assert any("figurescene_pl1000_12" in op for op in report.removed_ops)
    assert any("bleed" in w.lower() for w in report.warnings)


def test_strip_removes_all_claire_extra_ids(tmp_path: Path):
    staging = tmp_path
    s11 = _plant(staging, FIGURE_SCENE_11)
    s10 = _plant(staging, FIGURE_SCENE_10)
    report = ConversionReport()
    strip_claire_extra_figures(staging, report)
    assert not s11.exists()
    assert not s10.exists()
    assert any("figurescene_pl1000_11" in op for op in report.removed_ops)
    assert any("figurescene_pl1000_10" in op for op in report.removed_ops)


def test_strip_claire_extra_figures_helper(tmp_path: Path):
    staging = tmp_path
    _plant(staging, FIGURE_SCENE_12)
    _plant(staging, FIGURE_PFB_12)
    report = ConversionReport()
    n = strip_claire_extra_figures(staging, report)
    assert n == 2
    assert len(report.removed_ops) == 2
