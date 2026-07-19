"""Strip DLC contentsholder scenes when converting between outfits.

Elza-based mods ship ``contentsholder_dlc_costume_e.scn`` which registers
``Costume_E`` and points at Elza UI/PFB/MSG paths. Renaming loose UI to
Noir (``ui0601_01_07``) while leaving that holder makes Elza keep the
preview.

String-patching the holder to ``Costume_D`` / ``costume_d`` is worse:
path strings change, but RE Engine register hashes stay on Elza's pack,
and the renamed file overrides vanilla Noir's contentsholder — Noir
disappears from the costume menu while Elza still shows the mod art.

Safe approach: remove DLC contentsholders on convert. Loose PFBs, UI, and
MSG files are enough for the target slot; vanilla keeps the DLC unlock.
"""

from __future__ import annotations

from pathlib import Path

from .outfits import Outfit
from .reports import ConversionReport


def sync_dlc_contentsholder(
    staging: Path,
    target: Outfit,
    report: ConversionReport,
) -> None:
    """Remove DLC contentsholders so they cannot leak or break costume UI."""
    for path in staging.rglob("contentsholder_dlc*"):
        if not path.is_file():
            continue
        rel = path.relative_to(staging).as_posix()
        path.unlink(missing_ok=True)
        report.removed_ops.append(rel)
        report.warnings.append(
            f"Removed {path.name} (DLC contentsholder cannot be safely "
            f"retargeted to {target.name}; prevents broken/leaked costume UI)."
        )
