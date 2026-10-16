"""Keep mesh material slots and MDF names paired after a Blender re-export.

RE Mesh Editor rebuilds the material table in first-seen viscon/submesh
order. Classic RE2 often still paints by slot index; RT binds by material
name + Murmur hash. A reshuffle or a leftover MDF name (Holster vs Body2)
makes clothing groups unload. Inverse is the same shuffle on RT → classic.

Renaming an MDF slot to the mesh name at that index is not undone on the
way back: the mesh is the truth, so classicize keeps the aligned names.
"""

from __future__ import annotations

import math
import os
import re
from itertools import combinations


def material_names(re_mesh) -> list[str]:
    return [re_mesh.rawNameList[i] for i in re_mesh.materialNameRemapList]


def _names_repeat(names: list[str]) -> bool:
    return len(names) != len(set(names))


def slot_remap(src_names: list[str], dest_names: list[str]) -> list[int] | None:
    """dest slot → src slot, or None if the name sets differ."""
    if _names_repeat(src_names) or _names_repeat(dest_names):
        return None
    if src_names == dest_names:
        return list(range(len(src_names)))
    if len(src_names) != len(dest_names) or set(src_names) != set(dest_names):
        return None
    index_in_src = {name: i for i, name in enumerate(src_names)}
    return [index_in_src[name] for name in dest_names]


def apply_slot_remap_to_indices(old_to_new: list[int], material_index: int) -> int:
    if material_index < 0 or material_index >= len(old_to_new):
        return material_index
    return old_to_new[material_index]


def _iter_subdivisions(re_mesh):
    headers = [re_mesh.lodHeader]
    if getattr(re_mesh, "shadowHeader", None) is not None:
        headers.append(re_mesh.shadowHeader)
    for header in headers:
        if header is None:
            continue
        for lod in getattr(header, "lodGroupList", []) or []:
            for group in getattr(lod, "meshGroupList", []) or []:
                for entry in getattr(group, "vertexInfoList", []) or []:
                    yield entry


def restore_mesh_material_order(src: str, dst: str, file_re_mesh) -> str | None:
    """Rewrite dest material remap + indices to match source slot order.

    Returns a short note when it changed the file, else None.
    """
    src_mesh = file_re_mesh.readREMesh(src)
    dst_mesh = file_re_mesh.readREMesh(dst)
    src_names = material_names(src_mesh)
    dest_names = material_names(dst_mesh)
    remap = slot_remap(src_names, dest_names)
    if remap is None:
        print(
            "RE2RTX_MESH: material set changed, left export order "
            f"src={src_names} dest={dest_names}"
        )
        return None
    if remap == list(range(len(remap))):
        return None

    name_to_raw = {}
    for raw_i in dst_mesh.materialNameRemapList:
        name_to_raw.setdefault(dst_mesh.rawNameList[raw_i], raw_i)
    dst_mesh.materialNameRemapList = [name_to_raw[name] for name in src_names]

    for entry in _iter_subdivisions(dst_mesh):
        entry.materialIndex = apply_slot_remap_to_indices(remap, entry.materialIndex)

    file_re_mesh.writeREMesh(dst_mesh, dst)
    return f"restored material order {dest_names} -> {src_names}"


def sibling_mesh_path(mdf_src: str, prefer_suffix: str | None = None) -> str | None:
    """``pl1004.mdf2.10`` → ``pl1004.mesh.*`` in the same folder, if any.

    When both the classic mesh and the RT mesh are on disk, pass the suffix
    the game will load. The export can drop empty slots, and aligning to the
    other mesh leaves the material file longer than the one that draws.
    """
    folder = os.path.dirname(mdf_src)
    stem = os.path.basename(mdf_src).split(".mdf2")[0].lower()
    if not stem or not os.path.isdir(folder):
        return None
    hits = [
        os.path.join(folder, name)
        for name in os.listdir(folder)
        if name.lower().startswith(stem + ".mesh.")
    ]
    if not hits:
        return None
    main = [h for h in hits if "_blend.mesh" not in os.path.basename(h).lower()]
    pool = main or hits
    if prefer_suffix:
        preferred = [
            h for h in pool if os.path.basename(h).lower().endswith(prefer_suffix.lower())
        ]
        if preferred:
            return preferred[0]
    return pool[0]


