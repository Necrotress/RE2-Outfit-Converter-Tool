# Shared MDF preset handling for both conversion directions.
# Runs inside Blender batch alongside RE Mesh Editor's file_re_mdf.
#
# A preset is one of RE Mesh Editor's material JSON exports. Rebuilding a
# material from a preset is how we move it onto a different master material:
# the preset defines the slot layout the target shader expects, and whatever
# the source material already had under the same name carries over.

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable

_RE3_PLAYER_ID = re.compile(r"^pl2\d{3}$", re.IGNORECASE)
_FACE_MESH_IDS = frozenset({"pl1050", "pl1060", "pl1070", "pl2050"})
# Same rule as formats.RE2_PLAYER_ID. Blender batch does not import formats.
RE2_PLAYER_ID = re.compile(r"^pl\d{4}$", re.IGNORECASE)

# Master materials shipped by RE2 itself, from both dumps'
# natives/.../mastermaterial/master. Used to tell a mod's own shader apart
# from one the game already provides.
STOCK_RE2_MMTR = frozenset({
    "character_default.mmtr",
    "character_eyetransparentex.mmtr",
    "character_fur.mmtr",
    "character_hair.mmtr",
    "character_zombie.mmtr",
    "emissive.mmtr",
    "env_alpha.mmtr",
    "env_alphadissolve.mmtr",
    "env_decal.mmtr",
    "env_default.mmtr",
    "env_default_blendcolor.mmtr",
    "env_default_cavity.mmtr",
    "env_default_detail.mmtr",
    "env_default_without_wet.mmtr",
    "env_emissive.mmtr",
    "env_emissivemask.mmtr",
    "env_g5train.mmtr",
    "env_gimmickwiringnode.mmtr",
    "env_jewelry.mmtr",
    "env_mirror.mmtr",
    "env_rainleafefx.mmtr",
    "env_sm42_229_glassline.mmtr",
    "env_wetfloor_decal.mmtr",
    "env_wetfloor_standard.mmtr",
    "env_witherplant.mmtr",
    "expensiveeyecornea.mmtr",
    "eye.mmtr",
    "eye_tear.mmtr",
    "eyeleon.mmtr",
    "glass_expensivetransparent.mmtr",
    "glass_frosted.mmtr",
    "glass_reflectivetransparent.mmtr",
    "glass_reflectivetransparent_fakesphere.mmtr",
    "glass_transparency_spheremap.mmtr",
    "hair.mmtr",
    "hair_dither.mmtr",
    "interact_default.mmtr",
    "item_default.mmtr",
    "props_default.mmtr",
    "record_default.mmtr",
    "record_em0000_defect.mmtr",
    "record_enemydefault.mmtr",
    "record_enemyemissive.mmtr",
    "record_fur.mmtr",
    "record_player.mmtr",
    "record_player_face.mmtr",
    "record_player_hair.mmtr",
    "record_player_tohu.mmtr",
    "record_zombie_cloth.mmtr",
    "record_zombie_skin.mmtr",
    "uv_scroll.mmtr",
    "vfx_character_bloodpaint.mmtr",
    "vfx_character_hair_bloodpaint.mmtr",
    "vfx_character_neck_bloodpaint.mmtr",
    "vfx_water_bh2r_chain.mmtr",
    "weapon_default.mmtr",
    "zombie_clothdamage.mmtr",
    "zombie_clothdamage_body.mmtr",
})

# Suffixes mod authors append when porting a shader in from another RE title.
# Longer suffixes first. "_rt" is a suffix of "_re3rt", so checking it
# first would leave "env_alpha_re3" and miss the stock shader.
PORT_SUFFIXES = ("_re3rt", "_re2rt", "_re3", "_re2", "_re8", "_rt")

