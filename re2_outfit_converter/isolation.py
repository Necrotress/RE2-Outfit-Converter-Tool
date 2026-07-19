"""Face/hair private IDs and shared texture isolation."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .analyzer import AnalysisResult
from .outfits import (
    CLAIRE_FACE_IDS,
    CLAIRE_HAIR_MESH_IDS,
    RESERVED_MESH_IDS,
    Outfit,
)
from .paths import MESH_ROOTS, engine_path, resolve_ci
from .reports import ConversionError, ConversionReport


def staging_mesh_ids(staging: Path) -> set[str]:
    """Collect pl1xxx folder/file stems present under mesh roots."""
    found: set[str] = set()
    for root in MESH_ROOTS:
        root_dir = resolve_ci(staging, root)
        if root_dir is None:
            continue
        for entry in root_dir.iterdir():
            m = re.match(r"(pl1\d{3})", entry.name, re.IGNORECASE)
            if m:
                found.add(m.group(1).lower())
    return found
def allocate_private_ids(seed: str, reserved: set[str]) -> tuple[str, str]:
    """Stable digit-only private face/hair IDs in pl1800–pl1899."""
    digest = hashlib.sha1(seed.encode("utf-8", errors="replace")).hexdigest()
    start = int(digest[:8], 16) % 100
    face_id: str | None = None
    for offset in range(100):
        cand = f"pl{1800 + ((start + offset) % 100)}"
        if cand not in reserved:
            face_id = cand
            reserved.add(cand)
            break
    if face_id is None:
        raise ConversionError(
            "Could not allocate a free private face mesh ID (pl1800–pl1899).")

    hair_id: str | None = None
    hair_start = (int(digest[8:16], 16) % 100)
    for offset in range(100):
        cand = f"pl{1800 + ((hair_start + offset) % 100)}"
        if cand not in reserved:
            hair_id = cand
            reserved.add(cand)
            break
    if hair_id is None:
        raise ConversionError(
            "Could not allocate a free private hair mesh ID (pl1800–pl1899).")
    return face_id, hair_id
def pick_present_id(present: set[str], preferred: list[str]) -> str | None:
    for pid in preferred:
        if pid in present:
            return pid
    return None
def isolation_seed(analysis: AnalysisResult) -> str:
    """Stable seed so AddonFor packages share the main mod's private IDs."""
    info = analysis.modinfo
    for candidate in (info.addonfor, info.nameasbundle, info.name):
        if candidate and candidate.strip():
            return candidate.strip()
    if analysis.root is not None:
        return analysis.root.name
    return "mod"
def isolate_claire_face_hair(
    staging: Path,
    analysis: AnalysisResult,
    source: Outfit,
    target: Outfit,
    rename_map: dict[str, str],
    report: ConversionReport,
) -> tuple[str, str]:
    """Move shared/exclusive face and hair meshes onto private IDs.

    Always on: keeps converted mods from fighting over pl1050 / pl1070 with
    other Fluffy Claire mods.

    Only files that actually exist in the mod are remapped. Vanilla fallback
    paths (textures/meshes the mod never shipped under pl1050/pl1070) must keep
    their shared IDs — rewriting those prefixes/IDs blindly breaks the head
    when another mod is also enabled.

    Returns the allocated (face_priv, hair_priv) IDs for further isolation steps.
    """
    seed = isolation_seed(analysis)
    present = staging_mesh_ids(staging)
    reserved = set(RESERVED_MESH_IDS) | present
    face_priv, hair_priv = allocate_private_ids(seed, reserved)

    face_src = pick_present_id(
        present,
        [source.head_id, target.head_id, *sorted(CLAIRE_FACE_IDS)],
    )
    hair_src = pick_present_id(
        present,
        [source.hair_id, target.hair_id, "pl1070", *sorted(CLAIRE_HAIR_MESH_IDS)],
    )

    if face_src and face_src != face_priv:
        for root in MESH_ROOTS:
            root_dir = resolve_ci(staging, root)
            if root_dir is not None:
                rename_entries(
                    root_dir, staging, face_src, face_priv, rename_map, report)
        alias_standard_mesh_paths(
            staging, face_src, face_priv, rename_map, report)
        report.rename_ops.append(
            f"isolated face {face_src}  ->  {face_priv}")

    if hair_src and hair_src != hair_priv:
        for root in MESH_ROOTS:
            root_dir = resolve_ci(staging, root)
            if root_dir is not None:
                rename_entries(
                    root_dir, staging, hair_src, hair_priv, rename_map, report)
        alias_standard_mesh_paths(
            staging, hair_src, hair_priv, rename_map, report)
        report.rename_ops.append(
            f"isolated hair {hair_src}  ->  {hair_priv}")
    return face_priv, hair_priv
