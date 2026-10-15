"""Mesh material slots must stay in source order after a Blender re-export."""

from __future__ import annotations

import sys

from re2_outfit_converter.platform.blender_detect import blender_script_dir

sys.path.insert(0, str(blender_script_dir()))

import mesh_material_order  # noqa: E402


# Claire Latex Demon body: Blender first-seen order vs the file we imported.
_SRC = [
    "pl5300_Body_Mat",
    "pl5300_Skin_Mat",
    "pl5300_clear_Mat",
    "pl5300_Accessories_Mat",
    "pl5300_colorclear_Mat",
    "pl5300_Body2_Mat",
]
_EXPORTED = [
    "pl5300_Skin_Mat",
    "pl5300_Accessories_Mat",
    "pl5300_Body2_Mat",
    "pl5300_clear_Mat",
    "pl5300_colorclear_Mat",
    "pl5300_Body_Mat",
]


def test_latex_demon_body2_returns_to_the_dress_slot():
    """Body2 is the clothing. Export parked it on MDF index 2 (Env_Emissive)."""
    remap = mesh_material_order.slot_remap(_SRC, _EXPORTED)
    assert remap is not None
    assert mesh_material_order.apply_slot_remap_to_indices(remap, 2) == 5
    assert mesh_material_order.apply_slot_remap_to_indices(remap, 0) == 1
    assert mesh_material_order.apply_slot_remap_to_indices(remap, 5) == 0


def test_matching_order_is_identity():
    remap = mesh_material_order.slot_remap(_SRC, list(_SRC))
    assert remap == list(range(6))


def test_different_name_set_is_refused():
    assert mesh_material_order.slot_remap(["A", "B"], ["A", "C"]) is None


def test_round_trip_order_is_symmetric():
    """RT → classic hits the same first-seen shuffle; remap must invert."""
    forward = mesh_material_order.slot_remap(_SRC, _EXPORTED)
    back = mesh_material_order.slot_remap(_EXPORTED, _SRC)
    assert forward is not None and back is not None
    for dest_slot, src_slot in enumerate(forward):
        assert back[src_slot] == dest_slot


class _Tex:
    def __init__(self, path: str) -> None:
        self.textureType = "BaseMetalMap"
        self.texturePath = path


class _Mat:
    def __init__(self, name: str, albedo: str = "") -> None:
        self.materialName = name
        self.textureList = [_Tex(albedo)] if albedo else []


class _Mdf:
    def __init__(self, names: list[str]) -> None:
        self.materialList = [_Mat(n) for n in names]


def test_face_and_eyelash_are_not_swapped_to_match_mesh_order():
    """Same names, different order. Index rename puts the hair shader on the face."""
    mdf = _Mdf([
        "pl1050_Eyelash_Mat",
        "pl1050_Face_Mat",
        "pl1050_Tearline_Mat",
        "pl1050_Eyes_In_Mat",
        "pl1050_Eyes_Out_Mat",
    ])
    mdf.materialList[0].textureList = [_Tex("hair_ALBA.tex")]
    mdf.materialList[1].textureList = [_Tex("face_ALBM.tex")]
    mesh = [
        "pl1050_Face_Mat",
        "pl1050_Eyelash_Mat",
        "pl1050_Tearline_Mat",
        "pl1050_Eyes_In_Mat",
        "pl1050_Eyes_Out_Mat",
    ]
    notes = mesh_material_order.align_mdf_names_to_mesh(mdf, mesh)
    by_name = {mat.materialName: mat for mat in mdf.materialList}
    assert by_name["pl1050_Face_Mat"].textureList[0].texturePath == "face_ALBM.tex"
    assert by_name["pl1050_Eyelash_Mat"].textureList[0].texturePath == "hair_ALBA.tex"
    assert not any("match mesh slot" in note for note in notes)


def test_latex_demon_mdf_names_follow_the_mesh():
    """Holster/Panel leftovers must take the clothing mesh names."""
    mdf = _Mdf([
        "pl5300_Body_Mat",
        "pl5300_Skin_Mat",
        "pl1000_Panel_Mat",
        "pl5300_clear_Mat",
        "pl5300_colorclear_Mat",
        "pl1003_Holster_Mat",
    ])
    notes = mesh_material_order.align_mdf_names_to_mesh(mdf, _SRC)
    assert [m.materialName for m in mdf.materialList] == _SRC
    assert "pl1003_Holster_Mat -> pl5300_Body2_Mat (match mesh slot)" in notes
    assert "pl1000_Panel_Mat -> pl5300_clear_Mat (match mesh slot)" in notes