# Keyword → preset, most specific first. Picks a stock shader for a material
# whose own master material cannot exist in the target game.
PRESET_BY_KEYWORD: tuple[tuple[str, str], ...] = (
    ("eyetransparent", "Tearline.json"),
    ("tear", "Tearline.json"),
    ("cornea", "Eye Lens.json"),
    ("eyelash", "Eyelash.json"),
    ("eye", "Eye.json"),
    ("face", "Face.json"),
    ("skin", "Face.json"),
    ("hair", "Hair.json"),
    # Glass before emissive: an "emissive glass" panel is a transparent
    # surface, and the Glass preset pair matches slot for slot across the two
    # builds while the Emissive pair was dumped from two different materials.
    ("glass", "Glass.json"),
    ("emissive", "Emissive.json"),
    ("decal", "Decal.json"),
    ("weapon", "Weapon.json"),
    ("cloth", "Character.json"),
    ("player", "Character.json"),
    ("character", "Character.json"),
)

FALLBACK_PRESET = "Character.json"

# Stock shaders we hold a preset pair for, so we can tell whether a material
# actually fits the shader it names.
PRESET_BY_MMTR = {
    "record_player.mmtr": "Character.json",
    "record_player_face.mmtr": "Face.json",
    "record_player_hair.mmtr": "Hair.json",
    "hair.mmtr": "Eyelash.json",
    "eyeleon.mmtr": "Eye.json",
    "expensiveeyecornea.mmtr": "Eye Lens.json",
    "eye_tear.mmtr": "Tearline.json",
    "weapon_default.mmtr": "Weapon.json",
    "env_decal.mmtr": "Decal.json",
    "env_emissive.mmtr": "Emissive.json",
    "glass_expensivetransparent.mmtr": "Glass.json",
}

# Marks a note about a material moved onto a different master material, so the
# caller can pull those out of Blender's stdout. Notes stay ASCII: Blender
# writes to a pipe under the console code page and mangles anything else.
RETARGET_PREFIX = "retarget: "

# Top-level folders RE2's pak mounts. Keep in step with formats.RE2_PAK_ROOTS.
RE2_PAK_ROOTS = frozenset({
    "alphatest",
    "autoplay",
    "cafelatte",
    "gen",
    "hikako",
    "mastermaterial",
    "movie",
    "objectroot",
    "re_engine_library",
    "sectionroot",
    "streaming",
    "systems",
    "test",
    "tool",
    "vfx",
})
RE2_SECTIONROOT_CHILDREN = frozenset({
    "animation",
    "behaviortree",
    "character",
    "collision",
    "cutscene",
    "dynamics",
    "environment",
    "event",
    "leveldesign",
    "light",
    "message",
    "props",
    "sound",
    "ui",
    "userdata",
})
_NULL_WHITE = "systems/rendering/NullWhite.tex"
_NULL_BLACK = "systems/rendering/NullBlack.tex"
_NULL_BLACK_MSK4 = (
    "VFX/RecordSystem/RecordTexture/BaseTextures/null_black_MSK4.tex"
)
_VANILLA_BODY_RTEX = "VFX/RecordSystem/RecordTexture/pl1000/pl1000_body.rtex"
_VANILLA_HEAD_RTEX = "VFX/RecordSystem/RecordTexture/pl1000/pl1000_head.rtex"
_FACE_RTEX_HINTS = (
    "pl1050", "pl1060", "pl1070", "pl1000_head", "_head", "/head", "face",
)


def presets_dir(game: str) -> Path:
    return Path(__file__).resolve().parent / "presets" / game


