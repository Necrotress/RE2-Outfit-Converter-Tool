"""Figure gallery retarget — keep Bonuses hair/face after convert."""

from pathlib import Path

from re2_outfit_converter.figure_scenes import (
    convert_figure_scenes_for_ops,
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
BASE_FIGURE_SCENE = (
    "natives/x64/objectroot/scene/ui/figure/pl/figurescene_pl1000.scn.19"
)
BASE_FIGURE_PFB = (
    "natives/x64/objectroot/prefab/ui/figure/pl/figure_pl1000.pfb.16"
)
TANK_FIGURE_SCENE = (
    "natives/x64/objectroot/scene/ui/figure/pl/figurescene_pl1001.scn.19"
)
TANK_FIGURE_PFB = (
    "natives/x64/objectroot/prefab/ui/figure/pl/figure_pl1001.pfb.16"
)
CLASSIC_FIGURE_SCENE = (
    "natives/x64/objectroot/scene/ui/figure/pl/figurescene_pl1008.scn.19"
)
CLASSIC_FIGURE_PFB = (
    "natives/x64/objectroot/prefab/ui/figure/pl/figure_pl1005.pfb.16"
)
CLASSIC_TANK_FIGURE_SCENE = (
    "natives/x64/objectroot/scene/ui/figure/pl/figurescene_pl1011.scn.19"
)
CLASSIC_TANK_FIGURE_PFB = (
    "natives/x64/objectroot/prefab/ui/figure/pl/figure_pl1011.pfb.16"
)
JACKET_FIGURE_SCENE = BASE_FIGURE_SCENE


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


def test_strip_keeps_requested_ids(tmp_path: Path):
    staging = tmp_path
    s11 = _plant(staging, FIGURE_SCENE_11)
    s10 = _plant(staging, FIGURE_SCENE_10)
    report = ConversionReport()
    n = strip_claire_extra_figures(staging, report, keep_ids={"11"})
    assert n == 1
    assert s11.exists()
    assert not s10.exists()


def test_retarget_elza_to_noir_renames_and_registers_token(tmp_path: Path):
    staging = tmp_path
    scene = _plant(staging, FIGURE_SCENE_12, b"figure-scene")
    pfb = _plant(staging, FIGURE_PFB_12, b"figure-pfb")
    report = ConversionReport()
    rename_map: dict[str, str] = {}
    convert_figure_scenes_for_ops(
        staging,
        [(CLAIRE_OUTFIT_BY_KEY["elza"], CLAIRE_OUTFIT_BY_KEY["noir"])],
        rename_map,
        report,
    )
    assert not scene.exists()
    assert not pfb.exists()
    # Vanilla Noir gallery is figurescene_pl1000_10 (costume_a / pl1005).
    assert (staging / FIGURE_SCENE_10).exists()
    assert (
        staging
        / "natives/x64/objectroot/prefab/ui/figure/extra/figure_pl1000_10.pfb.16"
    ).exists()
    assert rename_map.get("figurescene_pl1000_12.scn") == (
        "figurescene_pl1000_10.scn"
    )
    assert rename_map.get("figure_pl1000_12.pfb") == "figure_pl1000_10.pfb"


def test_retarget_elza_to_military_uses_id_11(tmp_path: Path):
    staging = tmp_path
    _plant(staging, FIGURE_SCENE_12, b"mil-scene")
    _plant(staging, FIGURE_PFB_12, b"mil-pfb")
    report = ConversionReport()
    rename_map: dict[str, str] = {}
    convert_figure_scenes_for_ops(
        staging,
        [(CLAIRE_OUTFIT_BY_KEY["elza"], CLAIRE_OUTFIT_BY_KEY["military"])],
        rename_map,
        report,
    )
    # Vanilla Military gallery is figurescene_pl1000_11 (costume_b / pl1006).
    assert (staging / FIGURE_SCENE_11).exists()
    assert not (staging / FIGURE_SCENE_10).exists()
    assert rename_map.get("figurescene_pl1000_12.scn") == (
        "figurescene_pl1000_11.scn"
    )


def test_elza_to_elza_keeps_figure_scene(tmp_path: Path):
    staging = tmp_path
    scene = _plant(staging, FIGURE_SCENE_12, b"keep-me")
    report = ConversionReport()
    rename_map: dict[str, str] = {}
    convert_figure_scenes_for_ops(
        staging,
        [(CLAIRE_OUTFIT_BY_KEY["elza"], CLAIRE_OUTFIT_BY_KEY["elza"])],
        rename_map,
        report,
    )
    assert scene.exists()
    assert scene.read_bytes() == b"keep-me"


def test_promote_elza_to_jacket_base_paths(tmp_path: Path):
    staging = tmp_path
    _plant(staging, FIGURE_SCENE_12, b"base-scene")
    _plant(staging, FIGURE_PFB_12, b"base-pfb")
    report = ConversionReport()
    rename_map: dict[str, str] = {}
    convert_figure_scenes_for_ops(
        staging,
        [(CLAIRE_OUTFIT_BY_KEY["elza"], CLAIRE_OUTFIT_BY_KEY["jacket"])],
        rename_map,
        report,
    )
    assert not (staging / FIGURE_SCENE_12).exists()
    assert (staging / BASE_FIGURE_SCENE).read_bytes() == b"base-scene"
    assert (staging / BASE_FIGURE_PFB).read_bytes() == b"base-pfb"
    assert any("figure/pl/pl1000" in w for w in report.warnings)


def test_promote_elza_to_tank_uses_pl1001(tmp_path: Path):
    staging = tmp_path
    _plant(staging, FIGURE_SCENE_12, b"tank-scene")
    _plant(staging, FIGURE_PFB_12, b"tank-pfb")
    report = ConversionReport()
    rename_map: dict[str, str] = {}
    convert_figure_scenes_for_ops(
        staging,
        [(CLAIRE_OUTFIT_BY_KEY["elza"], CLAIRE_OUTFIT_BY_KEY["tanktop"])],
        rename_map,
        report,
    )
    assert (staging / TANK_FIGURE_SCENE).read_bytes() == b"tank-scene"
    assert (staging / TANK_FIGURE_PFB).read_bytes() == b"tank-pfb"
    assert any("figure/pl/pl1001" in w for w in report.warnings)


def test_promote_elza_to_classic_uses_pl1008_not_jacket(tmp_path: Path):
    staging = tmp_path
    _plant(staging, FIGURE_SCENE_12, b"classic-scene")
    _plant(staging, FIGURE_PFB_12, b"classic-pfb")
    report = ConversionReport()
    rename_map: dict[str, str] = {}
    convert_figure_scenes_for_ops(
        staging,
        [(CLAIRE_OUTFIT_BY_KEY["elza"], CLAIRE_OUTFIT_BY_KEY["classic_jacket"])],
        rename_map,
        report,
    )
    assert not (staging / FIGURE_SCENE_12).exists()
    assert not (staging / JACKET_FIGURE_SCENE).exists()
    assert (staging / CLASSIC_FIGURE_SCENE).read_bytes() == b"classic-scene"
    assert (staging / CLASSIC_FIGURE_PFB).read_bytes() == b"classic-pfb"
    assert rename_map.get("Figure_pl1000") == "Figure_pl1005"
    assert any("figure/pl/pl1008" in w for w in report.warnings)


def test_promote_elza_to_classic_tank_uses_pl1011(tmp_path: Path):
    staging = tmp_path
    _plant(staging, FIGURE_SCENE_12, b"ctank-scene")
    _plant(staging, FIGURE_PFB_12, b"ctank-pfb")
    report = ConversionReport()
    rename_map: dict[str, str] = {}
    convert_figure_scenes_for_ops(
        staging,
        [(
            CLAIRE_OUTFIT_BY_KEY["elza"],
            CLAIRE_OUTFIT_BY_KEY["classic_tanktop"],
        )],
        rename_map,
        report,
    )
    assert not (staging / JACKET_FIGURE_SCENE).exists()
    assert (staging / CLASSIC_TANK_FIGURE_SCENE).read_bytes() == b"ctank-scene"
    assert (staging / CLASSIC_TANK_FIGURE_PFB).read_bytes() == b"ctank-pfb"
    assert rename_map.get("Figure_pl1000") == "Figure_pl1011"
    assert any("figure/pl/pl1011" in w for w in report.warnings)


def test_retarget_classic_base_figure_to_tanktop(tmp_path: Path):
    """Classic Jacket figure/pl files must move onto Tank Top stems."""
    staging = tmp_path
    scene = _plant(staging, CLASSIC_FIGURE_SCENE, b"classic-scene")
    pfb = _plant(staging, CLASSIC_FIGURE_PFB, b"classic-pfb")
    report = ConversionReport()
    rename_map: dict[str, str] = {}
    convert_figure_scenes_for_ops(
        staging,
        [(
            CLAIRE_OUTFIT_BY_KEY["classic_jacket"],
            CLAIRE_OUTFIT_BY_KEY["tanktop"],
        )],
        rename_map,
        report,
    )
    assert not scene.exists()
    assert not pfb.exists()
    assert (staging / TANK_FIGURE_SCENE).read_bytes() == b"classic-scene"
    assert (staging / TANK_FIGURE_PFB).read_bytes() == b"classic-pfb"
    assert rename_map.get("Figure_pl1005") == "Figure_pl1001"
    assert any("Retargeted base figure gallery" in w for w in report.warnings)


def test_other_base_figure_is_left_alone(tmp_path: Path):
    staging = tmp_path
    _plant(staging, CLASSIC_FIGURE_SCENE, b"classic-scene")
    jacket = _plant(staging, BASE_FIGURE_SCENE, b"jacket-scene")
    report = ConversionReport()
    convert_figure_scenes_for_ops(
        staging,
        [(
            CLAIRE_OUTFIT_BY_KEY["classic_jacket"],
            CLAIRE_OUTFIT_BY_KEY["tanktop"],
        )],
        {},
        report,
    )
    assert jacket.read_bytes() == b"jacket-scene"
    assert (staging / TANK_FIGURE_SCENE).read_bytes() == b"classic-scene"


def test_sync_figure_template_stems_to_local_mesh(tmp_path: Path):
    """figure_pl1001 plmira/pl107l leftovers alias onto plnico/pl107t."""
    from re2_outfit_converter.paths import MESH_ROOTS

    staging = tmp_path
    face = staging / MESH_ROOTS[0] / "pl1803"
    face.mkdir(parents=True)
    (face / "plnico.mesh.1").write_bytes(b"face")
    hair = staging / MESH_ROOTS[0] / "pl1816"
    hair.mkdir(parents=True)
    (hair / "pl107t.mesh.1").write_bytes(b"hair")
    (staging / MESH_ROOTS[0] / "pl107t.chain.21").write_bytes(b"c")
    (staging / MESH_ROOTS[0] / "pl100t.chain.21").write_bytes(b"c")

    # Minimal UTF-16LE payload like a half-patched Tank figure prefab.
    payload = (
        "SectionRoot/Character/Player/pl1000/pl1803/plmira.mesh\0"
        "SectionRoot/Character/Player/pl1000/pl1816/pl107l.mdf2\0"
        "SectionRoot/Character/Player/pl1000/pl100l.chain\0"
        "SectionRoot/Character/Player/pl1000/pl107l.chain\0"
    ).encode("utf-16-le")
    _plant(staging, TANK_FIGURE_PFB, payload)

    report = ConversionReport()
    rename_map: dict[str, str] = {}
    convert_figure_scenes_for_ops(
        staging,
        [(
            CLAIRE_OUTFIT_BY_KEY["classic_jacket"],
            CLAIRE_OUTFIT_BY_KEY["tanktop"],
        )],
        rename_map,
        report,
    )
    assert rename_map.get("plmira") == "plnico"
    assert rename_map.get("pl107l") == "pl107t"
    assert rename_map.get("pl100l") == "pl100t"