def mesh_path_for_mdf(mdf_src: str, prefer_suffix: str | None = None) -> str | None:
    """Mesh this material file draws with.

    A sibling ``pl1001.mdf2`` sits next to ``pl1001.mesh``. An alternate
    such as ``pl1001_01.mdf2`` lives in a child folder and still draws
    the parent body mesh.
    """
    hit = sibling_mesh_path(mdf_src, prefer_suffix)
    if hit:
        return hit
    folder = os.path.dirname(mdf_src)
    parent = os.path.dirname(folder)
    stem = os.path.basename(parent)
    if not stem or not os.path.isdir(parent):
        return None
    return sibling_mesh_path(os.path.join(parent, stem + ".mdf2"), prefer_suffix)


def _mesh_name_is_cut(mesh_name: str, mdf_name: str) -> bool:
    """True when the mesh export cut a long material name.

    Vaccine slots leave the mesh with ``...Env_Alph`` and the MDF with
    ``...Env_Alpha``. That material still belongs to the slot.
    """
    return (
        len(mesh_name) >= 8
        and mesh_name != mdf_name
        and mdf_name.startswith(mesh_name)
    )


def _drop_materials_the_mesh_does_not_name(mdf, mesh_names: list[str]) -> list[str]:
    """Drop surplus materials so the MDF is not longer than the mesh.

    A longer material file checkerboards every slot on that mesh. The head
    is a different file, so it stays. Names the mesh does not use go first,
    then extra copies of a name. A cut vaccine name is kept unless the list
    is still longer. Never adds a material.
    """
    mats = list(getattr(mdf, "materialList", []) or [])
    extra = len(mats) - len(mesh_names)
    if extra <= 0 or not mesh_names:
        return []
    mesh_counts: dict[str, int] = {}
    for name in mesh_names:
        mesh_counts[name] = mesh_counts.get(name, 0) + 1
    seen: dict[str, int] = {}
    ranked: list[tuple[int, int]] = []
    for index, mat in enumerate(mats):
        name = mat.materialName
        seen[name] = seen.get(name, 0) + 1
        cut = any(_mesh_name_is_cut(mesh_name, name) for mesh_name in mesh_names)
        if name not in mesh_counts and not cut:
            ranked.append((0, index))
        elif name in mesh_counts and seen[name] > mesh_counts[name]:
            ranked.append((1, index))
        elif cut:
            ranked.append((2, index))
    # Rank is the priority. File order must not drop a cut vaccine name
    # while an unused material is still in the list.
    ranked.sort()
    drop_at = {index for _, index in ranked[:extra]}
    if not drop_at:
        return []
    notes: list[str] = []
    kept = []
    for index, mat in enumerate(mats):
        if index in drop_at:
            notes.append(f"dropped {mat.materialName} (mesh has no slot)")
            continue
        kept.append(mat)
    mdf.materialList = kept
    return notes


def _index_pairing_is_trustworthy(mdf_names: list[str], mesh_names: list[str]) -> bool:
    """True when renaming by index keeps each shared name's textures.

    A leftover name (Holster where the mesh says Body2) is safe to rename:
    the textures at that index belong to the mesh slot. A shared name may
    also sit one slot off when a leftover is what displaced it. Latex's
    ``clear_Mat`` is on the accessories index and ``Panel`` is on the clear
    index; the dress textures are the Holster leftover on Body2.

    A swap of two shared names is the other case. Elite's face list is
    Eyelash then Face; the mesh lists Face then Eyelash. Renaming by index
    puts the hair shader on the face, which drops the neck and the head.
    """
    if _names_repeat(mdf_names) or _names_repeat(mesh_names):
        return False
    mdf_at = {name: i for i, name in enumerate(mdf_names)}
    mesh_at = {name: i for i, name in enumerate(mesh_names)}
    mdf_set = set(mdf_at)
    mesh_set = set(mesh_at)
    shared = mdf_set & mesh_set
    if not shared:
        return True
    displaced = 0
    for name in shared:
        mdf_i = mdf_at[name]
        mesh_i = mesh_at[name]
        if mdf_i == mesh_i:
            continue
        if mesh_i >= len(mdf_names) or mdf_i >= len(mesh_names):
            return False
        # The other slot is also a shared name. That is a swap.
        if mdf_names[mesh_i] in mesh_set or mesh_names[mdf_i] in mdf_set:
            return False
        displaced += 1
    # One Skirt name on the wrong slot must not rename the whole list.
    # A leftover that pushed clear_Mat over by one slot may: the other
    # shared names already agree.
    return displaced * 2 < len(shared)


