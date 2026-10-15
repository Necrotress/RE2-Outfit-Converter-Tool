# Classicize RT (RE2RT) MDF materials for non-RT RE2.
# Runs inside Blender batch alongside RE Mesh Editor's file_re_mdf.
#
# Ground truth (Ultimate Claire RT vs Non-RT dual pack):
#   - same mmtr (Record_Player.mmtr)
#   - same texture types + paths
#   - flags: clear SSSProfileUsed only  (e.g. 134217880 -> 152)
#   - drop exactly 3 RT-only properties
#   - other property values stay the same
#
# Emily-over-Sherry edge case: face PressureMap pointed at a mod-local
# pl3050_RTT.rtex (shipped as rtex.5). Classic Face presets use NullWhite
# for PressureMap; loading RT rtex stubs crashes on save load. We rewrite
# mod-local .rtex bindings to classic nulls and leave game VFX/RecordSystem
# paths alone.

from __future__ import annotations

import mdf_presets

# When the RT master material is a different shader than classic, rebuild
# from the classic preset. Do not rebuild a material that already uses a
# classic mmtr — Emissive.json is a larger slot layout than live
# Env_Emissive materials (dog tags), and that mismatch crashes on load.
MMTR_TO_PRESET = {
    "weapon_default.mmtr": "Weapon.json",
    "eyeleon.mmtr": "Eye.json",
    "expensiveeyecornea.mmtr": "Eye Lens.json",
    "eye_tear.mmtr": "Tearline.json",
    # RT-only tearline shader. Classic RE2 uses Eye_Tear.mmtr with no
    # texture slots. Keeping Character_EyeTransparentEX crashes non-RT.
    "character_eyetransparentex.mmtr": "Tearline.json",
    "hair.mmtr": "Eyelash.json",
    "record_player_hair.mmtr": "Hair.json",
}

# Already-classic shaders: clear the RT flag and drop RT-only props only.
STRIP_ONLY_MMTR = {
    "record_player.mmtr",
    "record_player_face.mmtr",
    "env_emissive.mmtr",
}

RT_ONLY_PROPS = {
    "CERD_D_BloodColorMultiplier",
    "CustomSpecularReflecance",
    "UseCustomSpecularReflectance",
}

# MDFFlags bit 27. RT player materials set it; classic RE2 never does.
SSS_PROFILE_USED_FLAG = 0x08000000

# RT expensive-transparent shader type → the classic RE2 value.
SHADER_TYPE_TO_CLASSIC = {13: 10}

_GAME = "RE2"

# Classic RE2 Face.json defaults for slots that RT mods bind to local RTT.
_NULL_WHITE = "systems/rendering/NullWhite.tex"
_NULL_BLACK = "systems/rendering/NullBlack.tex"
_NULL_BLACK_MSK4 = (
    "VFX/RecordSystem/RecordTexture/BaseTextures/null_black_MSK4.tex"
)


def _remap_path(path: str) -> str:
    out = path or ""
    replacements = (
        ("natives/stm/", "natives/x64/"),
        ("natives\\stm\\", "natives\\x64\\"),
        ("natives/STM/", "natives/x64/"),
        ("natives\\STM\\", "natives\\x64\\"),
        (".tex.34", ".tex.10"),
    )
    for old, new in replacements:
        out = out.replace(old, new)
    return out


def _is_game_record_rtex(path: str) -> bool:
    """True for engine VFX RecordSystem paths (exist in classic game files)."""
    lower = path.replace("\\", "/").lower()
    return "vfx/recordsystem/" in lower or lower.startswith("vfx/recordsystem/")


def _is_mod_local_rtex(path: str) -> bool:
    lower = path.replace("\\", "/").lower()
    if ".rtex" not in lower:
        return False
    if _is_game_record_rtex(path):
        return False
    return True


def _safe_texture_path(texture_type: str, path: str) -> str:
    """Remap platform tokens; replace mod-local .rtex with classic nulls."""
    out = _remap_path(path)
    if not _is_mod_local_rtex(out):
        return out
    t = texture_type or ""
    if t in ("PressureMap", "IntensityMap"):
        return _NULL_WHITE
    if t.startswith("Rec_") or t == "BloodMask":
        return _NULL_BLACK_MSK4
    return _NULL_BLACK