def test_align_drops_materials_the_mesh_does_not_name():
    """A longer MDF checkerboards every slot. The extra name is removed."""
    mdf = _Mdf(["A", "B"])
    notes = mesh_material_order.align_mdf_names_to_mesh(mdf, ["A"])
    assert [m.materialName for m in mdf.materialList] == ["A"]
    assert notes == ["dropped B (mesh has no slot)"]


def test_align_does_not_add_materials_when_the_mesh_is_longer():
    mdf = _Mdf(["A"])
    assert mesh_material_order.align_mdf_names_to_mesh(mdf, ["A", "B"]) == []
    assert [m.materialName for m in mdf.materialList] == ["A"]


def test_sportsuit_body_drops_the_two_unused_materials():
    """Export drops empty slots. The suit and skin names stay, with their textures."""
    mesh_names = [
        "pl1000_Body_Mat",
        "pl1000_Boots_Mat",
        "pl2000_Supporter_Mat",
        "pl2000_Holsterparts_Mat",
        "pl2000_Button_Mat",
        "pl2000_Bag_Mat",
        "pl2000_light_Mat",
        "pl2000_LightDirt_Mat",
        "pl2000_Lightglass_Mat",
        "wp4500_Cover_Mat",
        "sm46_049_ES_VaccineCase01A_C_Mat__Env_Alph",
        "pl2000_Sling_Mat",
    ]
    mdf = _Mdf([
        "pl2000_Body_Mat",
        "pl1000_Boots_Mat",
        "pl1000_Body_Mat",
        "pl2000_Badge_Mat",
        "pl2000_light_Mat",
        "pl2000_Lightglass_Mat",
        "wp4500_Cover_Mat",
        "pl2000_LightDirt_Mat",
        "pl2000_Holsterparts_Mat",
        "pl2000_Button_Mat",
        "pl2000_Bag_Mat",
        "pl2000_Supporter_Mat",
        "pl2000_Sling_Mat",
        "sm46_049_ES_VaccineCase01A_C_Mat__Env_Alpha",
    ])
    mdf.materialList[1].textureList = [_Tex("pl2000_Ouft_ALBM.tex")]
    mdf.materialList[2].textureList = [_Tex("pl2000_Body_ALBM.tex")]
    used = {"pl1000_Body_Mat", "pl1000_Boots_Mat"}
    notes = mesh_material_order.align_mdf_names_to_mesh(mdf, mesh_names, used)
    got = [m.materialName for m in mdf.materialList]
    assert len(got) == len(mesh_names)
    assert "pl2000_Body_Mat" not in got
    assert "pl2000_Badge_Mat" not in got
    boots = next(m for m in mdf.materialList if m.materialName == "pl1000_Boots_Mat")
    body = next(m for m in mdf.materialList if m.materialName == "pl1000_Body_Mat")
    assert boots.textureList[0].texturePath == "pl2000_Ouft_ALBM.tex"
    assert body.textureList[0].texturePath == "pl2000_Body_ALBM.tex"
    assert "dropped pl2000_Body_Mat (mesh has no slot)" in notes
    assert "dropped pl2000_Badge_Mat (mesh has no slot)" in notes


def test_punisher_jacket_is_renamed_before_extras_are_dropped():
    """The vest donor has to land on pl1000_Boots_Mat before surplus names go."""
    mesh_names = [
        "pl1000_Body_Mat",
        "pl1000_Boots_Mat",
        "pl2020_Skirt_Mat",
        "pl2000_Supporter_Mat",
    ]
    mdf = _Mdf([
        "pl2020_Boots_Mat",
        "pl2020_Skirt_Mat",
        "pl0000_body_strap_Mat",
        "pl1000_Body_Mat",
        "pl2000_Body_Mat",
        "pl2000_Supporter_Mat",
    ])
    mdf.materialList[0].textureList = [_Tex("pl2900_dress_albm.tex")]
    mdf.materialList[3].textureList = [_Tex("pl2900_Body_ALBM.tex")]
    used = {
        "pl1000_Body_Mat",
        "pl1000_Boots_Mat",
        "pl2020_Skirt_Mat",
        "pl2000_Supporter_Mat",
    }
    notes = mesh_material_order.align_mdf_names_to_mesh(mdf, mesh_names, used)
    got = [m.materialName for m in mdf.materialList]
    assert len(got) == len(mesh_names)
    boots = next(m for m in mdf.materialList if m.materialName == "pl1000_Boots_Mat")
    assert boots.textureList[0].texturePath == "pl2900_dress_albm.tex"
    assert "pl2020_Boots_Mat -> pl1000_Boots_Mat (mesh slot had no material)" in notes
    assert "pl2000_Body_Mat" not in got