def used_material_names(re_mesh) -> set[str]:
    """Material names on submeshes that actually have faces.

    Empty slots in this mesh are a single triangle (face count 3). Those
    are not a piece of the outfit.
    """
    names = material_names(re_mesh)
    used: set[str] = set()
    for entry in _iter_subdivisions(re_mesh):
        index = int(getattr(entry, "materialIndex", -1))
        faces = int(getattr(entry, "faceCount", 0) or 0)
        if faces > 3 and 0 <= index < len(names):
            used.add(names[index])
    return used


def _material_role(name: str) -> str:
    """``pl2020_Boots_Mat`` and ``pl1000_Boots_Mat`` share ``Boots_Mat``."""
    match = re.match(r"pl\d+_(.+)", name)
    return match.group(1) if match else name


# A clothing donor on one of these slots is a different shader than the
# face file expects. RTX loads every used name, and that one material
# unloads the whole face. The bunny-ears head is that case: the dress
# was the only unbound material, and the extra eye slot was the only hole.
_HEAD_SLOT_MARKERS = (
    "face", "eye", "lash", "tear", "hair", "teeth", "tooth", "mouth", "brow",
)


def _is_head_slot(name: str) -> bool:
    role = _material_role(name).lower()
    return any(marker in role for marker in _HEAD_SLOT_MARKERS)


def _albedo_key(mat) -> str:
    for tex in getattr(mat, "textureList", []) or []:
        path = (getattr(tex, "texturePath", "") or "").replace("\\", "/")
        kind = getattr(tex, "textureType", "") or ""
        if "Base" in kind or "albm" in path.lower():
            return path.rsplit("/", 1)[-1].lower()
    return ""


def _bind_unmatched_mesh_names(mdf, mesh_names: list[str], used_names) -> list[str]:
    """Point an unused material at a mesh slot the MDF never named.

    The mesh and the MDF have the same count. Adding a material makes the
    body file longer than the mesh list, and the game then checkerboards
    every slot on that mesh. Rename a material the mesh does not look up.
    A slot named ``pl1000_Boots_Mat`` takes ``pl2020_Boots_Mat`` (same role).
    One leftover clothing slot takes the one clothing material whose
    texture is not already on a mesh name. A face, eye, hair, or tear
    slot does not: that clothing shader unloads the face file.
    """
    mesh_set = set(mesh_names)
    present = {mat.materialName for mat in mdf.materialList}
    holes: list[str] = []
    for name in mesh_names:
        if name in present:
            continue
        if used_names is not None and name not in used_names:
            continue
        if name not in holes:
            holes.append(name)

    donors_by_role: dict[str, list] = {}
    for mat in mdf.materialList:
        if mat.materialName in mesh_set:
            continue
        donors_by_role.setdefault(_material_role(mat.materialName), []).append(mat)

    notes: list[str] = []
    still: list[str] = []
    for name in holes:
        donors = donors_by_role.get(_material_role(name), [])
        if len(donors) != 1:
            still.append(name)
            continue
        donor = donors.pop(0)
        old = donor.materialName
        donor.materialName = name
        notes.append(f"{old} -> {name} (mesh slot had no material)")

    if len(still) != 1:
        return notes

    bound = {mat.materialName for mat in mdf.materialList} & mesh_set
    shown = {_albedo_key(mat) for mat in mdf.materialList if mat.materialName in bound}
    shown.discard("")
    orphans = []
    for mat in mdf.materialList:
        if mat.materialName in mesh_set:
            continue
        key = _albedo_key(mat)
        if key and key not in shown:
            orphans.append(mat)
    if len(orphans) != 1 or _is_head_slot(still[0]):
        return notes
    donor = orphans[0]
    old = donor.materialName
    donor.materialName = still[0]
    notes.append(f"{old} -> {still[0]} (only unbound clothing material)")
    return notes