def _strip_rt_bits(mat) -> tuple[int, int, int]:
    """Clear SSSProfileUsed; drop RT-only props; sanitize rtex paths.

    Returns (old_flags, dropped_props, rtex_rewrites).
    """
    before = int(mat.flags.asInt32)
    mat.flags.asInt32 = before & ~SSS_PROFILE_USED_FLAG
    mat.shaderType = SHADER_TYPE_TO_CLASSIC.get(
        int(mat.shaderType), int(mat.shaderType)
    )
    kept = [p for p in mat.propertyList if p.propName not in RT_ONLY_PROPS]
    dropped = len(mat.propertyList) - len(kept)
    mat.propertyList = kept
    rtex_hits = 0
    for tex in mat.textureList:
        new_path = _safe_texture_path(tex.textureType, tex.texturePath)
        if new_path != tex.texturePath:
            rtex_hits += 1
        tex.texturePath = new_path
    mat.mmtrPath = _remap_path(mat.mmtrPath)
    return before, dropped, rtex_hits


def _rebuild(mat, preset_name: str, file_re_mdf):
    preset = mdf_presets.load_preset(_GAME, preset_name)
    return mdf_presets.rebuild_from_preset(
        mat, preset, file_re_mdf, _safe_texture_path
    )


def classicize_mdf(mdf_file, file_re_mdf, shipped_mmtr=None) -> list[str]:
    """Mutate mdf_file materials in place for classic RE2. Returns notes."""
    shipped = mdf_presets.shipped_bases(shipped_mmtr)
    notes: list[str] = []
    for index, mat in enumerate(list(mdf_file.materialList)):
        base = mdf_presets.mmtr_base(mat.mmtrPath)

        # A shader the mod brought along is an RT build classic cannot load.
        if base in shipped:
            action, target = mdf_presets.resolve_shipped_shader(
                mat, base, shipped, _GAME
            )
            if action == "rename":
                mat.mmtrPath = f"MasterMaterial/Master/{target}"
                _strip_rt_bits(mat)
                notes.append(
                    f"{mdf_presets.RETARGET_PREFIX}{mat.materialName}: "
                    f"{base} -> stock {target} (mod-shipped shader, same slots)"
                )
                continue
            preset_name = target
            old_props = len(mat.propertyList)
            new_mat = _rebuild(mat, preset_name, file_re_mdf)
            mdf_file.materialList[index] = new_mat
            notes.append(
                f"{mdf_presets.RETARGET_PREFIX}{new_mat.materialName}: "
                f"{base} has no classic build, rebuilt on {preset_name} "
                f"({new_mat.mmtrPath}, "
                f"props {old_props} -> {len(new_mat.propertyList)})"
            )
            continue

        # Ground-truth path for body/face player materials.
        if base in STRIP_ONLY_MMTR or base not in MMTR_TO_PRESET:
            preset_name = mdf_presets.PRESET_BY_MMTR.get(base)
            if preset_name:
                kind = mdf_presets.layout_kind(
                    mat, mdf_presets.load_preset("RE2RT", preset_name)
                )
                # Env_Emissive's live table is smaller than Emissive.json.
                # Rebuilding a broken one onto that preset crashes on load.
                if kind == "corrupt" and base != "env_emissive.mmtr":
                    old_props = len(mat.propertyList)
                    new_mat = _rebuild(mat, preset_name, file_re_mdf)
                    mdf_file.materialList[index] = new_mat
                    notes.append(
                        f"{new_mat.materialName}: broken property table, "
                        f"rebuilt on {preset_name} "
                        f"(props {old_props} -> {len(new_mat.propertyList)})"
                    )
                    continue
            before, dropped, rtex_hits = _strip_rt_bits(mat)
            extra = f", rewrote {rtex_hits} mod rtex path(s)" if rtex_hits else ""
            notes.append(
                f"{mat.materialName}: strip RT "
                f"(flags {before} -> {mat.flags.asInt32}, "
                f"dropped {dropped} props"
                f"{extra})"
            )
            continue

        # Slot-layout rebuild for emissive / weapon / eyes / hair variants.
        preset_name = MMTR_TO_PRESET[base]
        old_flags = int(mat.flags.asInt32)
        old_props = len(mat.propertyList)
        new_mat = _rebuild(mat, preset_name, file_re_mdf)
        mdf_file.materialList[index] = new_mat
        notes.append(
            f"{new_mat.materialName}: preset {preset_name} "
            f"(flags {old_flags} -> {new_mat.flags.asInt32}, "
            f"props {old_props} -> {len(new_mat.propertyList)})"
        )
    return notes
