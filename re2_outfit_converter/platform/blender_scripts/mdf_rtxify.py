# Prepare classic RE2 MDF materials for RE2 RT.
# Mirror of mdf_classicize.py; runs inside Blender alongside file_re_mdf.
#
# Ground truth (Ultimate Claire dual pack, plus Emily/Jessica RT mods):
#   - RT player skin and cloth materials set MDF flag bit 27, SSSProfileUsed
#     (0x08000098 on body, 0x08000099 on face). Classic has the bit clear.
#   - Expensive-transparent materials use shaderType 13 in RT. Classic RE2
#     uses 10 and classic RE3 uses 11 for the same slot.
#   - Hair, decal, emissive and environment materials are byte-identical
#     apart from the file version, so they are left alone.
#
# A shipped classic .mmtr cannot load in RT (the game's copies are
# .mmtr.2109101635, and it has no Record_Player_Cloth_RE3). Leaving those
# names on the body made Hardcore Punisher draw the head only: the head
# already uses Hair / Record_Player_Face, which RT ships. Materials are
# moved onto the closest stock RT shader. Texture folders are not remounted.
# Inverse is the same re-aim in mdf_classicize.py.

from __future__ import annotations

import mdf_presets

SSS_PROFILE_USED_FLAG = 0x08000000  # MDFFlags bit 27

# Stock shaders whose RT counterparts carry SSSProfileUsed. Taken from the
# RE2 / RE2RT preset pairs, which differ only in this bit and the shader type:
# Character 0x99→0x08000099, Face 0x98→0x08000098, Eyelash 0x83→0x08000083.
# Record_Player_Hair stays clear in both.
SSS_MMTR = frozenset({
    "record_player.mmtr",
    "record_player_face.mmtr",
    "hair.mmtr",
})

# Classic expensive-transparent shader types → the RT value.
SHADER_TYPE_TO_RT = {10: 13, 11: 13}

# Shaders that declare more parameters in the RT build, and the preset pair
# that spells out the difference. Record_Player goes from 34 to 37: the three
# mdf_classicize.RT_ONLY_PROPS drops on the way back. Only shaders whose two
# presets are a clean superset belong here — the Emissive pair, for one, was
# dumped from different materials and does not describe a build difference.
RT_PROPERTY_PRESETS = {
    "record_player.mmtr": "Character.json",
}

_GAME = "RE2RT"
_CLASSIC_GAME = "RE2"


def _remap_path(path: str) -> str:
    out = path or ""
    replacements = (
        ("natives/x64/", "natives/stm/"),
        ("natives\\x64\\", "natives\\stm\\"),
        ("natives/X64/", "natives/stm/"),
        ("natives\\X64\\", "natives\\stm\\"),
        (".tex.10", ".tex.34"),
        (".TEX.10", ".tex.34"),
    )
    for old, new in replacements:
        out = out.replace(old, new)
    return out


_RE3_PLAYER_DEST = None


def _safe_texture_path(texture_type: str, path: str) -> str:
    """Remap platform tokens, then put textures where RT mounts files.

    A player folder the RT dump does not have (wap100) is moved onto
    the costume folder. Textures under pl2000/mesh are too: RTX has no
    mesh texture folder on that character, so the suit checkerboards
    if they stay there. Face files under pl2000/pl2050 stay.
    Rec_RTT is not rewritten to Claire's record texture.
    """
    del texture_type
    nested = mdf_presets.nest_under_sectionroot(_remap_path(path))
    dest = _RE3_PLAYER_DEST or ""
    nested = mdf_presets.retarget_unmounted_player_path(nested, dest)
    return mdf_presets.retarget_re3_player_path(nested, dest)


def _add_rt_properties(mat, file_re_mdf) -> int:
    """Top a stock material up to the parameters its RT shader declares."""
    preset_name = RT_PROPERTY_PRESETS.get(mdf_presets.mmtr_base(mat.mmtrPath))
    if not preset_name:
        return 0
    return mdf_presets.align_properties_to_preset(
        mat,
        mdf_presets.load_preset(_CLASSIC_GAME, preset_name),
        mdf_presets.load_preset(_GAME, preset_name),
        file_re_mdf,
    )


def _upgrade_in_place(mat, file_re_mdf) -> tuple[int, int, int, int]:
    """Set the RT flag, shader type and parameters on a kept-shader material."""
    before_flags = int(mat.flags.asInt32)
    before_shader = int(mat.shaderType)
    if mdf_presets.mmtr_base(mat.mmtrPath) in SSS_MMTR:
        mat.flags.asInt32 = before_flags | SSS_PROFILE_USED_FLAG
    mat.shaderType = SHADER_TYPE_TO_RT.get(before_shader, before_shader)
    added = _add_rt_properties(mat, file_re_mdf)
    rtex_hits = 0
    for tex in mat.textureList:
        old = tex.texturePath or ""
        tex.texturePath = _safe_texture_path(tex.textureType, tex.texturePath)
        if ".rtex" in old.lower() and ".rtex" not in tex.texturePath.lower():
            rtex_hits += 1
    mat.mmtrPath = _remap_path(mat.mmtrPath)
    return before_flags, before_shader, added, rtex_hits


