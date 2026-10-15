"""Point ray tracing at a Claire costume's own face and hair.

RTX reads ``pl1000_*_costume_*.pfb.17`` from the game pak and ignores the
classic ``.pfb.16``. A custom hair mesh is copied onto the file that pak
prefab already names (``pl1075`` for Noir, ``pl1071`` for Military,
``pl1070`` otherwise).

The face is not copied onto ``pl1050.mesh``. That one file is the head
for every Claire outfit except '98, and the neck is part of it. Replacing
it hides the neck on the other outfits. When the mod has its own face
mesh, a ``.pfb.17`` is written beside the classic prefab so only that
costume loads the private mesh. The prefab is built from the shared-head
template (costume 8 / default): those paths are the same length as a
private ``pl18xx`` mesh, so the file's offset table stays valid.

Texture-only hair has no mesh. The ``.pfb.17`` keeps the pak mesh and
``pl1070.chain`` (a missing chain freezes outfit changes) and points the
material file at the private folder. Material names in that file are
aligned to the pak mesh so the hair is not invisible.
"""

from __future__ import annotations

import re
import shutil
import struct
from pathlib import Path

from ..hair_prefabs import align_hair_mdf_materials
from ..material_hash import material_name_hash
from ..paths import assets_dir

# Costume letter -> mesh path under pl1000, then the mdf path.
# Taken from the RTX unpack's pl1000_face_costume_*.pfb.17 / hair prefabs.
# Letters that are not listed use the Elza / default pair.
_FACE_RT = {
    "1": ("pl1050/pl1050", "pl1050/pl1050_01/pl1050_01"),
    "2": ("pl1050/pl1050", "pl1050/pl1050_02/pl1050_02"),
    "3": ("pl1050/pl1050", "pl1050/pl1050_02/pl1050_02"),
    "4": ("pl1050/pl1050", "pl1050/pl1050_03/pl1050_03"),
    "b": ("pl1050/pl1050", "pl1050/pl1050_04/pl1050_04"),
    "d": ("pl1057/pl1057", "pl1057/pl1057"),
}
_FACE_RT_DEFAULT = ("pl1050/pl1050", "pl1050/pl1050")
_HAIR_RT = {
    "a": "pl1075/pl1075",
    "b": "pl1071/pl1071",
}
_HAIR_RT_DEFAULT = "pl1070/pl1070"
# Every Claire costume except '98 draws this mesh. The neck is on it.
_SHARED_FACE = "pl1050/pl1050"
_FACE_MESH = "pl1050/pl1050.mesh"
_FACE_MDF = "pl1050/pl1050.mdf2"
_FACE_BLEND = "pl1050/pl1050_Blend.mesh"
_FACE_MAT = "pl1050_Face_Mat"
_FACE_MAT_RE = re.compile(r"pl[0-9A-Za-z]{4}_Face_Mat")
_TEMPLATE_DIR = "rt_prefab"


def mount_claire_costume_parts(
    staging: Path,
    report,
    face_slot: str | None = None,
    hair: bool = True,
) -> None:
    natives = staging / "natives"
    if not natives.is_dir():
        return
    saw_face = False
    saw_hair = False
    for prefab in natives.rglob("pl1000_*.pfb.*"):
        kind, slot = _prefab_kind(prefab.name)
        if kind is None or slot is None:
            continue
        # A .17 we just wrote is handled with its .16. One that still names
        # pl1050/pl1050.mesh is the pak head, so it is rewritten onto the
        # private mesh. Other .17 files are left as the mod shipped them.
        if prefab.name.lower().endswith(".pfb.17"):
            if kind != "face" or not _names_shared_face_mesh(prefab.read_bytes()):
                continue
        player = _player_dir(prefab)
        if player is None:
            continue
        strings = _utf16_strings(prefab.read_bytes())
        if kind == "face":
            saw_face = True
            mesh_rel, mdf_rel = _FACE_RT.get(slot, _FACE_RT_DEFAULT)
            _copy_part(
                staging, player, strings, mesh_rel, mdf_rel, report,
                prefab, kind, slot,
            )
        elif hair:
            saw_hair = True
            mesh_rel = _HAIR_RT.get(slot, _HAIR_RT_DEFAULT)
            _copy_part(
                staging, player, strings, mesh_rel, mesh_rel, report,
                prefab, kind, slot,
            )
    # Addons replace the classic mesh and omit the prefab, so the loop
    # above never sees them. Elza is the default slot.
    for player in _claire_player_dirs(natives):
        _drop_all_suits_face(player, report)
        if face_slot and not saw_face:
            _write_loose_face_prefab(staging, player, face_slot, report)
        if not saw_face:
            _leave_shared_face(
                player, "pl1050/pl1060.mesh", report, "loose face",
            )
        if hair and not saw_hair:
            _mount_loose(player, "pl1605/pl1678.mesh", "pl1070/pl1070", report)
            _mount_loose_chain(player, "pl1605.chain", "pl1070", report)