def test_align_is_noop_when_names_already_match():
    mdf = _Mdf(list(_SRC))
    assert mesh_material_order.align_mdf_names_to_mesh(mdf, _SRC) == []


def test_moto_keeps_authored_material_names():
    """Shared names stay put. The jacket and skirt slots get copies.

    Index rename put the leather on Skin_Mat and the glass shader on the
    jacket. The mesh draws the vest as pl1000_Boots_Mat and the skirt as
    pl2020_Socks_Mat, and neither name is in the MDF. Those two get copies.
    Skin_Mat has no faces, so it is left alone.
    """
    albedos = {
        "pl2020_Boots_Mat": "pl2900_dress_albm.tex",
        "pl2020_Skirt_Mat": "pl2900_Body_ALBM.tex",
        "pl0000_body_strap_Mat": "pl2900_dress3_albm.tex",
        "pl2020_Cardigan_Mat": "pl2900_dress_albm.tex",
        "pl1000_Body_Mat": "pl2900_Body_ALBM.tex",
        "pl2000_Body_Mat": "pl2900_Body_ALBM.tex",
        "pl2000_Supporter_Mat": "pl2900_dress2_albm.tex",
    }
    mdf_names = [
        "pl2020_Boots_Mat",
        "pl2020_Skirt_Mat",
        "pl0000_body_strap_Mat",
        "pl2020_Cardigan_Mat",
        "pl2000_LightDirt_Mat",
        "pl2000_Lightglass_Mat",
        "pl2000_light_Mat",
        "wp4500_Cover_Mat",
        "pl2000_Bag_Mat",
        "sm46_049_ES_VaccineCase01A_A_Mat__Env_Alpha",
        "sm46_049_ES_VaccineCase01A_A_Mat__Env_default",
        "sm46_049_ES_VaccineCase01A_Vaccine_Mat",
        "pl2020_Legholster_Mat",
        "pl1000_Body_Mat",
        "pl2000_Bag_Mat",
        "pl2000_Body_Mat",
        "pl2000_Holsterparts_Mat",
        "pl2000_Props_Mat",
        "pl2000_Sling_Mat",
        "pl2000_Supporter_Mat",
        "sm46_049_ES_VaccineCase01A_C_Mat__Env_Alpha",
    ]
    mesh_names = [
        "Skin_Mat",
        "pl2020_Socks_Mat",
        "pl2020_Skirt_Mat",
        "pl1000_Body_Mat",
        "pl1000_Boots_Mat",
        "pl2020_Cardigan_Mat",
        "pl2000_Props_Mat",
        "pl2000_Holsterparts_Mat",
        "pl2000_Supporter_Mat",
        "pl2020_Legholster_Mat",
        "wp4500_Cover_Mat",
        "pl2000_Bag_Mat",
        "pl2000_Bandage_Mat",
        "pl2000_Sling_Mat",
        "pl2000_light_Mat",
        "pl2000_Lightglass_Mat",
        "pl2000_LightDirt_Mat",
        "sm46_049_ES_VaccineCase01A_Vaccine_Mat",
        "sm46_049_ES_VaccineCase01A_A_Mat__Env_default",
        "sm46_049_ES_VaccineCase01A_A_Mat__Env_Alpha",
        "sm46_049_ES_VaccineCase01A_C_Mat__Env_Alpha",
    ]
    used = {
        "pl1000_Body_Mat",
        "pl1000_Boots_Mat",
        "pl2020_Socks_Mat",
        "pl2000_Supporter_Mat",
    }
    mdf = _Mdf(mdf_names)
    for mat in mdf.materialList:
        albedo = albedos.get(mat.materialName)
        if albedo:
            mat.textureList = [_Tex(albedo)]
    notes = mesh_material_order.align_mdf_names_to_mesh(mdf, mesh_names, used)
    got = [m.materialName for m in mdf.materialList]
    assert len(got) == len(mdf_names)
    assert got[0] == "pl1000_Boots_Mat"
    assert got[2] == "pl2020_Socks_Mat"
    assert got[1] == "pl2020_Skirt_Mat"
    assert got[3] == "pl2020_Cardigan_Mat"
    assert "pl2020_Boots_Mat -> pl1000_Boots_Mat (mesh slot had no material)" in notes
    assert "pl0000_body_strap_Mat -> pl2020_Socks_Mat (only unbound clothing material)" in notes
    assert mdf.materialList[0].textureList[0].texturePath == "pl2900_dress_albm.tex"
    assert mdf.materialList[2].textureList[0].texturePath == "pl2900_dress3_albm.tex"