def isolate_shared_outfit_textures(
    staging: Path,
    face_priv: str,
    rename_map: dict[str, str],
    report: ConversionReport,
) -> None:
    """Move CR-AW shared outfit texture folders onto private same-length names.

    Claire body materials often load textures from::

        Escape/Character/Player/wap100/Pl2020/Mesh/pl2900_*.tex
        Escape/Character/Textures/*.tex

    Those paths are shared across CR-AW Claire mods (BSAA, Moto, Beach Girl),
    so Fluffy overwrites cause vest/skin bleed. Rename the folders in-place to
    same-length private tokens derived from the face private ID
    (``Pl2020``→``Pl1808``, ``Textures``→``Tex_1808``) and patch mdf2 refs.

    Only remaps files that exist in the mod (no folder-prefix rewrites), and
    does **not** touch ``sectionroot/character/Textures`` — face materials still
    need vanilla paths there (e.g. ``pl_Face_BloodMask``). Rewriting those
    blanks the head and can freeze on outfit switch.
    """
    if not face_priv.lower().startswith("pl") or len(face_priv) != 6:
        return
    digits = face_priv[2:]  # e.g. 1808
    pl2020_new = f"Pl{digits}"       # Pl1808 (len 6, same as Pl2020)
    textures_new = f"Tex_{digits}"   # Tex_1808 (len 8, same as Textures)

    moved = False
    for parent_rel in (
        "natives/x64/escape/character/player/wap100",
        "natives/x64/streaming/escape/character/player/wap100",
    ):
        parent = resolve_ci(staging, parent_rel)
        if parent is not None and rename_named_folder(
                parent, staging, "Pl2020", pl2020_new, rename_map, report):
            moved = True

    for parent_rel in (
        "natives/x64/escape/character",
        "natives/x64/streaming/escape/character",
    ):
        parent = resolve_ci(staging, parent_rel)
        if parent is not None and rename_named_folder(
                parent, staging, "Textures", textures_new, rename_map, report):
            moved = True

    if moved:
        report.rename_ops.append(
            f"isolated shared textures  Pl2020->{pl2020_new}, "
            f"Textures->{textures_new}"
        )
def rename_named_folder(
    parent_dir: Path,
    staging: Path,
    old_name: str,
    new_name: str,
    rename_map: dict[str, str],
    report: ConversionReport,
) -> bool:
    """Rename one direct child folder (case-insensitive) and map shipped files.

    Only files that exist in the mod are added to ``rename_map``. A folder
    prefix rewrite would also retarget vanilla fallback paths the mod never
    shipped (same class of bug as bare face-ID rewrites).
    """
    if len(old_name) != len(new_name):
        report.warnings.append(
            f"Skipped texture folder rename {old_name}->{new_name}: "
            "length mismatch (binary paths must stay same length)."
        )
        return False
    entry = next(
        (c for c in parent_dir.iterdir()
         if c.is_dir() and c.name.lower() == old_name.lower()),
        None,
    )
    if entry is None:
        return False
    dest = entry.with_name(new_name)
    if dest.exists():
        report.warnings.append(
            f"Skipped renaming {entry.name}/ -> {new_name}/: target exists.")
        return False
    originals = [f.relative_to(entry) for f in entry.rglob("*") if f.is_file()]
    entry.rename(dest)
    report.rename_ops.append(f"folder {entry.name}/  ->  {new_name}/")
    for rel in sorted(originals):
        final = dest / rel
        add_rename(
            rename_map,
            (entry / rel).relative_to(staging).as_posix(),
            final.relative_to(staging).as_posix(),
        )
    return True