def _names_shared_face_mesh(data: bytes) -> bool:
    """True when a prefab still loads the head every Claire outfit uses."""
    for text in _utf16_strings(data):
        low = text.replace("\\", "/").lower()
        if low.endswith("pl1050/pl1050.mesh"):
            return True
    return False


def _prefab_kind(name: str) -> tuple[str | None, str | None]:
    low = name.lower()
    stem = low.split(".", 1)[0]
    if stem == "pl1000_face_default":
        return "face", "default"
    if stem == "pl1000_hair_default":
        return "hair", "default"
    if not stem.startswith("pl1000_") or "_costume_" not in stem:
        return None, None
    if stem.startswith("pl1000_face_costume_"):
        kind = "face"
    elif stem.startswith("pl1000_hair_costume_"):
        kind = "hair"
    else:
        return None, None
    slot = stem.split("_costume_", 1)[1]
    if len(slot) != 1:
        return None, None
    return kind, slot


def _player_dir(prefab: Path) -> Path | None:
    """Mesh folder, not the prefab's own pl1000 directory.

    Costume prefabs live under objectroot/.../parts/pl1000. The meshes
    they name live under sectionroot/character/player/pl1000.
    """
    plat = None
    for parent in prefab.parents:
        if parent.name.lower() in {"stm", "x64"} and parent.parent.name.lower() == "natives":
            plat = parent
            break
    if plat is None:
        return None
    section = _child(plat, "sectionroot")
    character = _child(section, "character") if section else None
    player = _child(character, "player") if character else None
    return _child(player, "pl1000") if player else None


def _child(folder: Path | None, name: str) -> Path | None:
    if folder is None or not folder.is_dir():
        return None
    for entry in folder.iterdir():
        if entry.name.lower() == name:
            return entry
    return None


def _claire_player_dirs(natives: Path) -> list[Path]:
    found: list[Path] = []
    if not natives.is_dir():
        return found
    for plat in natives.iterdir():
        if plat.name.lower() not in {"stm", "x64"}:
            continue
        section = _child(plat, "sectionroot")
        character = _child(section, "character") if section else None
        player = _child(character, "player") if character else None
        claire = _child(player, "pl1000") if player else None
        if claire is not None:
            found.append(claire)
    return found


_SHARED_FACE_ID = "pl1050"
# Loose copies of these filenames replace the pak face on every costume.
# alb is checked after albm so the longer role wins.
_SHARED_FACE_TEX_ROLES = ("albm", "nrmr", "atos", "alb")
_FACE_TEX_NAME = re.compile(
    r"^pl1050_(face_(?:albm|nrmr|atos|alb))(\.tex.*)$",
    re.IGNORECASE,
)


def _private_face_id(folder: Path) -> str | None:
    """Stem of a face mesh in this folder that is not the shared head."""
    stems: list[str] = []
    for path in folder.iterdir():
        if not path.is_file():
            continue
        low = path.name.lower()
        if ".mesh." not in low or "blend" in low:
            continue
        stem = path.name.split(".", 1)[0]
        if not re.fullmatch(r"pl[0-9]{4}", stem, re.IGNORECASE):
            continue
        if stem.lower() == _SHARED_FACE_ID:
            continue
        stems.append(stem)
    if not stems:
        return None
    for stem in stems:
        if stem.lower() == "pl1060":
            return stem
    return stems[0]


def _shared_face_mesh(folder: Path) -> Path | None:
    for path in folder.iterdir():
        if not path.is_file():
            continue
        low = path.name.lower()
        stem = path.name.split(".", 1)[0].lower()
        if stem == _SHARED_FACE_ID and ".mesh." in low and "blend" not in low:
            return path
    return None


def _drop_all_suits_face(player: Path, report) -> None:
    """Keep a shipped face off the pak head every other costume uses.

    A loose ``pl1050.mesh`` or ``pl1050_face_*`` replaces the neck on Jacket,
    Tank, Military, Noir, and both Classics. The destination costume loads
    the private file through its ray-tracing prefab.
    """
    folder = _child(player, _SHARED_FACE_ID)
    if folder is None:
        return
    shared = _shared_face_mesh(folder)
    if shared is not None:
        _privatize_shared_head(shared, report)
        return
    priv = _private_face_id(folder)
    if priv is None or len(priv) != len(_SHARED_FACE_ID):
        return
    roles = _retarget_shared_face_textures(folder, priv, report)
    if roles:
        _patch_shared_face_texture_ids(folder, priv, roles)


