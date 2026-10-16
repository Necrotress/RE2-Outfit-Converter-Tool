"""Filesystem remaps: natives/stm → natives/x64 and RT extensions → classic."""

from __future__ import annotations

import shutil
from pathlib import Path

from .formats import (
    PLATFORM_CLASSIC,
    PLATFORM_RT,
    remap_rel_to_classic,
    remap_rel_to_rt,
)
from .reports import ConversionReport


def stm_to_x64_rename_map() -> dict[str, str]:
    """Same-length platform tokens for binary path patching.

    Prefer path-shaped needles so we do not rewrite unrelated ``stm``
    substrings inside other names.
    """
    return {
        "natives/stm": "natives/x64",
        "natives\\stm": "natives\\x64",
        "/stm/": "/x64/",
        "\\stm\\": "\\x64\\",
        # Same-length version suffixes embedded in mesh/user/scene binaries.
        ".tex.34": ".tex.10",
        ".mdf2.21": ".mdf2.10",
        ".mesh.2109108288": ".mesh.1808312334",
    }


def x64_to_stm_rename_map() -> dict[str, str]:
    """Same-length tokens for classic → RT binary path patching."""
    return {new: old for old, new in stm_to_x64_rename_map().items()}


def move_tree_to_rt(staging: Path, report: ConversionReport) -> None:
    """Move natives/x64 → natives/stm and rename classic extensions to RT."""
    _move_platform_tree(
        staging, report,
        src_platform=PLATFORM_CLASSIC,
        dst_platform=PLATFORM_RT,
        remap_rel=remap_rel_to_rt,
    )


def move_tree_to_classic(staging: Path, report: ConversionReport) -> None:
    """Move natives/stm → natives/x64 and rename RT versioned extensions."""
    _move_platform_tree(
        staging, report,
        src_platform=PLATFORM_RT,
        dst_platform=PLATFORM_CLASSIC,
        remap_rel=remap_rel_to_classic,
    )


def lowercase_stm_tree(staging: Path) -> int:
    """Rename every path component under ``natives/stm`` to lowercase.

    Fluffy invalidates the pak entry with the lowercase path from the game
    list, then copies the loose file with the archive's own spelling.
    ``natives/STM`` does not satisfy a ``natives/stm`` lookup, so the pak
    prefab stays and the body never draws. A case-only rename has to hop
    through a temporary name or Windows leaves the old spelling in place.
    """
    natives = staging / "natives"
    if not natives.is_dir():
        return 0
    stm = next(
        (
            child for child in natives.iterdir()
            if child.is_dir() and child.name.lower() == PLATFORM_RT
        ),
        None,
    )
    if stm is None:
        return 0
    count = 0
    entries = sorted(stm.rglob("*"), key=lambda path: len(path.parts), reverse=True)
    for path in entries:
        count += _rename_case_lower(path)
    count += _rename_case_lower(stm)
    return count


def _rename_case_lower(path: Path) -> int:
    lower = path.name.lower()
    if path.name == lower or not path.exists():
        return 0
    temporary = path.with_name(f"{path.name}.~case")
    path.rename(temporary)
    temporary.rename(path.with_name(lower))
    return 1


def _move_platform_tree(
    staging: Path,
    report: ConversionReport,
    *,
    src_platform: str,
    dst_platform: str,
    remap_rel,
) -> None:
    natives = staging / "natives"
    if not natives.is_dir():
        return

    src_dir = None
    for child in natives.iterdir():
        if child.is_dir() and child.name.lower() == src_platform:
            src_dir = child
            break
    if src_dir is None:
        return

    files = sorted(
        (p for p in src_dir.rglob("*") if p.is_file()),
        key=lambda p: len(p.parts),
        reverse=True,
    )
    left_behind = False
    for src in files:
        rel_src = src.relative_to(staging).as_posix()
        rel_dst = remap_rel(rel_src)
        dest = staging.joinpath(*rel_dst.split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest.resolve() != src.resolve():
            try:
                dest.unlink()
            except OSError as e:
                report.warnings.append(f"Could not replace {rel_dst}: {e}")
                left_behind = True
                continue
            report.warnings.append(f"Replaced existing {rel_dst} with {rel_src}")
        shutil.move(str(src), str(dest))
        try:
            from ..msg_name import retarget_msg_file
            retarget_msg_file(dest)
        except Exception as e:
            report.warnings.append(
                f"Could not set message version on {rel_dst}: {e}")
        if rel_src != rel_dst:
            report.converted_ops.append(f"remap {rel_src} -> {rel_dst}")

    _remove_empty_dirs(src_dir)
    if src_dir.exists() and any(p.is_file() for p in src_dir.rglob("*")):
        if left_behind:
            report.warnings.append(
                f"Left natives/{src_platform} in place because a file "
                "could not be moved"
            )
    elif src_dir.exists():
        try:
            shutil.rmtree(src_dir)
            report.removed_ops.append(f"natives/{src_platform}")
        except OSError as e:
            report.warnings.append(f"Could not remove natives/{src_platform}: {e}")

    for child in list(natives.iterdir()):
        if child.is_dir() and child.name.lower() == dst_platform:
            if child.name != dst_platform:
                target = natives / dst_platform
                if not target.exists():
                    child.rename(target)


def _remove_empty_dirs(root: Path) -> None:
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass
