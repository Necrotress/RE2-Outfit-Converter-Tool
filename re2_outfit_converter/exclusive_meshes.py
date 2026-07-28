"""Override Noir/Military exclusive hair meshes for costume-select preview.

Gameplay hides the hat/headband via the hair redirect PFB (loads pl1070 /
isolated hair). The costume-select 3D preview still instantiates the exclusive
mesh IDs (pl1075 / pl1071) from vanilla. Shipping Claire shared-hair files
under those IDs makes the preview match gameplay.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from .isolation import staging_mesh_ids
from .outfits import EXCLUSIVE_PART_IDS, Outfit
from .paths import MESH_ROOTS, assets_dir, ensure_dir_ci, resolve_ci
from .reports import ConversionReport

_TEMPLATE_DIR = "exclusive_hide/pl1070_hair"
_MESH_NAME_RE = re.compile(r"\.mesh(?:\.\d+)?$", re.IGNORECASE)


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
    m = re.match(r"(pl1\d{3})(\.(?:mesh|mdf2|chain)(?:\.\d+)?)$", filename, re.I)
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
) -> int:
    """Copy src_dir files into each mesh root under dest_id. Returns file count."""
    files = _iter_source_files(src_dir)
    if not files:
        return 0
    written = 0
    for root in MESH_ROOTS:
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
) -> tuple[Path, str, str] | None:
    """Return (directory, src_id, note) for the best hair kit to mirror."""
    from .isolation import is_stable_custom_mesh_id

    present = staging_mesh_ids(staging)
    candidates: list[tuple[str, str]] = []
    if hair_priv and len(hair_priv) == 6 and hair_priv in present:
        candidates.append((hair_priv, f"from isolated {hair_priv}"))
    if "pl1070" in present:
        candidates.append(("pl1070", "from mod pl1070"))
    for mid in sorted(present):
        if mid in {c[0] for c in candidates}:
            continue
        if not is_stable_custom_mesh_id(mid):
            continue
        candidates.append((mid, f"from custom {mid}"))
    for src_id, note in candidates:
        for root in MESH_ROOTS:
            folder = resolve_ci(staging, f"{root}/{src_id}")
            if folder is not None and _folder_has_mesh(folder):
                return folder, src_id, note
    template = _bundled_hair_template()
    if template is not None:
        return template, "pl1070", "from bundled Claire hair template"
    return None


def ensure_exclusive_part_mesh_hide(
    staging: Path,
    target: Outfit,
    hair_priv: str,
    report: ConversionReport,
) -> None:
    """Place Claire hair meshes on Noir/Military exclusive IDs for the preview."""
    exclusive_id = target.hair_id
    if exclusive_id not in EXCLUSIVE_PART_IDS:
        return

    # Mod already ships a custom exclusive mesh — leave it alone.
    for root in MESH_ROOTS:
        existing = resolve_ci(staging, f"{root}/{exclusive_id}")
        if existing is not None and _folder_has_mesh(existing):
            report.rename_ops.append(
                f"exclusive preview hide: kept existing {exclusive_id} mesh"
            )
            return

    picked = _pick_source_hair_dir(staging, hair_priv)
    if picked is None:
        report.warnings.append(
            f"{target.name} costume preview may still show vanilla "
            f"{exclusive_id} (hat/headband): no hair mesh source and missing "
            f"bundled template ({_TEMPLATE_DIR})."
        )
        return

    src_dir, src_id, note = picked
    count = _copy_id_folder(
        src_dir, staging, src_id, exclusive_id, report, note)
    if count <= 0:
        report.warnings.append(
            f"Failed to seed {exclusive_id} for {target.name} costume preview."
        )
