"""Bundle exclusive-part .mdf2 so isolated hats keep custom textures."""

from __future__ import annotations

import shutil
from pathlib import Path

from .character import CLAIRE_PROFILE, CharacterProfile
from .isolation import add_rename, alias_standard_mesh_paths
from .outfits import EXCLUSIVE_PART_IDS
from .paths import (
    assets_dir,
    ensure_dir_ci,
    folder_has_mdf,
    mesh_roots,
    natives_platform,
    resolve_ci,
)
from .reports import ConversionReport


def bundled_exclusive_mdf(exclusive_id: str) -> Path | None:
    cand = assets_dir() / "exclusive_mdf" / f"{exclusive_id}.mdf2.10"
    return cand if cand.is_file() else None


def ensure_private_exclusive_mdf(
    staging: Path,
    hair_priv: str,
    exclusive_id: str,
    rename_map: dict[str, str],
    report: ConversionReport,
    profile: CharacterProfile | None = None,
) -> bool:
    """Copy bundled exclusive .mdf2 into the private hair folder if missing.

    Exclusive kits often ship mesh + textures but no ``.mdf2``. After moving
    them off ``pl1071``/``pl1075`` (so Military/Noir stay vanilla), the hair
    redirect must load a private mdf whose scarf/hat texture paths match the
    renamed private files. Unshipped refs (hair/wetmask) stay on the exclusive
    ID and resolve from the game pak.

    Returns True if a private mdf is present afterward.
    """
    if exclusive_id not in EXCLUSIVE_PART_IDS or len(hair_priv) != 6:
        return False

    roots = mesh_roots(profile)
    player_root = (profile or CLAIRE_PROFILE).player_root
    present = False
    for root in roots:
        folder = resolve_ci(staging, f"{root}/{hair_priv}")
        if folder is not None and folder_has_mdf(folder):
            present = True

    if present:
        alias_standard_mesh_paths(
            staging, exclusive_id, hair_priv, rename_map, report,
            profile=profile)
        return True

    if natives_platform() == "stm":
        report.warnings.append(
            f"Left exclusive {exclusive_id} material as shipped: staying on "
            "ray tracing does not re-export materials."
        )
        return False

    template = bundled_exclusive_mdf(exclusive_id)
    if template is None:
        report.warnings.append(
            f"Isolated exclusive {exclusive_id} to {hair_priv} but bundled "
            f"{exclusive_id}.mdf2 is missing — hat may use vanilla textures."
        )
        return False

    written = 0
    for root in roots:
        # Only seed mesh roots that already have the private kit (or sectionroot).
        folder = resolve_ci(staging, f"{root}/{hair_priv}")
        if folder is None:
            if "streaming" in root:
                continue
            folder = ensure_dir_ci(staging, f"{root}/{hair_priv}")
        dest = folder / f"{hair_priv}.mdf2.10"
        if dest.exists():
            present = True
            continue
        shutil.copy2(template, dest)
        written += 1
        add_rename(
            rename_map,
            # Synthetic old path so patch + aliases can retarget if needed.
            f"natives/x64/sectionroot/character/player/{player_root}/"
            f"{exclusive_id}/{exclusive_id}.mdf2.10",
            dest.relative_to(staging).as_posix(),
        )
        report.rename_ops.append(
            f"bundled exclusive mdf  ->  "
            f"{dest.relative_to(staging).as_posix()}"
        )

    if written or present:
        alias_standard_mesh_paths(
            staging, exclusive_id, hair_priv, rename_map, report,
            profile=profile)
        return True
    return False
