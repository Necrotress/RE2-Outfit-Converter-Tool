"""Material rules applied when an MDF crosses between classic RE2 and RE2 RT.

The Blender scripts import each other as top-level modules, the way Blender
loads them, so the script folder goes on sys.path here too.
"""

from __future__ import annotations

import sys

from re2_outfit_converter.platform.blender_detect import blender_script_dir

sys.path.insert(0, str(blender_script_dir()))

import mdf_classicize  # noqa: E402
import mdf_presets  # noqa: E402
import mdf_rtxify  # noqa: E402

SSS = 0x08000000


class Flags:
    def __init__(self, value: int = 0) -> None:
        self.asInt32 = value


class Property:
    def __init__(self, name: str = "", value=None) -> None:
        self.propName = name
        self.propValue = list(value or [])
        self.padding = 0
        self.frontPadding = 0
        self.paramCount = len(self.propValue)


class TextureBinding:
    def __init__(self, ttype: str = "", path: str = "") -> None:
        self.textureType = ttype
        self.texturePath = path


class Material:
    def __init__(self) -> None:
        self.materialName = ""
        self.mmtrPath = ""
        self.shaderType = 0
        self.hideInGame = False
        self.flags = Flags()
        self.flagsB = Flags()
        self.shaderLODNum = 0
        self.bakeTextureArraySize = 0
        self.propertyList = []
        self.textureList = []


class FakeMDFApi:
    Material = Material
    TextureBinding = TextureBinding
    Property = Property


class FakeMDF:
    def __init__(self, materials) -> None:
        self.materialList = list(materials)


def make_material(name, mmtr, *, shader=0, flags=0, textures=(), props=()):
    mat = Material()
    mat.materialName = name
    mat.mmtrPath = mmtr
    mat.shaderType = shader
    mat.flags = Flags(flags)
    mat.textureList = [TextureBinding(t, p) for t, p in textures]
    mat.propertyList = [Property(n, v) for n, v in props]
    return mat


def rtxify(materials, shipped=(), re3_player_dest=None):
    mdf = FakeMDF(materials)
    notes = mdf_rtxify.rtxify_mdf(
        mdf, FakeMDFApi, list(shipped), re3_player_dest=re3_player_dest
    )
    return mdf, notes


def test_player_materials_gain_the_sss_flag():
    body = make_material(
        "pl1000_Body_Mat", "MasterMaterial/Master/Record_Player.mmtr",
        flags=0x00000098,
    )
    face = make_material(
        "pl1050_Face_Mat", "MasterMaterial/Master/Record_Player_Face.mmtr",
        flags=0x00000099,
    )
    hair = make_material(
        "pl1070_Hair_Mat", "MasterMaterial/Master/Record_Player_Hair.mmtr",
        flags=0x00000083,
    )
    mdf, _ = rtxify([body, face, hair])
    assert mdf.materialList[0].flags.asInt32 == 0x08000098
    assert mdf.materialList[1].flags.asInt32 == 0x08000099
    # Record_Player_Hair keeps the bit clear in RT, unlike Hair.mmtr.
    assert mdf.materialList[2].flags.asInt32 == 0x00000083


def test_expensive_transparent_shader_type_becomes_rt():
    cornea = make_material(
        "pl1050_Eyes_Out_Mat",
        "MasterMaterial/Master/ExpensiveEyeCornea.mmtr", shader=10,
    )
    glass = make_material(
        "pl2000_LightDirt_Mat",
        "MasterMaterial/Master/Glass_ReflectiveTransparent.mmtr", shader=11,
    )
    opaque = make_material(
        "pl1000_Body_Mat", "MasterMaterial/Master/Record_Player.mmtr",
    )
    tearline = make_material(
        "pl1050_Tearline_Mat", "MasterMaterial/Master/Eye_Tear.mmtr", shader=1,
    )
    mdf, _ = rtxify([cornea, glass, opaque, tearline])
    assert [m.shaderType for m in mdf.materialList] == [13, 13, 0, 1]


