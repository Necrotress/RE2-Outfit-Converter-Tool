"""Claire DLC figure-gallery isolation on convert.

Elza/Noir/Military/'98 each have an extra figure entry::

    natives/x64/objectroot/scene/ui/figure/extra/figurescene_pl1000_{NN}.scn…
    natives/x64/objectroot/prefab/ui/figure/extra/figure_pl1000_{NN}.pfb…

Author figure scenes are often shared Claire mannequin clones. Renaming them
onto the target frame (e.g. Elza 12 → Noir 11) caused cross-outfit bleed in
the Records model viewer. Convert instead **strips** all Claire extra figure
files so each outfit's vanilla in-game viewer loads only that outfit's
remapped body mesh (same pattern as mesh-only Elza packs).
"""

from __future__ import annotations

import re
from pathlib import Path

from .paths import resolve_ci
from .reports import ConversionReport

_FIGURE_SCENE_RE = re.compile(
    r"^(figurescene_pl1000_)(\d{2})(\.scn(?:\.\d+)?)$",
    re.IGNORECASE,
)
_FIGURE_PFB_RE = re.compile(
    r"^(figure_pl1000_)(\d{2})(\.pfb(?:\.\d+)?)$",
    re.IGNORECASE,
)

_FIGURE_ROOTS = (
    "natives/x64/objectroot/scene/ui/figure/extra",
    "natives/x64/objectroot/prefab/ui/figure/extra",
)

# Military=10, Noir=11, Elza=12, '98=13
CLAIRE_EXTRA_FIGURE_IDS = frozenset({"10", "11", "12", "13"})

_BLEED_NOTE = (
    "Removed author figure gallery file(s); Records viewer uses the game's "
    "vanilla scene for the target outfit + remapped body mesh "
    "(prevents cross-outfit model-viewer bleed)."
)


def strip_claire_extra_figures(
    staging: Path,
    report: ConversionReport,
    *,
    reason: str | None = None,
) -> int:
    """Delete every Claire DLC extra figure scene/prefab (ids 10–13).

    Returns how many files were removed.
    """
    removed = 0
    note = reason or _BLEED_NOTE
    for root in _FIGURE_ROOTS:
        root_dir = resolve_ci(staging, root)
        if root_dir is None or not root_dir.is_dir():
            continue
        for path in list(root_dir.iterdir()):
            if not path.is_file():
                continue
            m = _FIGURE_SCENE_RE.match(path.name) or _FIGURE_PFB_RE.match(
                path.name)
            if m is None or m.group(2) not in CLAIRE_EXTRA_FIGURE_IDS:
                continue
            rel = path.relative_to(staging).as_posix()
            path.unlink(missing_ok=True)
            report.removed_ops.append(rel)
            removed += 1
    if removed:
        report.warnings.append(note)
    return removed