def test_bunny_eye_slot_does_not_take_the_dress():
    """The ears mesh uses Eyes_In. The only leftover material is the dress.

    Putting that body shader on the eye slot unloads the face file, so the
    head does not draw. The dress stays on its own name.
    """
    mesh_names = [
        "pl1050_Face_Mat",
        "pl1050_Eyelash_Mat",
        "pl1050_Tearline_Mat",
        "pl1050_Eyes_In_Mat",
        "pl1050_Eyes_Out_Mat",
    ]
    mdf = _Mdf([
        "pl1050_Eyelash_Mat",
        "pl1050_Face_Mat",
        "pl2000_Supporter_Mat",
        "pl1050_Eyes_Out_Mat",
        "pl1050_Tearline_Mat",
    ])
    mdf.materialList[0].textureList = [_Tex("pl1070_Hair_ALBA.tex")]
    mdf.materialList[1].textureList = [_Tex("pl1060_Face_ALBM.tex")]
    mdf.materialList[2].textureList = [_Tex("pl2900_dress2_albm.tex")]
    mdf.materialList[3].textureList = [_Tex("pl1050_Eye_Out_NRMR.tex")]
    mdf.materialList[4].textureList = [_Tex("pl1050_Tear.tex")]
    used = set(mesh_names)
    notes = mesh_material_order.align_mdf_names_to_mesh(mdf, mesh_names, used)
    got = [m.materialName for m in mdf.materialList]
    assert "pl1050_Eyes_In_Mat" not in got
    assert "pl2000_Supporter_Mat" in got
    assert "pl1050_Face_Mat" in got
    dress = next(m for m in mdf.materialList if m.materialName == "pl2000_Supporter_Mat")
    assert dress.textureList[0].texturePath == "pl2900_dress2_albm.tex"
    assert not any("Eyes_In" in note for note in notes)


def test_sibling_mesh_path(tmp_path):
    mdf = tmp_path / "pl1004.mdf2.10"
    mesh = tmp_path / "pl1004.mesh.1808312334"
    rt = tmp_path / "pl1004.mesh.2109108288"
    mdf.write_bytes(b"x")
    mesh.write_bytes(b"y")
    rt.write_bytes(b"z")
    (tmp_path / "pl1004_blend.mesh.1808312334").write_bytes(b"z")
    assert mesh_material_order.sibling_mesh_path(
        str(mdf), "mesh.2109108288"
    ) == str(rt)
    assert mesh_material_order.sibling_mesh_path(
        str(mdf), "mesh.1808312334"
    ) == str(mesh)


def test_cut_vaccine_name_is_kept_when_an_unused_name_is_earlier():
    mesh = [
        "pl1000_Body_Mat",
        "sm46_049_ES_VaccineCase01A_C_Mat__Env_Alph",
    ]
    mdf = _Mdf([
        "sm46_049_ES_VaccineCase01A_C_Mat__Env_Alpha",
        "pl2000_Badge_Mat",
        "pl1000_Body_Mat",
    ])
    notes = mesh_material_order.align_mdf_names_to_mesh(mdf, mesh)
    got = [m.materialName for m in mdf.materialList]
    assert "pl2000_Badge_Mat" not in got
    assert "sm46_049_ES_VaccineCase01A_C_Mat__Env_Alpha" in got
    assert "dropped pl2000_Badge_Mat (mesh has no slot)" in notes


