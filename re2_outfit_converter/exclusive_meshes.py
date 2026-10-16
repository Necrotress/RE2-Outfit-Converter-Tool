"""Override exclusive hair meshes for the costume-select 3D preview.

Gameplay hides the hat/headband via the hair redirect PFB (Claire ``pl1070``,
Leon ``pl0070``, or isolated hair). The costume-select preview still
instantiates the exclusive mesh IDs (Claire Noir/Military ``pl1075`` /
``pl1071``; Leon Noir/Sheriff ``pl0074`` / ``pl0075``). Copying that
character's shared hair under those IDs makes the preview match gameplay.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from .character import CLAIRE_PROFILE, CharacterProfile
from .isolation import staging_mesh_ids
from .outfits import Outfit
from .paths import (
    assets_dir,
    ensure_dir_ci,
    mesh_roots,
    natives_platform,
    resolve_ci,
)
from .reports import ConversionReport

_TEMPLATE_DIR = "exclusive_hide/pl1070_hair"
_MESH_NAME_RE = re.compile(r"\.mesh(?:\.\d+)?$", re.IGNORECASE)
# Loose face stems (pl1060) live in a private folder after isolation.
# Copying that folder onto pl1071/pl1075 draws a second head in the hair slot.
_FACE_MESH_STEMS = frozenset({
    "pl1050", "pl1057", "pl1060",
    "pl0050", "pl0057", "pl0060",
})


def _mesh_stems(folder: Path) -> list[str]:
    stems: list[str] = []
    if not folder.is_dir():
        return stems
    for path in folder.iterdir():
        if not path.is_file() or not _MESH_NAME_RE.search(path.name):
            continue
        stems.append(path.name.split(".")[0].lower().lstrip("-"))
    return stems


def _is_face_kit(folder: Path, src_id: str, profile: CharacterProfile) -> bool:
    """True when this folder is a head, not a hair kit."""
    if src_id.lower() in profile.face_ids:
        return True
    stems = _mesh_stems(folder)
    if not stems:
        return False
    face = _FACE_MESH_STEMS | {mid.lower() for mid in profile.face_ids}
    return all(stem in face for stem in stems)


def _folder_has_mesh(folder: Path) -> bool:
    if not folder.is_dir():
        return False
    return any(
        p.is_file() and _MESH_NAME_RE.search(p.name)
        for p in folder.iterdir()
    )


def _dest_name(filename: str, src_id: str, dest_id: str) -> str:
    """Rename mesh/mdf2/chain stems only; keep texture basenames for mdf refs.

    Custom hair kits often live under ``pl1605/pl1678.mesh`` — the folder id
    and file stem differ. Always retarget mesh/mdf2/chain stems to ``dest_id``
    so Noir/Military exclusive slots load ``pl1075.mesh`` / ``pl1071.mesh``.
    """
    low = filename.lower()
    src = src_id.lower()
    if low == src:
        return dest_id
    for kind in (".mesh", ".mdf2", ".chain"):
        if low.startswith(src + kind):
            return dest_id + filename[len(src_id):]
    # Mismatched stem (pl1678.mesh inside pl1605/) — still needs dest id.
    m = re.match(
        r"(pl[0-9a-zA-Z]{4})(\.(?:mesh|mdf2|chain)(?:\.\d+)?)$",
        filename, re.I)
    if m:
        return dest_id + m.group(2)
    return filename


def _iter_source_files(src_dir: Path) -> list[Path]:
    return sorted(p for p in src_dir.iterdir() if p.is_file())


def _copy_id_folder(
    src_dir: Path,
    staging: Path,
    src_id: str,
    dest_id: str,
    report: ConversionReport,
    note: str,
    profile: CharacterProfile,
) -> int:
    """Copy src_dir files into each mesh root under dest_id. Returns file count."""
    files = _iter_source_files(src_dir)
    if not files:
        return 0
    written = 0
    for root in mesh_roots(profile):
        dest_dir = ensure_dir_ci(staging, f"{root}/{dest_id}")
        for src in files:
            name = _dest_name(src.name, src_id, dest_id)
            dest = dest_dir / name
            shutil.copy2(src, dest)
            written += 1
            report.rename_ops.append(
                f"exclusive preview hide: {src.name}  ->  "
                f"{dest.relative_to(staging).as_posix()} ({note})"
            )
    return written


def _bundled_hair_template() -> Path | None:
    cand = assets_dir() / _TEMPLATE_DIR
    if _folder_has_mesh(cand):
        return cand
    return None


def _pick_source_hair_dir(
    staging: Path,
    hair_priv: str,
    profile: CharacterProfile,
    *,
    allow_template: bool = True,
) -> tuple[Path, str, str] | None:
    """Return (directory, src_id, note) for the best hair kit to mirror."""
    from .isolation import is_stable_custom_mesh_id

    present = staging_mesh_ids(staging, profile)
    candidates: list[tuple[str, str]] = []
    if hair_priv and len(hair_priv) == 6 and hair_priv in present:
        candidates.append((hair_priv, f"from isolated {hair_priv}"))
    shared = profile.default_hair_id
    if shared in present:
        candidates.append((shared, f"from mod {shared}"))
    for mid in sorted(present):
        if mid in {c[0] for c in candidates}:
            continue
        if mid in profile.exclusive_part_ids:
            continue
        if not is_stable_custom_mesh_id(mid):
            continue
        candidates.append((mid, f"from custom {mid}"))
    roots = mesh_roots(profile)
    for src_id, note in candidates:
        for root in roots:
            folder = resolve_ci(staging, f"{root}/{src_id}")
            if folder is None or not _folder_has_mesh(folder):
                continue
            if _is_face_kit(folder, src_id, profile):
                continue
            return folder, src_id, note
    # Bundled hide kit is Claire shared hair only, and it is a classic mesh.
    # On a ray-tracing tree that file would become the hair Noir's pak
    # prefab loads. Leave the game hair and chain alone instead.
    # Leon has no equivalent template.
    if allow_template and profile.key == "claire" and natives_platform() != "stm":
        template = _bundled_hair_template()
        if template is not None:
            return template, shared, "from bundled Claire hair template"
    return None


def ensure_exclusive_part_mesh_hide(
    staging: Path,
    target: Outfit,
    hair_priv: str,
    report: ConversionReport,
    *,
    allow_template: bool = True,
) -> None:
    """Place shared hair meshes on exclusive IDs for the costume preview."""
    profile = target.profile or CLAIRE_PROFILE
    exclusive_id = target.hair_id
    if exclusive_id not in profile.exclusive_part_ids:
        return

    # Mod already ships a custom exclusive mesh — leave it alone.
    for root in mesh_roots(profile):
        existing = resolve_ci(staging, f"{root}/{exclusive_id}")
        if existing is not None and _folder_has_mesh(existing):
            report.rename_ops.append(
                f"exclusive preview hide: kept existing {exclusive_id} mesh"
            )
            return

    picked = _pick_source_hair_dir(
        staging, hair_priv, profile, allow_template=allow_template)
    if picked is None:
        if not allow_template:
            report.rename_ops.append(
                f"exclusive preview hide: left {exclusive_id} alone "
                "(addon has no hair of its own)"
            )
            return
        if natives_platform() == "stm":
            report.rename_ops.append(
                f"exclusive preview hide: left {exclusive_id} alone "
                "(ray tracing keeps the game hair)"
            )
            return
        report.warnings.append(
            f"{target.name} costume preview may still show vanilla "
            f"{exclusive_id} (hat/headband): no hair mesh source"
            + (
                f" and missing bundled template ({_TEMPLATE_DIR})."
                if profile.key == "claire"
                else "."
            )
        )
        return

    src_dir, src_id, note = picked
    count = _copy_id_folder(
        src_dir, staging, src_id, exclusive_id, report, note, profile)
    if count <= 0:
        report.warnings.append(
            f"Failed to seed {exclusive_id} for {target.name} costume preview."
        )