# Every subset of unused names is scored. Past this, fall through to the
# bind-then-drop path instead of hanging the convert.
_MAX_INDEX_DROP_SEARCH = 4096


def _index_rename_after_dropping_extras(
    mdf, mesh_names: list[str]
) -> list[str] | None:
    """Drop unused names, then index-rename, when that pairing is trustworthy.

    Latex can lose one empty slot on export. The dress is still the leftover
    name at that index. Dropping the extra unused name makes the lists line
    up. Shared names that disagree (Moto, Punisher) do not pass, so those
    stay on the bind-then-drop path.
    """
    mats = list(getattr(mdf, "materialList", []) or [])
    extra = len(mats) - len(mesh_names)
    if extra <= 0:
        return None
    mesh_set = set(mesh_names)
    candidates = []
    for index, mat in enumerate(mats):
        name = mat.materialName
        if name in mesh_set:
            continue
        if any(_mesh_name_is_cut(mesh_name, name) for mesh_name in mesh_names):
            continue
        candidates.append(index)
    if len(candidates) < extra:
        return None
    if math.comb(len(candidates), extra) > _MAX_INDEX_DROP_SEARCH:
        return None
    best: tuple | None = None
    for combo in combinations(candidates, extra):
        drop = set(combo)
        kept = [mat for index, mat in enumerate(mats) if index not in drop]
        names = [mat.materialName for mat in kept]
        if not _index_pairing_is_trustworthy(names, list(mesh_names)):
            continue
        renames = sum(1 for old, new in zip(names, mesh_names) if old != new)
        key = (renames, combo)
        if best is None or key < best[0]:
            best = (key, drop)
    if best is None:
        return None
    drop = best[1]
    notes: list[str] = []
    kept = []
    for index, mat in enumerate(mats):
        if index in drop:
            notes.append(f"dropped {mat.materialName} (mesh has no slot)")
            continue
        kept.append(mat)
    for mat, name in zip(kept, mesh_names):
        old = mat.materialName
        if old == name:
            continue
        mat.materialName = name
        notes.append(f"{old} -> {name} (match mesh slot)")
    mdf.materialList = kept
    return notes


def albedo_rank_in_folder(folder: str):
    """File size of each albedo beside the material file. 0 when it is absent."""
    sizes: dict[str, int] = {}
    if folder and os.path.isdir(folder):
        for name in os.listdir(folder):
            path = os.path.join(folder, name)
            if os.path.isfile(path):
                sizes[name.lower()] = os.path.getsize(path)

    def rank(mat) -> int:
        key = _albedo_key(mat)
        if not key:
            return 0
        best = 0
        for name, size in sizes.items():
            if name == key or name.startswith(key + "."):
                best = max(best, size)
        return best

    return rank


def _collapse_duplicate_material_names(
    mdf, mesh_names: list[str], used_names, rank
) -> list[str]:
    """One RTX lookup per name. Keep the real albedo, not a flat duplicate.

    Classic can stack several materials on one name and paint by index.
    RTX keeps a single material for that name, so a white placeholder in
    front of the suit map hides the suit, and a live slot with no material
    (the skin) draws nothing. The largest albedo keeps the shared name.
    The next real map fills a mesh slot that still has no material.
    """
    if rank is None:
        return []
    notes: list[str] = []
    groups: dict[str, list] = {}
    for index, mat in enumerate(mdf.materialList):
        groups.setdefault(mat.materialName, []).append((index, mat))
    mesh_set = set(mesh_names)
    displaced: list[tuple[int, int, object]] = []
    for name, items in groups.items():
        if len(items) < 2 or name not in mesh_set:
            continue
        scored = []
        for index, mat in items:
            try:
                score = int(rank(mat) or 0)
            except OSError:
                score = 0
            scored.append((score, index, mat))
        best_score = max(item[0] for item in scored)
        if best_score <= 0:
            continue
        winner = min(
            (item for item in scored if item[0] == best_score),
            key=lambda item: item[1],
        )
        notes.append(f"{name} keeps {_albedo_key(winner[2]) or name}")
        for score, index, mat in scored:
            if mat is winner[2]:
                continue
            mat.materialName = f"__dup_{index}"
            displaced.append((score, index, mat))
    if not displaced:
        return []
    present = {mat.materialName for mat in mdf.materialList}
    used: list[str] = []
    unused: list[str] = []
    for name in mesh_names:
        if name in present or name in used or name in unused:
            continue
        if used_names is None or name in used_names:
            used.append(name)
        else:
            unused.append(name)
    displaced.sort(key=lambda item: (-item[0], item[1]))
    real = [item for item in displaced if item[0] > 0]
    rest = [item for item in displaced if item[0] <= 0]
    for hole in used:
        if not real:
            break
        _score, _index, mat = real.pop(0)
        key = _albedo_key(mat)
        mat.materialName = hole
        notes.append(f"{key or 'material'} -> {hole} (unbound mesh slot)")
    for hole, item in zip(unused, real + rest):
        item[2].materialName = hole
    return notes