def test_one_role_donor_is_not_renamed_onto_every_hole():
    """Skirt already disagrees about its slot, so this is not an index rename."""
    mdf = _Mdf(["pl2020_Skirt_Mat", "pl2000_Body_Mat", "pl1000_Other_Mat"])
    for mat in mdf.materialList:
        mat.textureList = [_Tex("dress.tex")]
    notes = mesh_material_order.align_mdf_names_to_mesh(
        mdf,
        ["pl1000_Body_Mat", "pl2020_Body_Mat", "pl2020_Skirt_Mat"],
        {"pl1000_Body_Mat", "pl2020_Body_Mat", "pl2020_Skirt_Mat"},
    )
    got = [m.materialName for m in mdf.materialList]
    assert "pl1000_Body_Mat" in got
    assert "pl2020_Body_Mat" not in got
    assert "pl2000_Body_Mat -> pl1000_Body_Mat (mesh slot had no material)" in notes


def test_longer_latex_list_drops_the_extra_then_keeps_the_dress():
    mesh = [
        "pl5300_Body_Mat",
        "pl5300_Skin_Mat",
        "pl5300_clear_Mat",
        "pl5300_colorclear_Mat",
        "pl5300_Body2_Mat",
    ]
    mdf = _Mdf([
        "pl5300_Body_Mat",
        "pl5300_Skin_Mat",
        "pl1000_Panel_Mat",
        "pl5300_clear_Mat",
        "pl5300_colorclear_Mat",
        "pl1003_Holster_Mat",
    ])
    notes = mesh_material_order.align_mdf_names_to_mesh(mdf, mesh)
    assert [m.materialName for m in mdf.materialList] == mesh
    assert "dropped pl1000_Panel_Mat (mesh has no slot)" in notes
    assert "pl1003_Holster_Mat -> pl5300_Body2_Mat (match mesh slot)" in notes


_BATTLESUIT = [
    "pl1001_Gun_Mat",
    "pl1001_Tanktop_Mat",
    "pl1001_Trousers_Mat",
    "pl1001_Boots_Mat",
    "pl1001_Chain_Mat",
    "pl1001_Holster_Mat",
    "pl1001_Body_Mat",
    "pl1001_Sling_Mat",
    "pl1001_Radio_Mat",
    "pl1001_Panel_Mat",
]
_BATTLESUIT_MDF = [
    "pl1001_Body_Mat",
    "pl1001_Boots_Mat",
    "pl1001_Holster_Mat",
    "pl1001_Tanktop_Mat",
    "pl1001_Trousers_Mat",
    "pl1001_Chain_Mat",
    "pl1001_Gun_Mat",
    "pl1001_Sling_Mat",
    "pl1001_Radio_Mat",
    "pl1001_Panel_Mat",
]


def test_duplicate_props_name_keeps_the_suit_map_and_fills_skin():
    """RTX binds one material per name. The white copy must not win."""
    mdf = _Mdf([
        "pl1003_Props_Mat",
        "pl1003_Props_Mat",
        "pl1003_Props_Mat",
        "pl1003_Other_Mat",
    ])
    mdf.materialList[0].textureList = [_Tex("pl1003_Prop1_ALBM.tex")]
    mdf.materialList[1].textureList = [_Tex("pl1003_Prop4_ALBM.tex")]
    mdf.materialList[2].textureList = [_Tex("pl1003_Prop5_ALBM.tex")]
    sizes = {
        "pl1003_prop1_albm.tex": 100,
        "pl1003_prop4_albm.tex": 5000,
        "pl1003_prop5_albm.tex": 5000,
    }

    def rank(mat) -> int:
        return sizes.get(mesh_material_order._albedo_key(mat), 0)

    mesh = [
        "pl1003_Gun_Mat",
        "pl1003_Props_Mat",
        "pl1003_Chain_Mat",
        "pl1003_Skin_Mat",
    ]
    mesh_material_order.align_mdf_names_to_mesh(
        mdf, mesh, {"pl1003_Props_Mat", "pl1003_Skin_Mat"}, albedo_rank=rank,
    )
    by_name = {mat.materialName: mat for mat in mdf.materialList}
    assert by_name["pl1003_Props_Mat"].textureList[0].texturePath.endswith(
        "Prop4_ALBM.tex"
    )
    assert by_name["pl1003_Skin_Mat"].textureList[0].texturePath.endswith(
        "Prop5_ALBM.tex"
    )