def _privatize_shared_head(
    mesh_src: Path, report,
) -> tuple[Path, Path | None] | None:
    """Move ``pl1050.mesh`` onto a private stem in the same folder.

    A second mesh such as ``pl1060`` is the costume face. The shared file
    is the all-suits copy and is removed. Otherwise the shared mesh, its
    material file, and its blend take the ``pl1060`` name so path lengths
    stay valid.
    """
    folder = mesh_src.parent
    if not folder.is_dir():
        return None
    existing = _private_face_id(folder)
    priv = existing or "pl1060"
    if len(priv) != len(_SHARED_FACE_ID) or priv.lower() == _SHARED_FACE_ID:
        return None
    if existing:
        mesh_src.unlink()
        report.warnings.append(
            f"Removed shared {mesh_src.name} so other outfits keep their "
            f"head. This costume still loads {folder.name}/{priv}."
        )
        private_mesh = _mesh_named(folder, priv)
        if private_mesh is None:
            return None
        roles = _retarget_shared_face_textures(folder, priv, report)
        _move_shared_blend(folder, priv)
        if roles:
            _patch_shared_face_texture_ids(folder, priv, roles)
        return private_mesh, _sibling(private_mesh, "mdf2")
    renamed = _rename_stem(mesh_src, priv)
    mdf = _file_named(folder, _SHARED_FACE_ID, "mdf2")
    if mdf is not None:
        mdf = _rename_stem(mdf, priv)
    else:
        mdf = _sibling(renamed, "mdf2")
    _move_shared_blend(folder, priv)
    roles = _retarget_shared_face_textures(folder, priv, report)
    if roles:
        _patch_shared_face_texture_ids(folder, priv, roles)
    report.warnings.append(
        f"Moved shared {_SHARED_FACE_ID}.mesh to {folder.name}/{priv} "
        "so other outfits keep their head and neck."
    )
    return renamed, mdf


def _mesh_named(folder: Path, stem: str) -> Path | None:
    return _file_named(folder, stem, "mesh")


def _file_named(folder: Path, stem: str, kind: str) -> Path | None:
    prefix = f"{stem.lower()}.{kind}."
    for path in folder.iterdir():
        if path.is_file() and path.name.lower().startswith(prefix):
            if kind == "mesh" and "blend" in path.name.lower():
                continue
            return path
    return None


def _rename_stem(path: Path, new_stem: str) -> Path:
    old_stem = path.name.split(".", 1)[0]
    dest = path.with_name(new_stem + path.name[len(old_stem):])
    if dest.exists():
        return dest
    path.rename(dest)
    return dest


def _move_shared_blend(folder: Path, priv: str) -> None:
    for path in list(folder.iterdir()):
        if not path.is_file():
            continue
        stem = path.name.split(".", 1)[0]
        if stem.lower() != f"{_SHARED_FACE_ID}_blend":
            continue
        dest = path.with_name(priv + path.name[len(_SHARED_FACE_ID):])
        if dest.exists():
            path.unlink()
            continue
        path.rename(dest)


def _retarget_shared_face_textures(
    folder: Path, priv: str, report,
) -> set[str]:
    roles: set[str] = set()
    for path in list(folder.iterdir()):
        if not path.is_file():
            continue
        match = _FACE_TEX_NAME.match(path.name)
        if match is None:
            continue
        role = match.group(1).split("_", 1)[1].lower()
        dest = path.with_name(priv + path.name[len(_SHARED_FACE_ID):])
        if dest.exists():
            path.unlink()
            report.warnings.append(
                f"Removed shared {path.name}; {dest.name} already "
                "covers this costume."
            )
        else:
            path.rename(dest)
            report.warnings.append(
                f"Moved {path.name} to {dest.name} so other outfits "
                "keep the vanilla neck."
            )
        roles.add(role)
    return roles


def _patch_shared_face_texture_ids(
    folder: Path, priv: str, roles: set[str],
) -> None:
    old_prefix = (_SHARED_FACE_ID + "_").encode("utf-16-le")
    new_prefix = (priv + "_").encode("utf-16-le")
    if len(old_prefix) != len(new_prefix):
        return
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        low = path.name.lower()
        if ".mdf2" not in low and ".mesh." not in low and ".pfb." not in low:
            continue
        data = path.read_bytes()
        patched = _swap_face_tex_prefix(data, old_prefix, new_prefix, roles)
        if patched != data:
            path.write_bytes(patched)


def _swap_face_tex_prefix(
    data: bytes,
    old_prefix: bytes,
    new_prefix: bytes,
    roles: set[str],
) -> bytes:
    out = bytearray()
    width = len(old_prefix)
    index = 0
    while index < len(data):
        if data[index:index + width] != old_prefix:
            out.append(data[index])
            index += 1
            continue
        token = _utf16_token(data, index + width)
        role = _face_tex_role(token)
        if role not in roles:
            out.append(data[index])
            index += 1
            continue
        out += new_prefix
        index += width
    return bytes(out)


def _utf16_token(data: bytes, start: int) -> str:
    chars: list[str] = []
    index = start
    while index + 1 < len(data) and data[index + 1] == 0:
        code = data[index]
        if not (code == ord("_") or 48 <= code <= 57 or 65 <= code <= 90
                or 97 <= code <= 122):
            break
        chars.append(chr(code))
        index += 2
    return "".join(chars)


def _face_tex_role(token: str) -> str | None:
    low = token.lower()
    if not low.startswith("face_"):
        return None
    rest = low[len("face_"):]
    for role in _SHARED_FACE_TEX_ROLES:
        if rest == role or rest.startswith(role) and (
            len(rest) == len(role) or not rest[len(role)].isalpha()
        ):
            return role
    return None