def _reorder_same_names(mdf, mesh_names: list[str]) -> list[str] | None:
    """Move each material onto the mesh slot of its own name.

    The face file lists Eyelash, then Face. The mesh lists Face, then
    Eyelash. The hair shader has to stay named Eyelash and sit on the
    eyelash slot. Renaming the eyelash slot to Face drops the head.
    """
    mats = list(getattr(mdf, "materialList", []) or [])
    names = [mat.materialName for mat in mats]
    order = slot_remap(names, mesh_names)
    if order is None or order == list(range(len(order))):
        return None
    mdf.materialList = [mats[index] for index in order]
    return [
        f"{names[index]} moved to mesh slot {slot}"
        for slot, index in enumerate(order)
        if slot != index
    ]


def align_mdf_names_to_mesh(
    mdf,
    mesh_names: list[str],
    used_names: set[str] | None = None,
    albedo_rank=None,
) -> list[str]:
    """Rename MDF slots to the mesh names at the same index.

    Shaders and texture binds stay on the slot. Writer rebuilds hashes from
    the new names. A material file longer than the mesh drops the names the
    mesh does not use; adding materials checkerboards the whole mesh, so
    this never grows the list. If the two lists share names that already
    disagree about which slot they are on, the MDF name is the one the mesh
    looks up and this does not rename. A mesh slot that still has no
    material takes the name of an unused material.
    """
    if not mesh_names:
        return []
    mats = list(getattr(mdf, "materialList", []) or [])
    mdf_names = [mat.materialName for mat in mats]
    # A repeated name is classic index stacking. The last copy can sit on
    # the mesh slot and look "trustworthy", which would keep a small
    # placeholder and rename the real albedo away. Collapse by file size
    # instead.
    duplicated = len(mdf_names) != len(set(mdf_names))
    # The same names in a different order stay with their textures and move
    # to the mesh slot. Renaming that list by index put the hair shader on
    # the face. A longer file still has to rename a donor onto a hole
    # first: dropping first can delete the jacket material.
    if not duplicated and len(mats) == len(mesh_names):
        reordered = _reorder_same_names(mdf, list(mesh_names))
        if reordered is not None:
            return reordered
    if (
        not duplicated
        and len(mats) == len(mesh_names)
        and _index_pairing_is_trustworthy(mdf_names, list(mesh_names))
    ):
        notes: list[str] = []
        for mat, name in zip(mats, mesh_names):
            old = mat.materialName
            if old == name:
                continue
            mat.materialName = name
            notes.append(f"{old} -> {name} (match mesh slot)")
        return notes
    if not duplicated:
        aligned = _index_rename_after_dropping_extras(mdf, list(mesh_names))
        if aligned is not None:
            return aligned
    notes = _collapse_duplicate_material_names(
        mdf, list(mesh_names), used_names, albedo_rank,
    )
    notes.extend(_bind_unmatched_mesh_names(mdf, list(mesh_names), used_names))
    notes.extend(_drop_materials_the_mesh_does_not_name(mdf, list(mesh_names)))
    return notes


def mesh_names_from_file(path: str, file_re_mesh) -> list[str]:
    return material_names(file_re_mesh.readREMesh(path))