def test_last_duplicate_on_the_mesh_slot_does_not_keep_the_small_map():
    """The last copy can sit on the mesh index and still be the placeholder."""
    mdf = _Mdf([
        "pl1003_Props_Mat",
        "pl1003_Gun_Mat",
        "pl1003_Props_Mat",
        "pl1003_Chain_Mat",
    ])
    mdf.materialList[0].textureList = [_Tex("pl1003_Prop4_ALBM.tex")]
    mdf.materialList[2].textureList = [_Tex("pl1003_Prop1_ALBM.tex")]
    sizes = {
        "pl1003_prop4_albm.tex": 5000,
        "pl1003_prop1_albm.tex": 100,
    }

    def rank(mat) -> int:
        return sizes.get(mesh_material_order._albedo_key(mat), 0)

    mesh = [
        "pl1003_Skin_Mat",
        "pl1003_Gun_Mat",
        "pl1003_Props_Mat",
        "pl1003_Chain_Mat",
    ]
    mesh_material_order.align_mdf_names_to_mesh(
        mdf, mesh, {"pl1003_Props_Mat", "pl1003_Skin_Mat"}, albedo_rank=rank,
    )
    by_name = {mat.materialName: mat for mat in mdf.materialList}
    assert by_name["pl1003_Props_Mat"].textureList[0].texturePath.endswith(
        "Prop4_ALBM.tex"
    )


def test_battlesuit_keeps_the_suit_texture_on_the_tanktop_name():
    """The body mesh slot is named Tanktop, and that material has the suit maps.

    Renaming by index put the jacket pants on that slot. The name is what
    RTX looks up, so Tanktop has to keep the top texture and the wet mask.
    """
    mdf = _Mdf(_BATTLESUIT_MDF)
    mdf.materialList[3].textureList = [
        _Tex("pl1001_Top_ALBM.tex"),
        _Tex("pl1001_wetMask_MSK1.tex"),
    ]
    notes = mesh_material_order.align_mdf_names_to_mesh(mdf, _BATTLESUIT)
    suit = next(m for m in mdf.materialList if m.materialName == "pl1001_Tanktop_Mat")
    assert suit.textureList[0].texturePath == "pl1001_Top_ALBM.tex"
    assert suit.textureList[1].texturePath == "pl1001_wetMask_MSK1.tex"
    assert "pl1001_Tanktop_Mat ->" not in " ".join(notes)


def test_alternate_mdf_uses_the_parent_body_mesh(tmp_path):
    body = tmp_path / "pl1001"
    alt = body / "pl1001_01"
    alt.mkdir(parents=True)
    mesh = body / "pl1001.mesh.2109108288"
    classic = body / "pl1001.mesh.1808312334"
    mdf = alt / "pl1001_01.mdf2.10"
    mesh.write_bytes(b"z")
    classic.write_bytes(b"y")
    mdf.write_bytes(b"x")
    assert mesh_material_order.mesh_path_for_mdf(
        str(mdf), "mesh.2109108288"
    ) == str(mesh)
    assert mesh_material_order.mesh_path_for_mdf(
        str(mdf), "mesh.1808312334"
    ) == str(classic)


def test_albedo_rank_uses_the_versioned_file_not_a_longer_stem(tmp_path):
    (tmp_path / "pl1003_prop1_albm.tex.10").write_bytes(b"a" * 10)
    (tmp_path / "pl1003_prop10_albm.tex.10").write_bytes(b"b" * 80)
    mdf = _Mdf(["pl1003_Props_Mat"])
    mdf.materialList[0].textureList = [_Tex("pl1003_Prop1_ALBM.tex")]
    rank = mesh_material_order.albedo_rank_in_folder(str(tmp_path))
    assert rank(mdf.materialList[0]) == 10


def test_index_drop_search_stops_when_the_subset_count_is_huge():
    mesh = [f"slot_{i}" for i in range(10)]
    names = [f"unused_{i}" for i in range(16)]
    notes = mesh_material_order._index_rename_after_dropping_extras(
        _Mdf(names), mesh
    )
    assert notes is None
