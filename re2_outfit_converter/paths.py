"""Shared filesystem / asset path helpers for conversion."""

from __future__ import annotations

import re
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from .character import CLAIRE_PROFILE, CharacterProfile

# Claire defaults kept for callers that have not been profile-wired yet.
PARTS_DIR = CLAIRE_PROFILE.parts_dir
MESH_ROOTS = CLAIRE_PROFILE.mesh_roots
PFB_EXT_RE = re.compile(r"(\.pfb(?:\.\d+)?)$", re.IGNORECASE)
_X64 = "natives/x64/"
# A stay-on-ray-tracing convert reads and writes stm. Classic stays x64.
_NATIVES_PLATFORM: ContextVar[str] = ContextVar(
    "re2oc_natives_platform", default="x64",
)


def natives_platform() -> str:
    return _NATIVES_PLATFORM.get()


@contextmanager
def use_natives_platform(platform: str):
    """Point outfit-stage path lookups at ``natives/x64`` or ``natives/stm``."""
    token = _NATIVES_PLATFORM.set(platform)
    try:
        yield
    finally:
        _NATIVES_PLATFORM.reset(token)


def locate(rel: str) -> str:
    """Rewrite a classic ``natives/x64`` relative path for the active platform."""
    platform = _NATIVES_PLATFORM.get()
    text = rel.replace("\\", "/")
    if platform == "x64" or not text.lower().startswith(_X64):
        return text
    return f"natives/{platform}/" + text[len(_X64):]


def parts_dir(profile: CharacterProfile | None = None) -> str:
    return locate((profile or CLAIRE_PROFILE).parts_dir)


def mesh_roots(profile: CharacterProfile | None = None) -> tuple[str, ...]:
    return tuple(locate(root) for root in (profile or CLAIRE_PROFILE).mesh_roots)


def assets_dir() -> Path:
    """Bundled converter assets (dev tree or frozen PyInstaller bundle)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "re2_outfit_converter" / "assets"
    return Path(__file__).resolve().parent / "assets"


def resolve_ci(base: Path, rel: str) -> Path | None:
    """Walk ``rel`` under ``base`` case-insensitively; return None if missing."""
    rel = locate(rel)
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
    rel = locate(rel)
    existing = resolve_ci(base, rel)
    if existing is not None:
        return existing
    dest = base.joinpath(*rel.split("/"))
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def engine_path(rel: str) -> str | None:
    """natives/x64/.../file.mesh.1808312334 -> sectionroot/.../file.mesh"""
    low = rel.replace("\\", "/")
    lower = low.lower()
    prefix = next(
        (item for item in ("natives/x64/", "natives/stm/") if lower.startswith(item)),
        None,
    )
    if prefix is None:
        return None
    path = low[len(prefix):]
    dirname, _, fname = path.rpartition("/")
    segs = fname.split(".")
    if len(segs) >= 3 and segs[-1].isdigit():
        fname = ".".join(segs[:-1])
    return f"{dirname}/{fname}" if dirname else fname


def engine_dir(rel: str) -> str | None:
    """natives/x64/.../pl1005 -> sectionroot/.../pl1005.

    Texture paths inside an MDF use this directory. An addon that only
    ships the MDF still has to follow the body folder rename.
    """
    eng = engine_path(rel.rstrip("/") + "/_.mesh.1")
    if not eng or "/" not in eng:
        return None
    return eng.rsplit("/", 1)[0]


def folder_has_mdf(folder: Path | None) -> bool:
    if folder is None or not folder.is_dir():
        return False
    return any(
        p.is_file() and ".mdf2" in p.name.lower()
        for p in folder.rglob("*")
    )
