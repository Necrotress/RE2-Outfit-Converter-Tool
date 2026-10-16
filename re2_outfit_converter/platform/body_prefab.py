"""Write the ray-tracing body prefab the game actually loads.

RTX ignores ``.pfb.16``. Elza, Military, and '98 ship a ``.pfb.17`` with
no chain, so a converted ``pl1004.chain.46`` never runs and the vest,
cardigan, and breasts stay still. Jacket's ``.pfb.17`` already names
``pl1000.chain``, which is why an in-place chain file is enough there.

A mod body prefab is usually a vanilla classic body prefab with in-place
string edits (mesh, material, chain). The matching ray-tracing prefab is
that same edit applied to the RT twin, so the offset table stays valid.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..outfits import Outfit
from ..paths import assets_dir, ensure_dir_ci, mesh_roots, parts_dir, resolve_ci

# Body chains the ray-tracing pak already has. A private chain such as
# pl1004.chain has to be in the mod or the prefab must not name it.
_PAK_CHAINS = frozenset({
    "pl1000.chain",
    "pl1005.chain",
    "pl1057.chain",
    "pl1070.chain",
    "pl1071.chain",
    "pl1075.chain",
})
_TEMPLATE_DIR = "body_prefab"


def publish_rt_body_prefabs(staging: Path, report) -> None:
    """Add a ``.pfb.17`` next to a classic body prefab RTX would ignore."""
    natives = staging / "natives"
    if not natives.is_dir():
        return
    pairs = _template_pairs()
    if not pairs:
        return
    shipped = _chain_stems(natives)
    for prefab in natives.rglob("pl1000_body_*.pfb.16"):
        if not prefab.is_file():
            continue
        dest = prefab.with_name(prefab.name.split(".", 1)[0] + ".pfb.17")
        if dest.is_file():
            continue
        try:
            mod = prefab.read_bytes()
        except OSError as exc:
            report.warnings.append(f"{prefab.name}: {exc}")
            continue
        derived = _derive(mod, pairs)
        if derived is None:
            derived = _transplant_custom_chain(mod, prefab.name)
        if derived is None:
            if _custom_chains(mod):
                report.warnings.append(
                    f"{prefab.name}: body chain was not attached to a ray "
                    "tracing prefab, so those parts stay on the vanilla rig."
                )
            continue
        missing = [
            stem for stem in _custom_chains(derived)
            if stem not in shipped
        ]
        if missing:
            report.warnings.append(
                f"{prefab.name}: ray tracing prefab was not written because "
                f"{', '.join(missing)} is not in the mod."
            )
            continue
        dest.write_bytes(derived)
        chains = ", ".join(sorted(_chain_stems_in(derived))) or "its chain"
        report.warnings.append(
            f"{prefab.name}: ray tracing body prefab loads {chains}."
        )


def _template_pairs() -> list[tuple[bytes, bytes]]:
    folder = assets_dir() / _TEMPLATE_DIR
    if not folder.is_dir():
        return []
    pairs: list[tuple[bytes, bytes]] = []
    for classic in sorted(folder.glob("*.pfb.16")):
        rt = classic.with_name(classic.name.replace(".pfb.16", ".pfb.17"))
        if rt.is_file():
            pairs.append((classic.read_bytes(), rt.read_bytes()))
    return pairs


def publish_classic_body_prefabs(staging: Path, report) -> None:
    """Write a ``.pfb.16`` from a ray-tracing body prefab that matches a template.

    Classic ignores ``.pfb.17``. The derive runs in reverse: the ray-tracing
    template is the source and the classic twin receives the same edits.
    """
    natives = staging / "natives"
    if not natives.is_dir():
        return
    pairs = [(rt, classic) for classic, rt in _template_pairs()]
    if not pairs:
        return
    for prefab in natives.rglob("pl1000_body_*.pfb.17"):
        if not prefab.is_file():
            continue
        dest = prefab.with_name(prefab.name.split(".", 1)[0] + ".pfb.16")
        if dest.is_file():
            continue
        try:
            mod = prefab.read_bytes()
        except OSError as exc:
            report.warnings.append(f"{prefab.name}: {exc}")
            continue
        derived = _derive(mod, pairs)
        if derived is None:
            continue
        dest.write_bytes(derived)
        chains = ", ".join(sorted(_chain_stems_in(derived))) or "its chain"
        report.warnings.append(
            f"{prefab.name}: classic body prefab loads {chains}."
        )


def _derive(mod: bytes, pairs: list[tuple[bytes, bytes]]) -> bytes | None:
    found: list[tuple[int, int, int, bytes]] = []
    for template, twin in pairs:
        parsed = _edits(template, mod)
        if parsed is None:
            continue
        edits, zeros, dwords = parsed
        if not edits and not zeros and not dwords:
            continue
        applied = _apply(twin, edits, zeros, dwords)
        if applied is None:
            continue
        found.append((len(edits), len(zeros), len(dwords), applied))
    if not found:
        return None
    found.sort(key=lambda item: item[:3])
    best = found[0]
    tied = [item for item in found if item[:3] == best[:3]]
    if len({item[3] for item in tied}) > 1:
        return None
    return best[3]


def _edits(
    template: bytes, mod: bytes,
) -> tuple[list[tuple[str, str]], list[bytes], list[tuple[int, bytes, bytes]]] | None:
    """In-place string swaps, cleared dwords, and other dword edits."""
    if len(template) != len(mod):
        return None
    covered = bytearray(len(template))
    edits: list[tuple[str, str]] = []
    i = 0
    while i + 1 < len(template):
        slot = _wstring_at(template, i)
        if slot is None:
            i += 2
            continue
        text, end = slot
        covered[i:end] = b"\x01" * (end - i)
        if template[i:end] != mod[i:end]:
            parsed = _wstring_at(mod, i)
            if parsed is None:
                return None
            new_text, new_end = parsed
            if new_end > end or len(new_text) > len(text):
                return None
            if mod[new_end:end] != b"\x00" * (end - new_end):
                return None
            edits.append((text, new_text))
        i = end if end % 2 == 0 else end + 1
    zeros: list[bytes] = []
    dwords: list[tuple[int, bytes, bytes]] = []
    i = 0
    while i < len(template):
        if template[i] == mod[i] or covered[i]:
            i += 1
            continue
        if (
            i % 4 == 0
            and i + 4 <= len(template)
            and not any(covered[i:i + 4])
        ):
            old = bytes(template[i:i + 4])
            new = bytes(mod[i:i + 4])
            if new == b"\x00\x00\x00\x00":
                zeros.append(old)
            else:
                dwords.append((i, old, new))
            i += 4
            continue
        return None
    return edits, zeros, dwords


def _apply(
    rt: bytes,
    edits: list[tuple[str, str]],
    zeros: list[bytes],
    dwords: list[tuple[int, bytes, bytes]],
) -> bytes | None:
    data = bytearray(rt)
    by_old: dict[str, str] = {}
    for old, new in edits:
        if old in by_old and by_old[old] != new:
            return None
        by_old[old] = new
    ordered = sorted(by_old.items(), key=lambda pair: len(pair[0]), reverse=True)
    for old, new in ordered:
        old_b = old.encode("utf-16le") + b"\x00\x00"
        if old_b not in data:
            return None
        new_b = (new.encode("utf-16le") + b"\x00\x00").ljust(len(old_b), b"\x00")
        if len(new_b) != len(old_b):
            return None
        data = bytearray(bytes(data).replace(old_b, new_b))
    for dword in zeros:
        start = 0
        hits: list[int] = []
        while True:
            idx = data.find(dword, start)
            if idx < 0:
                break
            hits.append(idx)
            start = idx + 1
        if len(hits) == 1:
            at = hits[0]
            data[at:at + 4] = b"\x00\x00\x00\x00"
    for offset, old, new in dwords:
        if offset + 4 > len(data):
            continue
        if bytes(data[offset:offset + 4]) != old:
            continue
        data[offset:offset + 4] = new
    return bytes(data)


def _wstring_at(data: bytes, pos: int) -> tuple[str, int] | None:
    if pos % 2 or pos + 5 >= len(data):
        return None
    if data[pos + 1] != 0 or not (32 <= data[pos] < 127):
        return None
    chars: list[str] = []
    j = pos
    while j + 1 < len(data) and data[j + 1] == 0 and 32 <= data[j] < 127:
        chars.append(chr(data[j]))
        j += 2
    if len(chars) < 2 or j + 1 >= len(data) or data[j] != 0 or data[j + 1] != 0:
        return None
    return "".join(chars), j + 2


def _transplant_custom_chain(classic: bytes, prefab_name: str) -> bytes | None:
    """Put a private chain on the slot prefab when the classic file matches no twin.

    Elza and Military ship no chain, so a vest or jacket sim never starts and
    the pak chain (Noir's necktie, on that slot) freezes the outfit change.
    The mesh, material, and chain paths are copied only when each one is the
    same length as the chain-bearing template. A shorter name would move the
    next field and the game would throw the prefab out. The template joint
    file stays: classic ships ``.jcns.11`` and ray tracing reads ``.jcns.19``.
    Pointing the costume at the classic file freezes the outfit change.
    """
    if not _custom_chains(classic):
        return None
    template = _chain_template(prefab_name)
    if template is None:
        return None
    data = template
    mesh_old = _player_resource(template, ".mesh")
    mesh_new = _player_resource(classic, ".mesh")
    chain_old = _player_resource(template, ".chain")
    chain_new = _player_resource(classic, ".chain")
    if not mesh_old or not mesh_new or not chain_old or not chain_new:
        return None
    if len(mesh_old) != len(mesh_new) or len(chain_old) != len(chain_new):
        return None
    data = _replace_u16(data, mesh_old, mesh_new)
    data = _replace_u16(data, chain_old, chain_new)
    old = _player_resource(template, ".mdf2")
    new = _player_resource(classic, ".mdf2")
    if old and new and len(old) == len(new):
        data = _replace_u16(data, old, new)
    for old, new in _same_suffix_material_pairs(template, classic):
        data = _replace_u16(data, old, new)
    if data == template:
        return None
    return data


def _same_suffix_material_pairs(
    template: bytes, classic: bytes,
) -> list[tuple[str, str]]:
    """Pair ``plXXXX_*_Mat`` names that share the suffix and the length.

    ``pl1005_Body_Mat`` matches ``pl5300_Body_Mat``. ``Body02`` does not
    match ``Body2``. A shorter name would move the next field.
    """
    classic_by_suffix: dict[str, str] = {}
    for name in _prefab_mat_names(classic):
        _id, _, suffix = name.partition("_")
        if suffix:
            classic_by_suffix.setdefault(suffix, name)
    pairs: list[tuple[str, str]] = []
    used: set[str] = set()
    for name in sorted(_prefab_mat_names(template), key=len, reverse=True):
        _id, _, suffix = name.partition("_")
        new = classic_by_suffix.get(suffix)
        if not suffix or suffix in used or new is None:
            continue
        if len(name) != len(new) or name == new:
            continue
        pairs.append((name, new))
        used.add(suffix)
    return pairs


def _chain_template(prefab_name: str) -> bytes | None:
    """The slot's ray-tracing body, or Noir's when that slot ships no chain."""
    folder = assets_dir() / _TEMPLATE_DIR
    token = _template_slot_token(prefab_name)
    direct = folder / f"pl1000_body_{token}.pfb.17"
    if direct.is_file():
        data = direct.read_bytes()
        if _chain_stems_in(data):
            return data
    donor = folder / "pl1000_body_costume_a.pfb.17"
    if not donor.is_file() or len(token) != len("costume_a"):
        return None
    return _replace_u16(
        donor.read_bytes(),
        "pl1000_body_costume_a",
        f"pl1000_body_{token}",
    )


def _player_resource(data: bytes, suffix: str) -> str | None:
    needle = "SectionRoot/Character/Player/"
    i = 0
    while i + 1 < len(data):
        slot = _wstring_at(data, i)
        if slot is None:
            i += 2
            continue
        text, end = slot
        if text.startswith(needle) and text.endswith(suffix):
            return text
        i = end if end % 2 == 0 else end + 1
    return None


def _chain_stems(natives: Path) -> set[str]:
    found: set[str] = set()
    for path in natives.rglob("*"):
        if not path.is_file():
            continue
        low = path.name.lower()
        if ".chain." not in low:
            continue
        found.add(low.split(".chain.", 1)[0] + ".chain")
    return found


def _chain_stems_in(data: bytes) -> set[str]:
    stems: set[str] = set()
    i = 0
    while i + 1 < len(data):
        slot = _wstring_at(data, i)
        if slot is None:
            i += 2
            continue
        text, end = slot
        if text.lower().endswith(".chain"):
            stems.add(text.replace("\\", "/").rsplit("/", 1)[-1].lower())
        i = end if end % 2 == 0 else end + 1
    return stems


def _custom_chains(data: bytes) -> list[str]:
    return sorted(stem for stem in _chain_stems_in(data) if stem not in _PAK_CHAINS)


_MAT_NAME_RE = re.compile(r"pl[0-9]{4}_[A-Za-z0-9_]+_Mat")
# Primary slot of each Claire outfit. Jacket stays on the default prefab:
# costume_1 points at the alternate mdf, which is not what draws the mesh.
_SOURCE_BODY_TEMPLATE = {
    "jacket": "pl1000_body_default.pfb.17",
    "tanktop": "pl1000_body_costume_3.pfb.17",
    "classic_jacket": "pl1000_body_costume_5.pfb.17",
    "classic_tanktop": "pl1000_body_costume_8.pfb.17",
    "noir": "pl1000_body_costume_a.pfb.17",
    "military": "pl1000_body_costume_b.pfb.17",
    "elza": "pl1000_body_costume_c.pfb.17",
}


def publish_rt_slot_body_prefab(
    staging: Path,
    report,
    source: Outfit,
    body_id: str,
    slot: str,
) -> None:
    """Write the target slot's ``.pfb.17`` from the source outfit's prefab.

    A mesh-only ray-tracing mod ships no body prefab, so the pak file for
    the destination slot draws. That file names the destination materials
    and chain. The body does not draw, and the swap freezes. The prefab
    written here is the source outfit's, with the body id retargeted, so
    the mesh path and the chain stay a pair. Material names keep the
    source spelling. A shorter name shifts the next field and the game
    throws the file out.
    """
    if source.character != "claire" or len(body_id) != 6 or len(source.body_id) != 6:
        return
    natives = staging / "natives"
    if not natives.is_dir() or not _body_mesh_present(staging, body_id):
        return
    existing = [
        path for path in natives.rglob(f"pl1000_body_{slot}.pfb.17")
        if path.is_file()
    ]
    if _prefab_keeps_shipped_chain(existing, staging):
        return
    template_path = _source_body_template(source)
    if template_path is None:
        return
    data = _retarget_source_body(
        template_path.read_bytes(),
        source.body_id,
        body_id,
        _template_slot_token(template_path.name),
        slot,
        staging,
    )
    if existing and all(path.read_bytes() == data for path in existing):
        return
    missing = [
        stem for stem in _chain_stems_in(data)
        if stem not in _PAK_CHAINS and not _chain_on_disk(staging, stem)
    ]
    if missing:
        report.warnings.append(
            f"pl1000_body_{slot}.pfb.17: ray tracing body prefab was not "
            f"written because {', '.join(missing)} is not in the mod."
        )
        return
    if existing:
        for path in existing:
            path.write_bytes(data)
        dest_name = existing[0].name
    else:
        dest_dir = ensure_dir_ci(staging, parts_dir())
        dest = dest_dir / f"pl1000_body_{slot}.pfb.17"
        dest.write_bytes(data)
        dest_name = dest.name
    chains = ", ".join(sorted(_chain_stems_in(data))) or "no chain"
    report.warnings.append(
        f"{dest_name}: ray tracing body prefab loads "
        f"pl1000/{body_id}/{body_id}.mesh and {chains}."
    )


def publish_rt_jacket_body_prefab(
    staging: Path,
    report,
    body_id: str,
    slot: str,
) -> None:
    """Write a jacket-shaped ``.pfb.17`` for this slot.

    Kept for callers that already know the mesh is a jacket. Slot changes
    go through :func:`publish_rt_slot_body_prefab`.
    """
    from ..outfits import CLAIRE_OUTFIT_BY_KEY

    publish_rt_slot_body_prefab(
        staging, report, CLAIRE_OUTFIT_BY_KEY["jacket"], body_id, slot,
    )


def _prefab_keeps_shipped_chain(paths: list[Path], staging: Path) -> bool:
    """True when this slot's prefab already names a private chain in the mod.

    The source-outfit template has no chain on Elza and Military. Writing it
    over a transplanted prefab drops ``pl5300.chain`` and the cloth sim stops.
    """
    for path in paths:
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if any(_chain_on_disk(staging, stem) for stem in _custom_chains(data)):
            return True
    return False


def _prefab_mat_names(data: bytes) -> set[str]:
    found: set[str] = set()
    i = 0
    while i + 1 < len(data):
        slot = _wstring_at(data, i)
        if slot is None:
            i += 2
            continue
        text, end = slot
        if _MAT_NAME_RE.fullmatch(text):
            found.add(text)
        i = end if end % 2 == 0 else end + 1
    return found


def _body_mesh_present(staging: Path, body_id: str) -> bool:
    for root in mesh_roots():
        folder = resolve_ci(staging, f"{root}/{body_id}")
        if folder is None:
            continue
        for path in folder.iterdir():
            if path.is_file() and ".mesh" in path.name.lower():
                return True
    return False


def _source_body_template(source: Outfit) -> Path | None:
    name = _SOURCE_BODY_TEMPLATE.get(source.key)
    if name is None:
        return None
    path = assets_dir() / _TEMPLATE_DIR / name
    if not path.is_file():
        return None
    return path


def _template_slot_token(filename: str) -> str:
    stem = filename.split(".pfb.", 1)[0]
    return stem[len("pl1000_body_"):]


def _chain_on_disk(staging: Path, stem: str) -> bool:
    natives = staging / "natives"
    if not natives.is_dir():
        return False
    low = stem.lower()
    prefix = low + "."
    for path in natives.rglob("*"):
        if not path.is_file():
            continue
        name = path.name.lower()
        if name == low:
            return True
        rest = name[len(prefix):] if name.startswith(prefix) else ""
        if rest.isdigit():
            return True
    return False


def _retarget_source_body(
    data: bytes,
    src_id: str,
    body_id: str,
    token: str,
    slot: str,
    staging: Path,
) -> bytes:
    """Point the source prefab at ``body_id`` without changing a pak chain.

    The mesh lives in ``pl1000/<body>/<body>.mesh``. Replacing only the
    filename leaves the folder as the source id and the body does not load.
    Material names change by the body id only. The character count in front
    of each name has to stay, because the next field starts immediately
    after that many wide characters.
    """
    if src_id != body_id:
        data = _replace_u16(
            data,
            f"pl1000/{src_id}/{src_id}.mesh",
            f"pl1000/{body_id}/{body_id}.mesh",
        )
        data = _replace_u16(
            data,
            f"pl1000/{src_id}/{src_id}.mdf2",
            f"pl1000/{body_id}/{body_id}.mdf2",
        )
        for variant in ("01", "02"):
            data = _replace_u16(
                data,
                f"pl1000/{src_id}/{src_id}_{variant}/{src_id}_{variant}.mdf2",
                f"pl1000/{body_id}/{src_id}_{variant}/{body_id}_{variant}.mdf2",
            )
        names = sorted(
            (name for name in _prefab_mat_names(data) if name.startswith(src_id + "_")),
            key=len,
            reverse=True,
        )
        for name in names:
            data = _replace_u16(data, name, body_id + name[len(src_id):])
        data = _retarget_shipped_chains(data, src_id, body_id, staging)
    if token != slot and len(token) == len(slot):
        data = _replace_u16(data, f"pl1000_body_{token}", f"pl1000_body_{slot}")
    return data


def _retarget_shipped_chains(
    data: bytes, src_id: str, body_id: str, staging: Path,
) -> bytes:
    """A chain the mod shipped moves with the body id. A pak chain does not."""
    src = src_id.lower()
    for stem in sorted(_chain_stems_in(data), key=len, reverse=True):
        if stem in _PAK_CHAINS or not stem.startswith(src + "."):
            continue
        new_stem = body_id + stem[len(src):]
        if not _chain_on_disk(staging, new_stem):
            continue
        data = _replace_u16(data, stem, new_stem)
    return data


def _replace_u16(data: bytes, old: str, new: str) -> bytes:
    if len(old) != len(new) or old == new:
        return data
    return data.replace(old.encode("utf-16le"), new.encode("utf-16le"))