def _leave_shared_face(player: Path, src_rel: str, report, label: str) -> None:
    """Keep the pak's pl1050 head. A custom face must not replace it."""
    src = _find_versioned(player, src_rel)
    if src is None or not _clobbers_shared_face(_SHARED_FACE, src):
        return
    stem = src.name.split(".", 1)[0]
    report.warnings.append(
        f"{label}: left shared pl1050.mesh alone so Military, Jacket, "
        f"Tank Top, and both Classics keep their head and neck. "
        f"The custom face stays on {src.parent.name}/{stem}."
    )


def _clobbers_shared_face(mesh_rel: str, src: Path) -> bool:
    """True when copying ``src`` would replace the head every Claire outfit uses.

    ``pl1059/pl1050.mesh`` is a private head that reuses the shared file
    name. Only the file that already lives in the ``pl1050`` folder is
    the shared head.
    """
    if mesh_rel.lower() != _SHARED_FACE:
        return False
    stem = src.name.split(".", 1)[0].lower()
    return not (src.parent.name.lower() == "pl1050" and stem == "pl1050")


def _authored_chain_id(strings: list[str]) -> str | None:
    rel = _authored_player_rel(strings, ".chain")
    if not rel:
        return None
    name = rel.replace("\\", "/").rsplit("/", 1)[-1]
    if not name.lower().endswith(".chain"):
        return None
    return name[:-len(".chain")]


def _hair_needs_its_own_chain(
    strings: list[str],
    mesh_rel: str,
    player: Path,
) -> bool:
    chain_id = _authored_chain_id(strings)
    pak_id = mesh_rel.split("/", 1)[0]
    if not chain_id or chain_id.lower() == pak_id.lower():
        return False
    return _referenced_file(player, strings, ".chain") is None


def _blend_rel(mesh_src: Path) -> str | None:
    folder = mesh_src.parent
    if not folder.is_dir():
        return None
    hits = [
        path for path in folder.iterdir()
        if path.is_file()
        and ".mesh." in path.name.lower()
        and "blend" in path.name.lower()
    ]
    if not hits:
        return None
    stem = hits[0].name.split(".", 1)[0]
    return f"{folder.name}/{stem}.mesh"


def _mount_loose(player: Path, src_rel: str, dest_rel: str, report) -> None:
    src = _find_versioned(player, src_rel)
    if src is None:
        return
    copied = _copy_if_different(src, _dest_file(player, dest_rel, src))
    mdf_src = _sibling(src, "mdf2")
    if mdf_src is not None:
        copied = _copy_if_different(
            mdf_src, _dest_file(player, dest_rel, mdf_src),
        ) or copied
    if copied:
        report.warnings.append(
            f"RTX loads {dest_rel}.mesh, so {src.name} was copied there"
        )


def _mount_loose_chain(player: Path, src_stem: str, dest_stem: str, report) -> None:
    if not player.is_dir():
        return
    prefix = src_stem.lower() + "."
    hits = [
        p for p in player.iterdir()
        if p.is_file() and p.name.lower().startswith(prefix)
    ]
    if not hits:
        return
    src = hits[0]
    if _copy_if_different(src, _dest_file(player, dest_stem, src)):
        report.warnings.append(
            f"RTX loads {dest_stem}.chain, so {src.name} was copied there"
        )


def _copy_part(
    staging: Path,
    player: Path,
    strings: list[str],
    mesh_rel: str,
    mdf_rel: str,
    report,
    prefab: Path,
    kind: str,
    slot: str,
) -> None:
    prefab_name = prefab.name
    mesh_src = _referenced_file(player, strings, ".mesh")
    if mesh_src is None:
        if kind == "hair":
            _write_texture_hair_prefab(
                staging, player, strings, prefab, slot, report,
            )
        return
    # A short style stored on another player (pl2000/pl207H) is the hair
    # this costume asked for. Copying it onto pl1070 would replace Claire's
    # ponytail for every outfit. Point this costume's prefab at it instead.
    if kind == "hair" and not _is_under(mesh_src, player):
        _write_external_hair_prefab(
            prefab, slot, mesh_src, strings, player, report,
        )
        return
    # Military and Noir load a different chain than the ponytail. Copying
    # the mesh onto that slot and leaving the pak chain freezes the outfit
    # change. A chain file in the mod can move with the mesh; a pak chain
    # cannot, so the prefab keeps the chain the mesh was built for.
    if kind == "hair" and _hair_needs_its_own_chain(strings, mesh_rel, player):
        _write_external_hair_prefab(
            prefab, slot, mesh_src, strings, player, report,
        )
        return
    if kind == "face" and mesh_rel.lower() == _SHARED_FACE:
        mdf_src = _sibling(mesh_src, "mdf2")
        if not _clobbers_shared_face(mesh_rel, mesh_src):
            relocated = _privatize_shared_head(mesh_src, report)
            if relocated is None:
                return
            mesh_src, mdf_src = relocated
        stem = mesh_src.name.split(".", 1)[0]
        wrote = _write_rt_face_prefab(
            prefab, slot, mesh_src, mdf_src, report,
        )
        if wrote:
            report.warnings.append(
                f"{prefab_name}: left shared pl1050.mesh alone and wrote "
                f"a ray tracing prefab for {mesh_src.parent.name}/{stem}."
            )
        else:
            report.warnings.append(
                f"{prefab_name}: left shared pl1050.mesh alone so Military, "
                f"Jacket, Tank Top, and both Classics keep their head and "
                f"neck. The custom face stays on "
                f"{mesh_src.parent.name}/{stem}."
            )
        return
    mesh_dest = _dest_file(player, mesh_rel, mesh_src)
    copied = _copy_if_different(mesh_src, mesh_dest)
    mdf_src = _sibling(mesh_src, "mdf2")
    mdf_dest = None
    if mdf_src is not None:
        mdf_dest = _dest_file(player, mdf_rel, mdf_src)
        copied = _copy_if_different(mdf_src, mdf_dest) or copied
    chain_src = _referenced_file(player, strings, ".chain")
    if chain_src is not None:
        chain_rel = mesh_rel.split("/", 1)[0]
        chain_dest = _dest_file(player, chain_rel, chain_src)
        copied = _copy_if_different(chain_src, chain_dest) or copied
    if copied:
        report.warnings.append(
            f"{prefab_name}: RTX loads {mesh_rel}.mesh, "
            f"so {mesh_src.name} was copied there"
        )