def test_re3_cloth_uses_the_jacket_shading_not_the_skin_values():
    """RE3 cloth stores Rec_Cloth 0 and Fresnel 1. That shades leather as skin.

    Vanilla Claire's jacket is Record_Player with Rec_Cloth 1 and Fresnel 0.
    Skin that is already Record_Player keeps its own values.
    """
    cloth = make_material(
        "pl2020_Skirt_Mat",
        "MasterMaterial/Master/Record_Player_Cloth_RE3.mmtr",
        props=(("Rec_Cloth", [0.0]), ("Fresnel", [1.0])),
        textures=(("BaseMetalMap", "Escape/Character/dress_albm.tex"),),
    )
    skin = make_material(
        "pl1000_Body_Mat",
        "MasterMaterial/Master/Record_Player.mmtr",
        props=(("Rec_Cloth", [0.0]), ("Fresnel", [1.0])),
    )
    mdf, _ = rtxify(
        [cloth, skin], ["record_player_cloth_re3.mmtr.1808160001"],
    )
    cloth_props = {p.propName: p.propValue for p in mdf.materialList[0].propertyList}
    skin_props = {p.propName: p.propValue for p in mdf.materialList[1].propertyList}
    assert cloth_props["Rec_Cloth"] == [1.0]
    assert cloth_props["Fresnel"] == [0.0]
    assert cloth_props["Rec_Rain_WetRate"] == [0.0]
    assert skin_props["Rec_Cloth"] == [0.0]
    assert skin_props["Fresnel"] == [1.0]


def test_authored_cloth_wetmask_survives_both_builds():
    """RE3 cloth stores the wetmask under RainWet, not Rec_Rain.

    Jacket shading must not put that rate back to zero. Classicize keeps
    the same stock slots.
    """
    props = (
        ("Rec_Cloth", [0.0]),
        ("Fresnel", [1.0]),
        ("RainWet_Intensity", [0.75]),
        ("Rain_RainRate", [0.4]),
    )
    textures = (
        ("RainRipples_AreaMap", "SectionRoot/Character/ripples.tex"),
        ("Rain_WetMask", "SectionRoot/Character/pl1050_wetMask_MSK1.tex"),
    )
    cloth = make_material(
        "pl2000_Body_Mat",
        "MasterMaterial/Master/Record_Player_Cloth_RE3.mmtr",
        props=props,
        textures=textures,
    )
    mdf, _ = rtxify([cloth], ["record_player_cloth_re3.mmtr.1808160001"])
    got = {p.propName: p.propValue for p in mdf.materialList[0].propertyList}
    assert got["Rec_Cloth"] == [1.0]
    _assert_wetmask(mdf.materialList[0])

    down = FakeMDF([make_material(
        "pl2000_Body_Mat",
        "MasterMaterial/Master/Record_Player_Cloth_RE3.mmtr",
        props=props,
        textures=textures,
    )])
    mdf_classicize.classicize_mdf(
        down, FakeMDFApi, ["record_player_cloth_re3.mmtr.2109101635"],
    )
    _assert_wetmask(down.materialList[0])


def _assert_wetmask(mat):
    props = {p.propName: p.propValue for p in mat.propertyList}
    bound = {t.textureType: t.texturePath for t in mat.textureList}
    assert props["Rec_Rain_WetRate"] == [0.75]
    assert props["Rec_Rain_RainRate"] == [0.4]
    assert bound["Rec_Rain_WetMask"].endswith("pl1050_wetMask_MSK1.tex")
    assert bound["Rec_Rain_WaterRiple"].endswith("ripples.tex")


def test_shipped_cloth_shader_is_rebuilt_without_moving_textures():
    """RT has no Cloth_RE3. The material moves to Record_Player.

    Texture folders stay authored. Inverse: classicize re-aims the same way.
    """
    mat = make_material(
        "pl2000_Body_Mat",
        "MasterMaterial/Master/Record_Player_Cloth_RE3.mmtr",
        flags=0x0000009A,
        textures=(
            ("BaseMetalMap", "Escape/Character/pl2000_Ouft_ALBM.tex"),
            ("NormalRoughnessMap", "Escape/Character/pl2000_Ouft_NRMR.tex"),
            ("SomethingRE3Only", "Escape/Character/whatever.tex"),
        ),
    )
    mdf, notes = rtxify([mat], ["record_player_cloth_re3.mmtr.1808160001"])
    out = mdf.materialList[0]
    assert out.mmtrPath == "MasterMaterial/Master/Record_Player.mmtr"
    bound = {t.textureType: t.texturePath for t in out.textureList}
    assert bound["BaseMetalMap"] == "SectionRoot/Character/pl2000_Ouft_ALBM.tex"
    assert bound["NormalRoughnessMap"] == "SectionRoot/Character/pl2000_Ouft_NRMR.tex"
    assert "SomethingRE3Only" not in bound
    assert "rebuilt on Character.json" in notes[0]