def load_preset(game: str, name: str) -> dict[str, Any]:
    path = presets_dir(game) / name
    if not path.is_file():
        raise FileNotFoundError(f"Missing {game} preset: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def mmtr_base(mmtr_path: str) -> str:
    """Lowercase file name of a master material path."""
    return os.path.basename((mmtr_path or "").replace("\\", "/")).lower()


def strip_port_suffix(base: str) -> str:
    """Record_Player_Cloth_RE3.mmtr → record_player_cloth.mmtr."""
    stem, dot, ext = base.rpartition(".")
    if not dot:
        return base
    for suffix in PORT_SUFFIXES:
        if stem.endswith(suffix) and len(stem) > len(suffix):
            return f"{stem[: -len(suffix)]}{dot}{ext}"
    return base


def preset_for_mmtr(base: str) -> str:
    """Closest stock preset for a shader the target game does not have."""
    for keyword, preset in PRESET_BY_KEYWORD:
        if keyword in base:
            return preset
    return FALLBACK_PRESET


def shipped_bases(shipped_mmtr) -> set[str]:
    """Mod-shipped mmtr file names, with the version suffix taken off."""
    out = set()
    for path in shipped_mmtr or ():
        base = mmtr_base(path)
        if ".mmtr." in base:
            base = base.split(".mmtr.")[0] + ".mmtr"
        out.add(base)
    return out


def resolve_shipped_shader(mat, base: str, shipped: set[str], game: str):
    """Pick how to move a material off a shader the mod brought with it.

    Returns ``("rename", alias)`` when the game ships a shader of the same
    name that the material already fits, otherwise ``("rebuild", preset)``.

    Dropping a ``_RE3`` suffix usually names a shader RE2 has, but not
    always a compatible one: a mod can override the stock shader with its own
    wider version, and RE3's Record_Player_Hair takes 78 parameters where
    RE2's takes 29. So the alias only wins if the game really owns that name
    and the material's parameter count matches the preset for it.
    """
    alias = strip_port_suffix(base)
    usable = (
        alias != base
        and alias in STOCK_RE2_MMTR
        and alias not in shipped
    )
    if usable:
        preset_name = PRESET_BY_MMTR.get(alias)
        if preset_name is None:
            return "rename", alias
        preset = load_preset(game, preset_name)
        if len(mat.propertyList) == len(preset["Property List"]):
            return "rename", alias
        return "rebuild", preset_name
    return "rebuild", preset_for_mmtr(alias)


def sane_prop_name(name: str) -> bool:
    """True when a property name looks like a real shader parameter."""
    if not name:
        return False
    return all(ch.isalnum() or ch in "._" for ch in name)


def layout_kind(mat, preset) -> str:
    """How a material's parameters sit against a stock preset.

    ``stock`` — every name is one the preset knows (arity may still differ).
    ``custom`` — extra real parameters, a layout we should not guess at.
    ``corrupt`` — empty/garbage names, or the same arity as the preset with
    the wrong names. Sportsuit's leftover ``pl1000_Body_Mat`` is this: 34
    slots, but the string table is truncated from ``IndirectLight_...`` on,
    so the RT game cannot load the MDF at all.
    """
    expected = [p["Property Name"] for p in preset["Property List"]]
    have = [p.propName for p in mat.propertyList]
    if any(not sane_prop_name(n) for n in have):
        return "corrupt"
    unknown = [n for n in have if n not in set(expected)]
    if not unknown:
        return "stock"
    if len(have) == len(expected):
        return "corrupt"
    return "custom"


_LIFT_PAK_ROOTS = RE2_PAK_ROOTS - {"sectionroot", "streaming"}


def nest_under_sectionroot(path: str) -> str:
    """Put an RE3/custom root where RE2 RT actually mounts it.

    ``Escape/Character/foo.tex`` becomes ``SectionRoot/Character/foo.tex``.
    ``Escape/VFX/foo.tex`` becomes ``VFX/foo.tex`` — VFX is a pak root
    (Nell and vanilla keep record textures there). ``Escape/SetModel``
    becomes ``ObjectRoot/SetModel`` — both dumps keep setmodel there, not
    under SectionRoot. Inverse is a no-op: classic Fluffy already loads
    VFX/, ObjectRoot/, and flattened SectionRoot.
    """
    raw = path or ""
    if not raw:
        return raw
    slash = "\\" if "\\" in raw and "/" not in raw else "/"
    parts = raw.replace("\\", "/").split("/")
    at = 0
    if len(parts) >= 2 and parts[0].lower() == "natives":
        at = 2
    if at >= len(parts) or not parts[at]:
        return raw
    first = parts[at].lower()
    second = parts[at + 1].lower() if at + 1 < len(parts) else ""
    if first == "sectionroot" and second:
        if second in _LIFT_PAK_ROOTS:
            del parts[at]
            return slash.join(parts)
        if second == "setmodel":
            parts[at] = "ObjectRoot"
            return slash.join(parts)
        if second in {"escape", "details"}:
            del parts[at + 1]
            return slash.join(parts)
        return raw
    if first not in RE2_PAK_ROOTS:
        if second in _LIFT_PAK_ROOTS:
            del parts[at]
            return slash.join(parts)
        if second == "setmodel":
            parts[at] = "ObjectRoot"
            return slash.join(parts)
        parts[at] = "SectionRoot"
        return slash.join(parts)
    return raw


def retarget_unmounted_player_path(path: str, dest_prefix: str) -> str:
    """Move a texture that lives under a non-player folder onto the costume.

    ``SectionRoot/Character/Player/wap100/Pl2020/Mesh/foo.tex`` becomes
    ``SectionRoot/Character/Player/pl1000/pl1004/foo.tex``. Vanilla RT
    player children are ``pl`` plus four digits, and the character tree
    has no ``mesh`` texture folder. ``pl2000`` matches that shape and
    stays put. Inverse is a no-op: classicize does not move it back, and
    classic already loads files under the costume folder.
    """
    if not dest_prefix or not path:
        return path
    slash = "\\" if "\\" in path and "/" not in path else "/"
    parts = path.replace("\\", "/").split("/")
    for i, part in enumerate(parts):
        if part.lower() != "player" or i + 1 >= len(parts):
            continue
        if RE2_PLAYER_ID.match(parts[i + 1]):
            return path
        dest = dest_prefix.replace("\\", "/").rstrip("/")
        return dest.replace("/", slash) + slash + parts[-1]
    return path


def retarget_re3_player_path(path: str, dest_prefix: str) -> str:
    """Park Jill/RE3 player textures next to the RE2 costume mesh.

    ``SectionRoot/Character/Player/Pl2000/Mesh/foo.tex`` becomes
    ``SectionRoot/Character/Player/pl1000/pl1004/foo.tex``. Both RE2 dumps
    already have a ``pl2000`` player tree (a different character than RE3
    Jill). Parking the RE3 files next to the Claire costume avoids overlaying
    that vanilla tree. Inverse is a no-op.
    """
    if not dest_prefix or not path:
        return path
    slash = "\\" if "\\" in path and "/" not in path else "/"
    parts = path.replace("\\", "/").split("/")
    for i, part in enumerate(parts):
        if part.lower() != "player" or i + 1 >= len(parts):
            continue
        if not _RE3_PLAYER_ID.match(parts[i + 1]):
            continue
        # player/pl2000/mesh/foo.tex and player/pl2000/pl2005/mesh/foo.tex.
        # The folder that owns "mesh" is the one that moves. pl2050/mesh
        # is a face and stays where the files are.
        mesh_at = next(
            (
                j for j in range(i + 2, len(parts) - 1)
                if parts[j].lower() == "mesh"
            ),
            None,
        )
        if mesh_at is None:
            continue
        owner = parts[mesh_at - 1].lower()
        if owner in _FACE_MESH_IDS:
            continue
        if owner != parts[i + 1].lower() and not _RE3_PLAYER_ID.match(owner):
            continue
        dest = dest_prefix.replace("\\", "/").rstrip("/")
        return dest.replace("/", slash) + slash + parts[-1]
    return path


def _looks_like_face_slot(path: str) -> bool:
    lower = (path or "").replace("\\", "/").lower()
    return any(hint in lower for hint in _FACE_RTEX_HINTS)


def replace_rtex_for_rt(texture_type: str, path: str) -> str:
    """Aim Rec_RTT at vanilla Claire record textures; null the rest.

    Vanilla RT Claire MDFs bind Rec_RTT to ``pl1000_body.rtex`` (body) or
    ``pl1000_head.rtex`` (face). The Mesh Editor RE2RT preset uses a tex
    null; the dump wins. Inverse is a no-op for those VFX paths: classicize
    already keeps game RecordSystem rtex. Other classic ``.rtex.4`` stubs
    (PressureMap, Rec_FIX, RE3 copies) still go to tex nulls.
    """
    t = texture_type or ""
    if t == "Rec_RTT":
        return (
            _VANILLA_HEAD_RTEX
            if _looks_like_face_slot(path)
            else _VANILLA_BODY_RTEX
        )
    if ".rtex" not in (path or "").lower():
        return path
    if t in ("PressureMap", "IntensityMap"):
        return _NULL_WHITE
    if t.startswith("Rec_") or t == "BloodMask":
        return _NULL_BLACK_MSK4
    return _NULL_BLACK


def align_properties_to_preset(mat, classic_preset, rt_preset, file_re_mdf) -> int:
    """Rebuild the property list in the RT shader's order and arity.

    Some shaders declare extra parameters in the RT build — Record_Player
    gains three, two of them at the end and one in the middle — so appending
    is not enough. Existing values are kept; the rest take preset defaults.

    Returns the number of parameters added, or -1 when the material carries a
    parameter the classic preset does not know. That means it is not a stock
    layout, so it is left untouched rather than reshaped on a guess.
    """
    classic_names = {p["Property Name"] for p in classic_preset["Property List"]}
    have = {p.propName: p for p in mat.propertyList}
    if any(name not in classic_names for name in have):
        return -1

    Property = file_re_mdf.Property
    rebuilt = []
    added = 0
    for pdata in rt_preset["Property List"]:
        name = pdata["Property Name"]
        defaults = prop_value_list(pdata.get("Value"))
        prop = Property()
        prop.propName = name
        existing = have.get(name)
        if existing is not None and len(list(existing.propValue)) == len(defaults):
            prop.propValue = [float(x) for x in existing.propValue]
        else:
            prop.propValue = defaults
            added += 1
        prop.padding = int(pdata.get("Padding") or 0)
        prop.frontPadding = 0
        prop.paramCount = len(prop.propValue)
        rebuilt.append(prop)
    mat.propertyList = rebuilt
    return added


def prop_value_list(raw: Any) -> list[float]:
    if isinstance(raw, list):
        return [float(x) for x in raw]
    if isinstance(raw, (int, float)):
        return [float(raw)]
    return [0.0]


def rebuild_from_preset(
    mat,
    preset: dict[str, Any],
    file_re_mdf,
    sanitize: Callable[[str, str], str],
) -> Any:
    """Re-lay a material onto the preset's slots, keeping matching values.

    ``sanitize`` receives (texture type, path) and returns the path to store.
    """
    Material = file_re_mdf.Material
    TextureBinding = file_re_mdf.TextureBinding
    Property = file_re_mdf.Property

    header = preset["Material Header"]
    flags = preset["Flags"]
    src_tex = {t.textureType: t.texturePath for t in mat.textureList}
    src_prop = {p.propName: list(p.propValue) for p in mat.propertyList}

    new_mat = Material()
    new_mat.materialName = mat.materialName
    new_mat.mmtrPath = header["Master Material Path"]
    new_mat.shaderType = int(header.get("Material Shader Type") or 0)
    new_mat.hideInGame = mat.hideInGame
    new_mat.flags.asInt32 = int(flags.get("FlagBitFlag") or 0)
    new_mat.flagsB.asInt32 = int(flags.get("FlagBitFlagB") or 0)
    new_mat.shaderLODNum = int(flags.get("ShaderLODNum") or 0)
    new_mat.bakeTextureArraySize = int(flags.get("BakeTextureArraySize") or 0)

    for pdata in preset.get("Property List") or []:
        prop = Property()
        name = pdata["Property Name"]
        prop.propName = name
        preset_vals = prop_value_list(pdata.get("Value"))
        if name in src_prop and len(src_prop[name]) == len(preset_vals):
            prop.propValue = [float(x) for x in src_prop[name]]
        else:
            prop.propValue = preset_vals
        prop.padding = int(pdata.get("Padding") or 0)
        prop.frontPadding = 0
        prop.paramCount = len(prop.propValue)
        new_mat.propertyList.append(prop)

    for tdata in preset.get("Texture Bindings") or []:
        tex = TextureBinding()
        ttype = tdata["Texture Type"]
        tex.textureType = ttype
        if ttype in src_tex and src_tex[ttype]:
            tex.texturePath = sanitize(ttype, src_tex[ttype])
        else:
            tex.texturePath = sanitize(ttype, tdata.get("Texture Path") or "")
        new_mat.textureList.append(tex)
    return new_mat