_PLAYER_REF_RE = re.compile(r"/player/(pl[0-9a-z]{4})/(.+)$", re.IGNORECASE)


def _referenced_file(player: Path, strings: list[str], suffix: str) -> Path | None:
    """Find a prefab path on this player or a sibling (pl2000, …)."""
    players = player.parent
    for text in strings:
        low = text.replace("\\", "/").lower()
        if not low.endswith(suffix) or "blend" in low:
            continue
        match = _PLAYER_REF_RE.search(low)
        if match is None:
            continue
        owner, rel = match.group(1).lower(), match.group(2)
        root = player if owner == player.name.lower() else _child(players, owner)
        if root is None:
            continue
        found = _find_versioned(root, rel)
        if found is not None:
            return found
    return None


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


_PAK_HAIR_MESH = "pl1000/pl1070/pl1070.mesh"
_PAK_HAIR_MDF = "pl1000/pl1070/pl1070.mdf2"
_PAK_HAIR_CHAIN = "pl1000/pl1070.chain"
_HAIR_MAT_SUFFIXES = ("_Hair_Mat", "_Hair2_Mat", "_Hair3_Mat")


def _authored_mat(strings: list[str], suffix: str) -> str | None:
    vanilla = f"pl1070{suffix}".lower()
    for text in strings:
        if text.lower().endswith(suffix.lower()) and text.lower().startswith("pl"):
            if text.lower() != vanilla:
                return text
    return None


def _authored_player_rel(strings: list[str], suffix: str) -> str | None:
    """``.../Player/pl2000/pl207H/pl2070.mesh`` → ``pl2000/pl207H/pl2070.mesh``.

    Case comes from the prefab. Windows folder listings lowercase ``pl207H``.
    """
    for text in strings:
        raw = text.replace("\\", "/")
        if "blend" in raw.lower() or not raw.lower().endswith(suffix):
            continue
        match = _PLAYER_REF_RE.search(raw)
        if match is None:
            continue
        return f"{match.group(1)}/{match.group(2)}"
    return None


def _write_external_hair_prefab(
    prefab: Path,
    slot: str,
    mesh_src: Path,
    strings: list[str],
    player: Path,
    report,
) -> None:
    """Point one costume at a hair mesh that does not live under pl1000."""
    mesh_rel = _authored_player_rel(strings, ".mesh")
    mdf_src = _sibling(mesh_src, "mdf2")
    mdf_rel = _authored_player_rel(strings, ".mdf2")
    if mdf_src is None:
        mdf_rel = None
    if not mesh_rel or not mdf_rel:
        report.warnings.append(
            f"{prefab.name}: could not read the short hair path; "
            "vanilla ponytail was left alone."
        )
        return
    if len(mesh_rel) != len(_PAK_HAIR_MESH) or len(mdf_rel) != len(_PAK_HAIR_MDF):
        report.warnings.append(
            f"{prefab.name}: hair path {mesh_rel} does not fit the ray "
            "tracing prefab; vanilla ponytail was left alone."
        )
        return
    data = _load_slot_template("hair", slot)
    if data is None:
        report.warnings.append(
            f"{prefab.name}: ray tracing hair template is missing; "
            "vanilla ponytail was left alone."
        )
        return
    data = _replace_utf16(data, _PAK_HAIR_MESH, mesh_rel)
    if data is None:
        return
    data = _replace_utf16(data, _PAK_HAIR_MDF, mdf_rel)
    if data is None:
        return
    chain_src = _referenced_file(player, strings, ".chain")
    if chain_src is not None:
        chain_rel = _authored_player_rel(strings, ".chain")
        if chain_rel and len(chain_rel) == len(_PAK_HAIR_CHAIN):
            patched = _replace_utf16(data, _PAK_HAIR_CHAIN, chain_rel)
            if patched is not None:
                data = patched
    for suffix in _HAIR_MAT_SUFFIXES:
        authored = _authored_mat(strings, suffix)
        vanilla = f"pl1070{suffix}"
        if authored and len(authored) == len(vanilla):
            patched = _replace_utf16(data, vanilla, authored)
            if patched is not None:
                data = patched
    if mdf_src is not None:
        _retarget_external_hair_textures(mdf_src, player, slot, report)
    dest = prefab.with_name(prefab.name.split(".", 1)[0] + ".pfb.17")
    dest.write_bytes(data)
    report.warnings.append(
        f"{prefab.name}: ray tracing loads {mesh_rel} "
        "and leaves shared pl1070.mesh alone."
    )