def test_re3_emissive_glass_is_rebuilt_onto_stock_glass():
    """shader_0006_EmissiveGlass_RE3 is not in the RTX master list.

    Leaving it on the body material file made the mesh draw nothing. The
    head uses Record_Player_Face, which RTX ships, so only the head showed.
    Glass_ExpensiveTransparent is the stock shader Moto's light panel uses.
    """
    mat = make_material(
        "pl2000_Lightglass_Mat",
        "Escape/VFX/Shader/shader_0006_EmissiveGlass_RE3.mmtr",
        shader=0,
        flags=0x10,
        props=(
            ("BaseColor", [1.0, 1.0, 1.0, 1.0]),
            ("HieghtScale", [1.0]),
            ("HightThrethold", [0.5]),
        ),
    )
    mdf, notes = rtxify([mat])
    out = mdf.materialList[0]
    assert out.materialName == "pl2000_Lightglass_Mat"
    assert out.mmtrPath == (
        "MasterMaterial/Master/Glass_ExpensiveTransparent.mmtr"
    )
    assert out.shaderType == 13
    names = [p.propName for p in out.propertyList]
    assert "HieghtScale" not in names
    assert "UseCubeMap" in names
    assert any("rebuilt on Glass.json" in note for note in notes)


def test_shipped_shader_with_a_stock_twin_is_renamed():
    mat = make_material(
        "Vaccine_Mat", "MasterMaterial/Master/Env_Alpha_RE3.mmtr",
        textures=(("BaseMetalMap", "mod/alb.tex"),),
        props=(("BaseColor", [1.0, 1.0, 1.0, 1.0]),),
    )
    mdf, notes = rtxify([mat], ["env_alpha_re3.mmtr.1808160001"])
    out = mdf.materialList[0]
    assert out.mmtrPath == "MasterMaterial/Master/env_alpha.mmtr"
    assert [t.textureType for t in out.textureList] == ["BaseMetalMap"]
    assert [p.propName for p in out.propertyList] == ["BaseColor"]
    assert "stock env_alpha.mmtr" in notes[0]


def hair_props(count):
    return tuple((f"HairProp{i}", [0.0]) for i in range(count))


def test_shipped_hair_shader_is_rebuilt_when_the_slot_count_disagrees():
    """RE3's Record_Player_Hair takes 78 parameters; RE2's takes 29."""
    mat = make_material(
        "Hair_Mat", "MasterMaterial/Master/Record_Player_Hair_RE3.mmtr",
        props=hair_props(78),
    )
    mdf, notes = rtxify([mat], ["record_player_hair_re3.mmtr.1808160001"])
    out = mdf.materialList[0]
    assert out.mmtrPath == "MasterMaterial/Master/Record_Player_Hair.mmtr"
    assert len(out.propertyList) == 29
    assert "rebuilt on Hair.json" in notes[0]


def test_both_directions_refuse_the_same_bad_alias():
    shipped = [
        "record_player_hair_re3.mmtr.1808160001",
        "record_player_hair.mmtr.1808160001",
    ]
    mmtr = "MasterMaterial/Master/Record_Player_Hair_RE3.mmtr"
    up, _ = rtxify([make_material("H", mmtr, props=hair_props(29))], shipped)
    down = FakeMDF([make_material("H", mmtr, props=hair_props(29))])
    mdf_classicize.classicize_mdf(down, FakeMDFApi, shipped)
    assert up.materialList[0].mmtrPath == down.materialList[0].mmtrPath
    assert up.materialList[0].mmtrPath != mmtr


def test_stock_shader_the_mod_does_not_ship_is_left_alone():
    mat = make_material(
        "pl1000_Body_Mat", "MasterMaterial/Master/Record_Player.mmtr",
        textures=(("BaseMetalMap", "mod/alb.tex"),),
        props=(("BaseColor", [1.0]),),
    )
    mdf, _ = rtxify([mat], ["record_player_cloth_re3.mmtr.1808160001"])
    out = mdf.materialList[0]
    assert out.mmtrPath == "MasterMaterial/Master/Record_Player.mmtr"
    assert [t.textureType for t in out.textureList] == ["BaseMetalMap"]