def alias_standard_mesh_paths(
    staging: Path,
    old_id: str,
    new_id: str,
    rename_map: dict[str, str],
    _report: ConversionReport,
) -> None:
    """Map standard plXXXX.mdf2/mesh/chain paths onto isolated files.

    Some mods ship ``--pl1070.mdf2`` while PFBs still reference ``pl1070.mdf2``.
    After isolation, register same-length aliases so injected/converted PFBs
    load the private assets instead of another mod's shared pl1070.
    """
    if len(old_id) != len(new_id):
        return
    for root in MESH_ROOTS:
        new_dir = resolve_ci(staging, f"{root}/{new_id}")
        if new_dir is None or not new_dir.is_dir():
            continue
        is_stream = "streaming" in root
        prefix = (
            "streaming/sectionroot/character/player/pl1000"
            if is_stream else
            "sectionroot/character/player/pl1000"
        )
        for path in sorted(new_dir.iterdir()):
            if not path.is_file():
                continue
            low = path.name.lower()
            for kind in (".mesh", ".mdf2", ".chain"):
                if kind not in low:
                    continue
                stem = path.name.split(".")[0].lower().lstrip("-")
                if stem not in (old_id, new_id):
                    continue
                new_eng = engine_path(path.relative_to(staging).as_posix())
                if not new_eng:
                    continue
                std_old = f"{prefix}/{old_id}/{old_id}{kind}"
                if len(std_old) == len(new_eng):
                    rename_map[std_old] = new_eng
def rename_entries(root_dir: Path, staging: Path, old_id: str, new_id: str,
                    rename_map: dict[str, str],
                    report: ConversionReport) -> None:
    for entry in sorted(root_dir.iterdir()):
        name_low = entry.name.lower()
        if not (name_low == old_id or name_low.startswith(old_id + ".")
                or name_low.startswith(old_id + "_")):
            continue
        new_name = new_id + entry.name[len(old_id):]
        dest = entry.with_name(new_name)
        if dest.exists():
            report.warnings.append(
                f"Skipped renaming {entry.name} -> {new_name}: target already exists.")
            continue

        if entry.is_dir():
            originals = [f.relative_to(entry) for f in entry.rglob("*") if f.is_file()]
            entry.rename(dest)
            report.rename_ops.append(f"folder {entry.name}/  ->  {new_name}/")
            for rel in sorted(originals):
                moved = dest / rel
                final = moved
                name_low = moved.name.lower()
                new_file_name = None
                if name_low.startswith(f"--{old_id}"):
                    # CR-AW style --pl1070.mdf2 -> pl1891.mdf2 (PFBs use undashed names)
                    new_file_name = new_id + moved.name[len(old_id) + 2:]
                elif name_low.startswith(old_id):
                    new_file_name = new_id + moved.name[len(old_id):]
                elif old_id in name_low:
                    # e.g. embedded id in a longer stem
                    idx = name_low.index(old_id)
                    new_file_name = (
                        moved.name[:idx] + new_id + moved.name[idx + len(old_id):]
                    )
                if new_file_name and new_file_name != moved.name:
                    candidate = moved.with_name(new_file_name)
                    if candidate.exists():
                        report.warnings.append(
                            f"Kept original name for {moved.name} in {new_name}/: "
                            f"{candidate.name} already exists."
                        )
                    else:
                        moved.rename(candidate)
                        final = candidate
                add_rename(
                    rename_map,
                    (entry / rel).relative_to(staging).as_posix(),
                    final.relative_to(staging).as_posix(),
                )
        else:
            add_rename(
                rename_map,
                entry.relative_to(staging).as_posix(),
                dest.relative_to(staging).as_posix(),
            )
            entry.rename(dest)
            report.rename_ops.append(f"{entry.name}  ->  {new_name}")
def add_rename(rename_map: dict[str, str], rel_old: str, rel_new: str) -> None:
    old_engine = engine_path(rel_old)
    new_engine = engine_path(rel_new)
    if old_engine and old_engine != new_engine:
        rename_map[old_engine] = new_engine