def _retarget_external_hair_textures(
    mdf_src: Path,
    player: Path,
    slot: str,
    report,
) -> None:
    """Point a short-hair material at the costume's texture-only recolor.

    SB Back to Raccoon City keeps the short mesh and ships the blonde
    color as ``pl1070_hair_alba`` with no mesh of its own. The short
    material still samples the brown ``pl2005`` map until that path is
    rewritten. Normals stay on the short mesh when the recolor folder
    did not ship them.
    """
    pak_id = _HAIR_RT.get(slot, _HAIR_RT_DEFAULT).split("/", 1)[0]
    folder = _child(player, pak_id)
    if folder is None or not folder.is_dir():
        return
    files = [path for path in folder.iterdir() if path.is_file()]
    if any(".mesh." in path.name.lower() for path in files):
        return
    recolors = [
        path for path in files
        if "hair" in path.name.lower() and _texture_role(path.name)
    ]
    if not recolors:
        return
    try:
        data = bytearray(mdf_src.read_bytes())
    except OSError:
        return
    changed: list[str] = []
    i = 0
    while i + 1 < len(data):
        slot_at = _aligned_wstring(data, i)
        if slot_at is None:
            i += 2
            continue
        text, char_end, end = slot_at
        low = text.lower().replace("\\", "/")
        role = _texture_role(text)
        if role and "player/" in low and "hair" in low and low.endswith(".tex"):
            picked = _pick_recolor(recolors, role)
            if picked is not None:
                parts = text.replace("\\", "/").split("/")
                if len(parts) >= 2:
                    old_tail = f"{parts[-2]}/{parts[-1]}"
                    new_name = picked.name.split(".", 1)[0] + ".tex"
                    new_tail = f"{pak_id}/{new_name}"
                    if old_tail.lower() != new_tail.lower():
                        if len(old_tail) != len(new_tail):
                            report.warnings.append(
                                f"{mdf_src.name}: hair texture {parts[-1]} "
                                f"does not fit {new_name}."
                            )
                        else:
                            prefix = text.replace("\\", "/")[:len(text) - len(old_tail)]
                            new_text = prefix + new_tail
                            data[i:char_end] = new_text.encode("utf-16le")
                            changed.append(new_name)
        i = end if end % 2 == 0 else end + 1
    if not changed:
        return
    mdf_src.write_bytes(bytes(data))
    listed = ", ".join(dict.fromkeys(changed))
    report.warnings.append(
        f"{mdf_src.name}: short hair uses {listed} from {pak_id}."
    )


def _texture_role(name: str) -> str | None:
    low = name.lower()
    for token in ("alba", "albm", "nrmr", "atos"):
        if token in low:
            return token
    return None


def _pick_recolor(files: list[Path], role: str) -> Path | None:
    for path in files:
        if _texture_role(path.name) == role:
            return path
    if role == "albm":
        for path in files:
            if _texture_role(path.name) == "alba":
                return path
    return None


def _aligned_wstring(data: bytes | bytearray, pos: int) -> tuple[str, int, int] | None:
    if pos % 2 or pos + 5 >= len(data):
        return None
    if data[pos + 1] != 0 or not (32 <= data[pos] < 127):
        return None
    chars: list[str] = []
    j = pos
    while j + 1 < len(data) and data[j + 1] == 0 and 32 <= data[j] < 127:
        chars.append(chr(data[j]))
        j += 2
    if len(chars) < 4 or j + 1 >= len(data) or data[j] != 0 or data[j + 1] != 0:
        return None
    return "".join(chars), j, j + 2


def _find_versioned(player: Path, rel: str) -> Path | None:
    """``pl1050/pl1060.mesh`` -> the versioned file on disk."""
    folder = player / Path(rel).parent
    stem = Path(rel).name  # pl1060.mesh
    if not folder.is_dir():
        return None
    prefix = stem.lower() + "."
    hits = [
        p for p in folder.iterdir()
        if p.is_file() and p.name.lower().startswith(prefix)
    ]
    return hits[0] if hits else None


