"""Mod packages nested inside another package."""

from __future__ import annotations

from pathlib import Path


def find_mod_roots(folder: Path) -> list[Path]:
    with_ini: list[Path] = []
    for ini in folder.rglob("modinfo.ini"):
        root = ini.parent
        if (root / "natives").is_dir():
            with_ini.append(root)
    if with_ini:
        return _unique_roots(with_ini)
    natives_roots: list[Path] = []
    for natives in folder.rglob("natives"):
        if natives.is_dir():
            natives_roots.append(natives.parent)
    return _dedupe_mod_roots(natives_roots)


def nested_package_dirs(root: Path) -> list[Path]:
    """Packages inside ``root`` that are converted on their own."""
    base = root.resolve()
    return [item for item in find_mod_roots(root) if item.resolve() != base]


def _unique_roots(roots: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    kept: list[Path] = []
    for root in roots:
        key = root.resolve()
        if key in seen:
            continue
        seen.add(key)
        kept.append(root)
    return kept


def _dedupe_mod_roots(roots: list[Path]) -> list[Path]:
    resolved = sorted({r.resolve() for r in roots}, key=lambda p: len(p.parts))
    kept: list[Path] = []
    for root in resolved:
        if any(_is_relative_to(root, item) for item in kept):
            continue
        kept.append(root)
    return kept


def _is_relative_to(path: Path, other: Path) -> bool:
    try:
        path.relative_to(other)
        return path != other
    except ValueError:
        return False
