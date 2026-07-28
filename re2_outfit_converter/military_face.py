"""Default face mode: dirty (leave target look), clean (Claire face), or mod face."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Sequence

from .analyzer import AnalysisResult
from .outfits import Outfit
from .paths import assets_dir, ensure_dir_ci
from .reports import ConversionReport

# User / CLI values
FACE_DIRTY = "dirty"
FACE_CLEAN = "clean"
FACE_MOD = "mod"  # locked when the mod already ships face data

FACE_MODE_LABELS = {
    FACE_DIRTY: "Outfit face",
    FACE_CLEAN: "Default face",
    FACE_MOD: "Using mod's face data",
}

_CLEAN_TEMPLATE = "military_face_clean"
# Clean Claire face textures live on the Military dirty-face path (pl1050_04).
# Seeding them into any convert replaces that dirty look with Claire's default.
_CLEAN_DEST = {
    "sectionroot": (
        "natives/x64/sectionroot/character/player/pl1000/pl1050/pl1050_04"
    ),
    "streaming": (
        "natives/x64/streaming/sectionroot/character/player/pl1000/"
        "pl1050/pl1050_04"
    ),
}


def analysis_has_face_rewrite(
    analysis: AnalysisResult,
    sources: Sequence[Outfit] | None = None,
) -> bool:
    """True if the mod owns face data that should lock the default-face option.

    Locks when the mod ships a Claire face PFB or the Military dirty-face set
    (``pl1050_04``). Loose ``pl1050_01/02/03`` textures alone do not count.
    """
    _ = sources
    if any(p.part == "face" for p in analysis.claire_pfbs):
        return True
    for rel in analysis.natives_files:
        low = rel.lower().replace("\\", "/")
        if "/pl1050/pl1050_04/" in low or "/pl1050/pl1050_04." in low:
            return True
    return False


def resolve_military_face_mode(
    target: Outfit,
    analysis: AnalysisResult,
    sources: Sequence[Outfit],
    requested: str | None,
) -> str:
    """Return the effective face mode for this convert (any target outfit)."""
    _ = target
    if analysis_has_face_rewrite(analysis, sources):
        return FACE_MOD
    mode = (requested or FACE_DIRTY).strip().lower()
    if mode not in (FACE_DIRTY, FACE_CLEAN):
        return FACE_DIRTY
    return mode


def apply_military_face_mode(
    staging: Path,
    target: Outfit,
    mode: str,
    report: ConversionReport,
) -> None:
    """Apply clean-face texture overrides when requested (any convert target)."""
    if mode != FACE_CLEAN:
        if mode == FACE_MOD:
            report.rename_ops.append(
                "face: kept mod face data (default-face option ignored)"
            )
        elif target.key == "military":
            report.rename_ops.append(
                "face: dirty (vanilla Military pl1050_04)"
            )
        else:
            report.rename_ops.append(
                f"face: left {target.name} face look unchanged"
            )
        return

    template = assets_dir() / _CLEAN_TEMPLATE
    if not template.is_dir():
        report.warnings.append(
            "Default face requested but bundled template is missing "
            f"({_CLEAN_TEMPLATE})."
        )
        return

    wrote = 0
    for key, dest_rel in _CLEAN_DEST.items():
        src_dir = template / key
        if not src_dir.is_dir():
            continue
        dest_dir = ensure_dir_ci(staging, dest_rel)
        for src in sorted(src_dir.iterdir()):
            if not src.is_file():
                continue
            dest = dest_dir / src.name
            shutil.copy2(src, dest)
            wrote += 1
            report.rename_ops.append(
                f"default face clean: {src.name}  ->  "
                f"{dest.relative_to(staging).as_posix()}"
            )

    if wrote <= 0:
        report.warnings.append(
            "Default face requested but no template textures were found."
        )