def _sibling(mesh: Path, kind: str) -> Path | None:
    stem = mesh.name.split(".", 1)[0]
    hits = [
        p for p in mesh.parent.iterdir()
        if p.is_file() and p.name.lower().startswith(f"{stem.lower()}.{kind}.")
    ]
    return hits[0] if hits else None


def _dest_file(player: Path, rel: str, src: Path) -> Path:
    """Keep the source version suffix on the RTX stem."""
    suffix = src.name.split(".", 1)[1]
    return player / Path(rel).parent / f"{Path(rel).name}.{suffix}"


def _copy_if_different(src: Path, dest: Path) -> bool:
    if src.resolve() == dest.resolve():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.read_bytes() == src.read_bytes():
        return False
    shutil.copy2(src, dest)
    return True


def _utf16_strings(data: bytes) -> list[str]:
    out: list[str] = []
    i = 0
    while i + 1 < len(data):
        if data[i + 1] == 0 and 32 <= data[i] < 127:
            chars: list[str] = []
            j = i
            while j + 1 < len(data) and data[j + 1] == 0 and 32 <= data[j] < 127:
                chars.append(chr(data[j]))
                j += 2
            if len(chars) >= 4:
                out.append("".join(chars))
            i = j
        else:
            i += 1
    return out


def _replace_utf16(data: bytes, old: str, new: str) -> bytes | None:
    """Replace one UTF-16LE token. Lengths must match so offsets stay valid."""
    if len(old) != len(new):
        return None
    if old == new:
        return data
    needle = old.encode("utf-16le")
    if needle not in data:
        return None
    return data.replace(needle, new.encode("utf-16le"))


def _load_slot_template(kind: str, slot: str) -> bytes | None:
    folder = assets_dir() / _TEMPLATE_DIR
    if slot == "default":
        path = folder / f"pl1000_{kind}_default.pfb.17"
        if not path.is_file():
            return None
        return path.read_bytes()
    path = folder / f"pl1000_{kind}_costume_8.pfb.17"
    if not path.is_file():
        return None
    data = path.read_bytes()
    if slot == "8":
        return data
    return _replace_utf16(data, "costume_8", f"costume_{slot}")


def _face_mat_in(path: Path) -> str | None:
    data = path.read_bytes()
    for text in _utf16_strings(data):
        match = _FACE_MAT_RE.search(text)
        if match:
            return match.group(0)
    match = _FACE_MAT_RE.search(data.decode("ascii", errors="ignore"))
    return match.group(0) if match else None


def _write_rt_face_prefab(
    prefab: Path,
    slot: str,
    mesh_src: Path,
    mdf_src: Path | None,
    report,
) -> bool:
    """Write a .pfb.17 that loads the private face and leaves pl1050.mesh."""
    mesh_stem = mesh_src.name.split(".", 1)[0]
    want_mesh = f"{mesh_src.parent.name}/{mesh_stem}.mesh"
    if mdf_src is None:
        # Mesh-only heads still use the pak face material.
        want_mdf = _FACE_MDF
        mdf_mat = None
    else:
        mdf_stem = mdf_src.name.split(".", 1)[0]
        want_mdf = f"{mdf_src.parent.name}/{mdf_stem}.mdf2"
        mdf_mat = _face_mat_in(mdf_src)
    if len(want_mesh) != len(_FACE_MESH) or len(want_mdf) != len(_FACE_MDF):
        report.warnings.append(
            f"{prefab.name}: custom face path does not fit the ray tracing "
            "prefab; shared pl1050.mesh was left alone."
        )
        return False
    data = _load_slot_template("face", slot)
    if data is None:
        report.warnings.append(
            f"{prefab.name}: ray tracing face template is missing; "
            "shared pl1050.mesh was left alone."
        )
        return False
    data = _replace_utf16(data, _FACE_MESH, want_mesh)
    if data is None:
        return False
    data = _replace_utf16(data, _FACE_MDF, want_mdf)
    if data is None:
        return False
    blend_rel = _blend_rel(mesh_src)
    if blend_rel and blend_rel.lower() != _FACE_BLEND.lower():
        if len(blend_rel) != len(_FACE_BLEND):
            report.warnings.append(
                f"{prefab.name}: face blend {blend_rel} does not fit the "
                "ray tracing prefab; the vanilla blend was left in place."
            )
        else:
            patched = _replace_utf16(data, _FACE_BLEND, blend_rel)
            if patched is not None:
                data = patched
    mesh_mat = _face_mat_in(mesh_src)
    if mdf_src is not None:
        mdf_mat = _face_mat_in(mdf_src)
    if (
        mdf_src is not None
        and mesh_mat
        and mdf_mat
        and mesh_mat != mdf_mat
        and len(mesh_mat) == len(mdf_mat)
    ):
        patched = _replace_utf16(mdf_src.read_bytes(), mdf_mat, mesh_mat)
        if patched is not None:
            old_h = struct.pack("<I", material_name_hash(mdf_mat))
            new_h = struct.pack("<I", material_name_hash(mesh_mat))
            if old_h != new_h and old_h in patched:
                patched = patched.replace(old_h, new_h)
            mdf_src.write_bytes(patched)
        mdf_mat = mesh_mat
    mat = mesh_mat or mdf_mat
    if mat and mat != _FACE_MAT:
        if len(mat) != len(_FACE_MAT):
            report.warnings.append(
                f"{prefab.name}: face material {mat} does not fit the ray "
                "tracing prefab; shared pl1050.mesh was left alone."
            )
            return False
        swapped = _replace_utf16(data, _FACE_MAT, mat)
        if swapped is None:
            return False
        data = swapped
    dest = prefab.with_name(prefab.name.split(".", 1)[0] + ".pfb.17")
    dest.write_bytes(data)
    return True


def _write_loose_face_prefab(
    staging: Path,
    player: Path,
    slot: str,
    report,
) -> None:
    """Point the destination costume at a face that shipped no classic prefab.

    Addons replace ``pl1050.mesh`` and omit the prefab. After that mesh is
    moved private, only this slot's ``.pfb.17`` loads it.
    """
    folder = _child(player, _SHARED_FACE_ID)
    if folder is None:
        return
    priv = _private_face_id(folder)
    if priv is None:
        return
    mesh = _mesh_named(folder, priv)
    if mesh is None:
        return
    parts = _claire_parts_dir(staging)
    stem = (
        "pl1000_face_default" if slot == "default"
        else f"pl1000_face_costume_{slot}"
    )
    if (parts / f"{stem}.pfb.17").is_file():
        return
    prefab = parts / f"{stem}.pfb.16"
    wrote = _write_rt_face_prefab(
        prefab, slot, mesh, _sibling(mesh, "mdf2"), report,
    )
    if wrote:
        report.warnings.append(
            f"{stem}.pfb.17: destination costume loads "
            f"{folder.name}/{priv}."
        )


def _claire_parts_dir(staging: Path) -> Path:
    natives = staging / "natives"
    for plat_name in ("stm", "x64"):
        candidate = (
            natives / plat_name / "objectroot" / "prefab" / "character"
            / "survivor" / "parts" / "pl1000"
        )
        if candidate.is_dir():
            return candidate
    dest = (
        natives / "stm" / "objectroot" / "prefab" / "character"
        / "survivor" / "parts" / "pl1000"
    )
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def _write_texture_hair_prefab(
    staging: Path,
    player: Path,
    strings: list[str],
    prefab: Path,
    slot: str,
    report,
) -> None:
    """Bind a hair albedo to the pak mesh without naming a missing file.

    An addon overlay must not replace the main mod's hair prefab with the
    vanilla mesh. A full mod's texture-only hair (no .mesh in the folder)
    keeps ``pl1070.mesh`` / ``pl1070.chain`` from the pak and points the
    material file at the private folder.
    """
    if _staging_is_addon(staging):
        return
    mdf_src = _referenced_file(player, strings, ".mdf2")
    if mdf_src is None:
        return
    pak_id = _HAIR_RT.get(slot, _HAIR_RT_DEFAULT).split("/", 1)[0]
    mdf_stem = mdf_src.name.split(".", 1)[0]
    priv = mdf_src.parent.name
    want = f"{priv}/{mdf_stem}.mdf2"
    have = f"{pak_id}/{pak_id}.mdf2"
    if want.lower() == have.lower():
        return
    if len(want) != len(have):
        report.warnings.append(
            f"{prefab.name}: hair material path {want} does not fit the "
            "ray tracing prefab; vanilla hair was left alone."
        )
        return
    align_hair_mdf_materials(staging, priv, mdf_stem, pak_id)
    data = _load_slot_template("hair", slot)
    if data is None:
        report.warnings.append(
            f"{prefab.name}: ray tracing hair template is missing; "
            "vanilla hair was left alone."
        )
        return
    if pak_id.lower() != "pl1070":
        retargeted = _replace_utf16(data, "pl1070", pak_id)
        if retargeted is None:
            return
        data = retargeted
    patched = _replace_utf16(data, have, want)
    if patched is None:
        report.warnings.append(
            f"{prefab.name}: could not point the ray tracing hair prefab "
            f"at {want}; vanilla hair was left alone."
        )
        return
    dest = prefab.with_name(prefab.name.split(".", 1)[0] + ".pfb.17")
    dest.write_bytes(patched)
    report.warnings.append(
        f"{prefab.name}: ray tracing keeps {pak_id}.mesh and "
        f"{pak_id}.chain and loads {want}."
    )


def _staging_is_addon(staging: Path) -> bool:
    if not staging.is_dir():
        return False
    inis = [
        child for child in staging.iterdir()
        if child.is_file() and child.name.lower() == "modinfo.ini"
    ]
    if not inis:
        inis = [
            path for path in staging.rglob("*")
            if path.is_file() and path.name.lower() == "modinfo.ini"
        ]
    for path in inis:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            if not line.strip().lower().startswith("addonfor"):
                continue
            value = line.split("=", 1)[-1].strip().strip('"')
            return bool(value)
    return False