def test_texture_paths_pick_up_the_rt_platform_tokens():
    mat = make_material(
        "Mat", "MasterMaterial/Master/Record_Player.mmtr",
        textures=(("BaseMetalMap", "natives/x64/sectionroot/character/body.tex.10"),),
    )
    mdf, _ = rtxify([mat])
    assert (
        mdf.materialList[0].textureList[0].texturePath
        == "natives/stm/sectionroot/character/body.tex.34"
    )


def test_classicize_undoes_both_rt_markers():
    mat = make_material(
        "pl1000_Body_Mat", "MasterMaterial/Master/Record_Player.mmtr",
        shader=13, flags=0x08000098,
    )
    mdf = FakeMDF([mat])
    mdf_classicize.classicize_mdf(mdf, FakeMDFApi)
    out = mdf.materialList[0]
    assert out.flags.asInt32 == 0x00000098
    assert out.shaderType == 10


def test_classicize_rebuilds_a_shader_the_mod_shipped():
    mat = make_material(
        "pl2000_Body_Mat",
        "MasterMaterial/Master/Record_Player_Cloth_RE3.mmtr",
        flags=0x08000098,
    )
    mdf = FakeMDF([mat])
    notes = mdf_classicize.classicize_mdf(
        mdf, FakeMDFApi, ["record_player_cloth_re3.mmtr.2109101635"]
    )
    out = mdf.materialList[0]
    assert out.mmtrPath == "MasterMaterial/Master/Record_Player.mmtr"
    assert not out.flags.asInt32 & SSS
    assert "rebuilt on Character.json" in notes[0]


def classic_character_props():
    preset = mdf_presets.load_preset("RE2", "Character.json")
    return [
        (p["Property Name"], mdf_presets.prop_value_list(p.get("Value")))
        for p in preset["Property List"]
    ]


def test_rt_adds_the_parameters_the_rt_shader_declares():
    mat = make_material(
        "pl1000_Body_Mat", "MasterMaterial/Master/Record_Player.mmtr",
        flags=0x98, props=classic_character_props(),
    )
    mdf, _ = rtxify([mat])
    names = [p.propName for p in mdf.materialList[0].propertyList]
    assert len(names) == 37
    assert set(mdf_classicize.RT_ONLY_PROPS) <= set(names)
    # Position matters: the blood multiplier sits third, not at the end.
    assert names[2] == "CERD_D_BloodColorMultiplier"
    assert names[-1] == "CustomSpecularReflecance"


def test_rt_leaves_a_non_stock_property_layout_alone():
    mat = make_material(
        "pl1000_Body_Mat", "MasterMaterial/Master/Record_Player.mmtr",
        props=(("SomeModdersOwnParam", [1.0]),),
    )
    mdf, _ = rtxify([mat])
    assert [p.propName for p in mdf.materialList[0].propertyList] == [
        "SomeModdersOwnParam"
    ]


def _corrupt_classic_body_props():
    """Sportsuit leftover: 34 slots, string table dies after AlphaTestRef."""
    names = [n for n, _ in classic_character_props()]
    out = [(n, [0.0]) for n in names[:14]]
    out.append(("Indir", [0.0]))
    while len(out) < 34:
        out.append(("", [0.0]))
    return out


def test_corrupt_stock_body_is_rebuilt_not_left_to_crash_rt():
    """A truncated property table in a stock shader must not ride through.

    Sportsuit's pl1000_Body_Mat / Boots_Mat are this. Leaving them made the
    whole body MDF unload in RT, so only the head (a different file) drew.
    """
    mat = make_material(
        "pl1000_Body_Mat", "MasterMaterial/Master/Record_Player.mmtr",
        flags=0x98,
        props=_corrupt_classic_body_props(),
        textures=(
            ("BaseMetalMap", "Escape/Character/body.tex"),
            (
                "Rec_RTT",
                "Escape/VFX/RecordSystem/RecordTexture/pl2000/pl2000_body.rtex",
            ),
        ),
    )
    mdf, notes = rtxify([mat])
    out = mdf.materialList[0]
    assert len(out.propertyList) == 37
    assert all(mdf_presets.sane_prop_name(p.propName) for p in out.propertyList)
    assert out.propertyList[2].propName == "CERD_D_BloodColorMultiplier"
    assert "broken property table" in notes[0]
    by_type = {t.textureType: t.texturePath for t in out.textureList}
    assert "body.tex" in by_type["BaseMetalMap"]
    assert by_type["Rec_RTT"] == (
        "VFX/RecordSystem/RecordTexture/pl2000/pl2000_body.rtex"
    )