def _use_jacket_shading(mat) -> None:
    """Shade rebuilt cloth like vanilla Claire's jacket.

    RTX has no cloth shader. Record_Player draws the jacket when its
    properties are the jacket preset: Rec_Cloth 1, Fresnel 0, no detail
    AO. RE3 cloth materials store the opposite (Rec_Cloth 0, Fresnel 1)
    and copying those values leaves the leather looking like skin.
    Textures stay on the material. A material that was already
    Record_Player is not passed here, so real skin is left alone.
    """
    preset = mdf_presets.load_preset(_GAME, "Character.json")
    defaults = {
        p["Property Name"]: mdf_presets.prop_value_list(p.get("Value"))
        for p in preset["Property List"]
    }
    for prop in mat.propertyList:
        values = defaults.get(prop.propName)
        if values is not None and len(list(prop.propValue)) == len(values):
            prop.propValue = list(values)


def _rebuild_on_rt_preset(mat, preset_name: str, file_re_mdf):
    preset = mdf_presets.load_preset(_GAME, preset_name)
    new_mat = mdf_presets.rebuild_from_preset(
        mat, preset, file_re_mdf, _safe_texture_path
    )
    if mdf_presets.mmtr_base(new_mat.mmtrPath) in SSS_MMTR:
        new_mat.flags.asInt32 = (
            int(new_mat.flags.asInt32) | SSS_PROFILE_USED_FLAG
        )
    source = mdf_presets.mmtr_base(mat.mmtrPath)
    if (
        "cloth" in source
        and mdf_presets.mmtr_base(new_mat.mmtrPath) == "record_player.mmtr"
    ):
        _use_jacket_shading(new_mat)
    return new_mat


def rtxify_mdf(
    mdf_file, file_re_mdf, shipped_mmtr=None, re3_player_dest=None
) -> list[str]:
    """Mutate mdf_file materials in place for RE2 RT. Returns notes."""
    global _RE3_PLAYER_DEST
    shipped = mdf_presets.shipped_bases(shipped_mmtr)
    notes: list[str] = []
    prev_dest = _RE3_PLAYER_DEST
    _RE3_PLAYER_DEST = re3_player_dest or None

    try:
        return _rtxify_mdf_body(mdf_file, file_re_mdf, shipped, notes)
    finally:
        _RE3_PLAYER_DEST = prev_dest


def _rtxify_mdf_body(mdf_file, file_re_mdf, shipped, notes) -> list[str]:
    for index, mat in enumerate(list(mdf_file.materialList)):
        base = mdf_presets.mmtr_base(mat.mmtrPath)

        if base in shipped or base not in mdf_presets.STOCK_RE2_MMTR:
            # RTX does not ship this shader. A classic .mmtr does not load
            # there, and one material still naming it makes the whole mesh
            # draw nothing. The head is a different file, so it still draws.
            # The usual case is a master material the mod brought along.
            # Escape/VFX/Shader/shader_0006_EmissiveGlass_RE3.mmtr is the
            # same failure when that file was missed from the shipped list.
            action, target = mdf_presets.resolve_shipped_shader(
                mat, base, shipped, _GAME
            )
            if action == "rename":
                mat.mmtrPath = f"MasterMaterial/Master/{target}"
                _upgrade_in_place(mat, file_re_mdf)
                notes.append(
                    f"{mdf_presets.RETARGET_PREFIX}{mat.materialName}: "
                    f"{base} -> stock {target} (mod-shipped shader, same slots)"
                )
                continue

            preset_name = target
            old_props = len(mat.propertyList)
            new_mat = _rebuild_on_rt_preset(mat, preset_name, file_re_mdf)
            mdf_file.materialList[index] = new_mat
            notes.append(
                f"{mdf_presets.RETARGET_PREFIX}{new_mat.materialName}: "
                f"{base} has no RT build, rebuilt on {preset_name} "
                f"({new_mat.mmtrPath}, "
                f"props {old_props} -> {len(new_mat.propertyList)})"
            )
            continue

        preset_name = (
            RT_PROPERTY_PRESETS.get(base) or mdf_presets.PRESET_BY_MMTR.get(base)
        )
        if preset_name:
            kind = mdf_presets.layout_kind(
                mat, mdf_presets.load_preset(_CLASSIC_GAME, preset_name)
            )
            if kind == "corrupt":
                old_props = len(mat.propertyList)
                new_mat = _rebuild_on_rt_preset(mat, preset_name, file_re_mdf)
                mdf_file.materialList[index] = new_mat
                notes.append(
                    f"{new_mat.materialName}: broken property table, "
                    f"rebuilt on {preset_name} "
                    f"(props {old_props} -> {len(new_mat.propertyList)})"
                )
                continue

        before_flags, before_shader, added, rtex_hits = _upgrade_in_place(
            mat, file_re_mdf
        )
        changes = []
        if int(mat.flags.asInt32) != before_flags:
            changes.append(f"flags {before_flags} -> {mat.flags.asInt32}")
        if int(mat.shaderType) != before_shader:
            changes.append(f"shaderType {before_shader} -> {mat.shaderType}")
        if added > 0:
            changes.append(f"added {added} RT-only prop(s)")
        elif added < 0:
            changes.append("non-stock property layout, left as-is")
        if rtex_hits:
            changes.append(f"rewrote {rtex_hits} rtex path(s)")
        if changes:
            notes.append(f"{mat.materialName}: " + ", ".join(changes))
    return notes
