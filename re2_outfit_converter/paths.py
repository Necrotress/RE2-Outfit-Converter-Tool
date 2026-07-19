"""Shared filesystem / asset path helpers for conversion."""

from __future__ import annotations

import re
import sys
from pathlib import Path

PARTS_DIR = "natives/x64/objectroot/prefab/character/survivor/parts/pl1000"
MESH_ROOTS = (
    "natives/x64/sectionroot/character/player/pl1000",
    "natives/x64/streaming/sectionroot/character/player/pl1000",
)
PFB_EXT_RE = re.compile(r"(\.pfb(?:\.\d+)?)$", re.IGNORECASE)


def assets_dir() -> Path:
    """Bundled converter assets (dev tree or frozen PyInstaller bundle)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "re2_outfit_converter" / "assets"
    return Path(__file__).resolve().parent / "assets"


def resolve_ci(base: Path, rel: str) -> Path | None:
    """Walk ``rel`` under ``base`` case-insensitively; return None if missing."""
    current = base
    for seg in rel.split("/"):
        if not current.is_dir():
            return None
        match = next(
            (c for c in current.iterdir() if c.name.lower() == seg.lower()),
            None,
        )
        if match is None:
            return None
        current = match
    return current


def ensure_dir_ci(base: Path, rel: str) -> Path:
    """Return ``base/rel``, creating parents; reuse existing case-insensitive path."""
    existing = resolve_ci(base, rel)
    if existing is not None:
        return existing
    dest = base.joinpath(*rel.split("/"))
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def engine_path(rel: str) -> str | None:
    """natives/x64/.../file.mesh.1808312334 -> sectionroot/.../file.mesh"""
    if not rel.lower().startswith("natives/x64/"):
        return None
    path = rel[len("natives/x64/"):]
    dirname, _, fname = path.rpartition("/")
    segs = fname.split(".")
    if len(segs) >= 3 and segs[-1].isdigit():
        fname = ".".join(segs[:-1])
    return f"{dirname}/{fname}" if dirname else fname