def test_rt_rewrites_classic_rtex_bindings():
    """Vanilla Rec_RTT stays; RE3 copies are aimed at the Claire record tex.

    Inverse: classicize already keeps VFX/RecordSystem rtex.
    """
    mat = make_material(
        "pl1000_Body_Mat", "MasterMaterial/Master/Record_Player.mmtr",
        flags=0x98, props=classic_character_props(),
        textures=(
            ("Rec_RTT", "VFX/RecordSystem/RecordTexture/pl1000/pl1000_body.rtex"),
        ),
    )
    mdf, _ = rtxify([mat])
    path = mdf.materialList[0].textureList[0].texturePath
    assert path == "VFX/RecordSystem/RecordTexture/pl1000/pl1000_body.rtex"
    mdf_classicize.classicize_mdf(mdf, FakeMDFApi)
    back = mdf.materialList[0].textureList[0].texturePath
    assert back == path


def test_authored_rec_rtt_is_left_alone():
    """Classic → RT does not aim every Rec_RTT at Claire's record texture."""
    mat = make_material(
        "pl1000_Body_Mat", "MasterMaterial/Master/Record_Player.mmtr",
        flags=0x98, props=classic_character_props(),
        textures=(
            (
                "Rec_RTT",
                "Escape/VFX/RecordSystem/RecordTexture/pl2000/pl2000_body.rtex",
            ),
        ),
    )
    mdf, _ = rtxify([mat])
    path = mdf.materialList[0].textureList[0].texturePath
    assert path == (
        "VFX/RecordSystem/RecordTexture/pl2000/pl2000_body.rtex"
    )


def test_face_rec_rtt_keeps_the_path_the_mod_wrote():
    mat = make_material(
        "pl1050_Face_Mat", "MasterMaterial/Master/Record_Player_Face.mmtr",
        flags=0x99, props=classic_character_props(),
        textures=(
            (
                "Rec_RTT",
                "VFX/RecordSystem/RecordTexture/pl2050/pl2050_head.rtex",
            ),
        ),
    )
    mdf, _ = rtxify([mat])
    path = mdf.materialList[0].textureList[0].texturePath
    assert path == "VFX/RecordSystem/RecordTexture/pl2050/pl2050_head.rtex"


def test_classicize_rebuilds_a_corrupt_rt_body():
    props = [("???", [0.0])] * 37
    mat = make_material(
        "pl1000_Body_Mat", "MasterMaterial/Master/Record_Player.mmtr",
        flags=0x08000098, props=props,
    )
    mdf = FakeMDF([mat])
    notes = mdf_classicize.classicize_mdf(mdf, FakeMDFApi)
    out = mdf.materialList[0]
    assert [p.propName for p in out.propertyList] == [
        n for n, _ in classic_character_props()
    ]
    assert "broken property table" in notes[0]


def test_corrupt_body_survives_a_round_trip():
    start = make_material(
        "pl1000_Body_Mat", "MasterMaterial/Master/Record_Player.mmtr",
        flags=0x98, props=_corrupt_classic_body_props(),
        textures=(("BaseMetalMap", "sectionroot/character/body.tex"),),
    )
    to_rt, _ = rtxify([start])
    assert len(to_rt.materialList[0].propertyList) == 37
    mdf_classicize.classicize_mdf(to_rt, FakeMDFApi)
    back = to_rt.materialList[0]
    assert [p.propName for p in back.propertyList] == [
        n for n, _ in classic_character_props()
    ]
    assert [t.texturePath for t in back.textureList if t.textureType == "BaseMetalMap"] == [
        "sectionroot/character/body.tex"
    ]


def test_a_stock_body_material_survives_a_round_trip():
    """classic -> RT -> classic must land back on the classic layout."""
    start = make_material(
        "pl1000_Body_Mat", "MasterMaterial/Master/Record_Player.mmtr",
        flags=0x00000098, props=classic_character_props(),
        textures=(("BaseMetalMap", "sectionroot/character/body.tex"),),
    )
    to_rt, _ = rtxify([start])
    rt_mat = to_rt.materialList[0]
    assert rt_mat.flags.asInt32 == 0x08000098
    assert len(rt_mat.propertyList) == 37

    mdf_classicize.classicize_mdf(to_rt, FakeMDFApi)
    back = to_rt.materialList[0]
    assert back.flags.asInt32 == 0x00000098
    assert back.mmtrPath == "MasterMaterial/Master/Record_Player.mmtr"
    assert [p.propName for p in back.propertyList] == [
        n for n, _ in classic_character_props()
    ]
    assert [t.texturePath for t in back.textureList] == ["sectionroot/character/body.tex"]


def test_an_expensive_transparent_material_survives_a_round_trip():
    start = make_material(
        "pl1050_Eyes_Out_Mat",
        "MasterMaterial/Master/ExpensiveEyeCornea.mmtr",
        shader=10, flags=0x00000014,
    )
    to_rt, _ = rtxify([start])
    assert to_rt.materialList[0].shaderType == 13
    mdf_classicize.classicize_mdf(to_rt, FakeMDFApi)
    assert to_rt.materialList[0].shaderType == 10


def test_platform_tokens_survive_a_round_trip():
    start = make_material(
        "Mat", "MasterMaterial/Master/Record_Player_Face.mmtr",
        textures=(("BaseMetalMap", "natives/x64/sectionroot/character/body.tex.10"),),
    )
    to_rt, _ = rtxify([start])
    assert (
        to_rt.materialList[0].textureList[0].texturePath
        == "natives/stm/sectionroot/character/body.tex.34"
    )
    mdf_classicize.classicize_mdf(to_rt, FakeMDFApi)
    assert (
        to_rt.materialList[0].textureList[0].texturePath
        == "natives/x64/sectionroot/character/body.tex.10"
    )


def test_both_directions_handle_a_mod_shipped_shader():
    """Both directions re-aim a shader the target game cannot load."""
    shipped = ["record_player_cloth_re3.mmtr.1808160001"]
    mmtr = "MasterMaterial/Master/Record_Player_Cloth_RE3.mmtr"
    to_rt, rt_notes = rtxify([make_material("Body", mmtr)], shipped)
    down = FakeMDF([make_material("Body", mmtr)])
    cl_notes = mdf_classicize.classicize_mdf(down, FakeMDFApi, shipped)

    assert to_rt.materialList[0].mmtrPath == down.materialList[0].mmtrPath
    assert rt_notes[0].startswith(mdf_presets.RETARGET_PREFIX)
    assert cl_notes[0].startswith(mdf_presets.RETARGET_PREFIX)


def test_retarget_prefix_matches_the_reader():
    from re2_outfit_converter.platform import blender_batch

    assert blender_batch.RETARGET_PREFIX == mdf_presets.RETARGET_PREFIX


def test_notes_stay_ascii_for_the_blender_pipe():
    body = make_material(
        "pl2000_Body_Mat",
        "MasterMaterial/Master/Record_Player_Cloth_RE3.mmtr", flags=0x98,
    )
    cornea = make_material(
        "Eyes_Out_Mat", "MasterMaterial/Master/ExpensiveEyeCornea.mmtr",
        shader=10,
    )
    _, notes = rtxify([body, cornea], ["record_player_cloth_re3.mmtr.1808160001"])
    assert notes
    for note in notes:
        note.encode("ascii")


def test_port_suffix_stripping():
    assert (
        mdf_presets.strip_port_suffix("record_player_cloth_re3.mmtr")
        == "record_player_cloth.mmtr"
    )
    assert mdf_presets.strip_port_suffix("env_alpha.mmtr") == "env_alpha.mmtr"
    # A shader actually named "_rt" with nothing before it is left alone.
    assert mdf_presets.strip_port_suffix("_rt.mmtr") == "_rt.mmtr"
    assert (
        mdf_presets.strip_port_suffix("env_alpha_re3rt.mmtr")
        == "env_alpha.mmtr"
    )
    assert (
        mdf_presets.strip_port_suffix("props_default_re2rt.mmtr")
        == "props_default.mmtr"
    )


def test_preset_choice_prefers_the_more_specific_keyword():
    assert mdf_presets.preset_for_mmtr(
        "escape/vfx/shader/shader_0006_emissiveglass.mmtr"
    ) == "Glass.json"
    assert mdf_presets.preset_for_mmtr("env_emissive_re3.mmtr") == "Emissive.json"
    assert mdf_presets.preset_for_mmtr("record_player_cloth.mmtr") == "Character.json"
    assert mdf_presets.preset_for_mmtr("expensiveeyecornea.mmtr") == "Eye Lens.json"
    assert mdf_presets.preset_for_mmtr("character_eyetransparentex.mmtr") == "Tearline.json"
    assert mdf_presets.preset_for_mmtr("totally_unknown.mmtr") == "Character.json"


def test_pak_roots_match_between_blender_and_converter():
    from re2_outfit_converter.platform.formats import RE2_PAK_ROOTS as conv_roots
    from re2_outfit_converter.platform.formats import RE2_PLAYER_ID as conv_player
    from re2_outfit_converter.platform.formats import (
        RE2_SECTIONROOT_CHILDREN as conv_children,
    )

    assert mdf_presets.RE2_PAK_ROOTS == conv_roots
    assert mdf_presets.RE2_SECTIONROOT_CHILDREN == conv_children
    assert mdf_presets.RE2_PLAYER_ID.pattern == conv_player.pattern


def test_authored_texture_paths_are_moved_to_rt_mounts():
    """Escape, VFX, SetModel, and details move. pl2000/mesh parks on Claire.

    RTX has no texture folder there, so the suit checkerboards if it stays.
    Inverse is a no-op: classicize does not move these back.
    """
    cases = {
        "Escape/Character/Player/Pl2000/Mesh/pl2000_Body_ALBM.tex":
            "SectionRoot/Character/Player/pl1000/pl1004/pl2000_Body_ALBM.tex",
        "SectionRoot/Escape/Character/pl2000_Body_ALBM.tex":
            "SectionRoot/Character/pl2000_Body_ALBM.tex",
        "Escape/VFX/RecordSystem/RecordTexture/pl2000/pl2000_body_BloodMask_MSK4.tex":
            "VFX/RecordSystem/RecordTexture/pl2000/pl2000_body_BloodMask_MSK4.tex",
        "SectionRoot/VFX/RecordSystem/pl2000_body_BloodMask_MSK4.tex":
            "VFX/RecordSystem/pl2000_body_BloodMask_MSK4.tex",
        "Escape/SetModel/sm42/case_albm.tex":
            "ObjectRoot/SetModel/sm42/case_albm.tex",
        "SectionRoot/SetModel/sm42/case_albm.tex":
            "ObjectRoot/SetModel/sm42/case_albm.tex",
        "details/tshirt_detail_nrm.tex":
            "SectionRoot/tshirt_detail_nrm.tex",
        "SectionRoot/Character/Player/wap100/Pl2020/Mesh/pl2900_dress_albm.tex":
            "SectionRoot/Character/Player/pl1000/pl1004/pl2900_dress_albm.tex",
        "SectionRoot/Character/Player/pl2000/pl2005/mesh/suit.tex":
            "SectionRoot/Character/Player/pl1000/pl1004/suit.tex",
        "SectionRoot/Character/Player/pl2000/pl2050/mesh/face.tex":
            "SectionRoot/Character/Player/pl2000/pl2050/mesh/face.tex",
        "SectionRoot/Character/Player/pl2050/mesh/face.tex":
            "SectionRoot/Character/Player/pl2050/mesh/face.tex",
    }
    for authored, expected in cases.items():
        mat = make_material(
            "pl2000_Body_Mat", "MasterMaterial/Master/Record_Player.mmtr",
            flags=0x98, props=classic_character_props(),
            textures=(("BaseMetalMap", authored),),
        )
        mdf, _ = rtxify(
            [mat], re3_player_dest="SectionRoot/Character/Player/pl1000/pl1004"
        )
        path = mdf.materialList[0].textureList[0].texturePath
        assert path == expected
        mdf_classicize.classicize_mdf(mdf, FakeMDFApi)
        back = mdf.materialList[0].textureList[0].texturePath
        assert back == expected
