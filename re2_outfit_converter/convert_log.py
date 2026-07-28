"""Embed convert.log inside converted Fluffy packages."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .analyzer import AnalysisResult
from .outfit_ops import OutfitOp
from .reports import BatchReport, ConversionReport

CONVERT_LOG_NAME = "convert.log"
BATCH_LOG_NAME = "convert_batch.log"


@dataclass
class ConvertLogContext:
    """Metadata for a convert.log (no absolute user paths)."""

    mod_name: str = ""
    source_basename: str = ""
    outfits: str = ""
    characters: str = ""
    addonfor: str = ""
    op_lines: list[str] = field(default_factory=list)
    as_folder: bool = False
    tag_output: bool = False
    tag_marker: str = ""
    display_name: str = ""
    military_face: str = ""
    package_name: str = ""


def source_basename(path: Path | str | None) -> str:
    """Filename or folder name only — never a full disk path."""
    if path is None:
        return ""
    p = Path(path)
    return p.name or str(p)


def context_from_analysis(
    analysis: AnalysisResult,
    ops: Sequence[OutfitOp] | list[OutfitOp],
    *,
    source_name: str | None = None,
    as_folder: bool = False,
    tag_output: bool = False,
    tag_marker: str = "",
    display_name: str | None = None,
    military_face: str = "",
    package_name: str = "",
    label: str = "",
) -> ConvertLogContext:
    outfits = ", ".join(o.name for o in analysis.claire_outfits) or "(none)"
    characters = ", ".join(sorted(analysis.characters)) or "(none)"
    op_lines: list[str] = []
    for op in ops:
        if op.target is None:
            op_lines.append(f"Delete {op.source.name}")
        else:
            op_lines.append(f"From {op.source.name} → To {op.target.name}")
    src = (source_name or "").strip()
    if not src and analysis.root is not None:
        src = source_basename(analysis.root)
    return ConvertLogContext(
        mod_name=(
            label
            or analysis.modinfo.name
            or src
            or "(unnamed)"
        ),
        source_basename=src,
        outfits=outfits,
        characters=characters,
        addonfor=(analysis.modinfo.addonfor or "").strip(),
        op_lines=op_lines,
        as_folder=as_folder,
        tag_output=tag_output,
        tag_marker=(tag_marker or "").strip(),
        display_name=(display_name or "").strip(),
        military_face=(military_face or "").strip(),
        package_name=package_name or "",
    )


def format_convert_log(
    report: ConversionReport,
    ctx: ConvertLogContext,
) -> str:
    lines: list[str] = [
        f"RE2 Outfit Converter v{__version__}  —  convert log",
        "",
        "=== Input ===",
        f"Mod name: {ctx.mod_name}",
    ]
    if ctx.source_basename:
        lines.append(f"Source: {ctx.source_basename}")
    lines.append(f"Detected outfits: {ctx.outfits}")
    lines.append(f"Characters: {ctx.characters}")
    if ctx.addonfor:
        lines.append(f"AddonFor: {ctx.addonfor}")

    lines.extend(["", "=== Operations ==="])
    if ctx.op_lines:
        lines.extend(ctx.op_lines)
    else:
        lines.append("(none)")

    lines.extend([
        "",
        "=== Options ===",
        f"Output mode: {'folder' if ctx.as_folder else 'zip'}",
        f"Tag output: {'yes' if ctx.tag_output else 'no'}"
        + (f" {ctx.tag_marker}" if ctx.tag_output and ctx.tag_marker else ""),
        f"Display name: {ctx.display_name or '(none)'}",
        f"Military face: {ctx.military_face or '(n/a)'}",
    ])

    lines.extend(["", "=== Progress ==="])
    if report.progress_log:
        lines.extend(report.progress_log)
    else:
        lines.append("(none)")

    def _section(title: str, items: list[str]) -> None:
        lines.extend(["", f"=== {title} ==="])
        if items:
            lines.extend(items)
        else:
            lines.append("(none)")

    _section("Prefab ops", report.pfb_ops)
    _section("Renames / isolation", report.rename_ops)
    _section("Removals", report.removed_ops)
    _section("Binary patches", report.patch_ops)
    _section("Warnings", report.warnings)

    lines.extend(["", "=== Output ==="])
    if ctx.package_name:
        lines.append(ctx.package_name)
    else:
        mode = "folder" if ctx.as_folder else "zip"
        lines.append(f"Fluffy-ready {mode} (includes this convert.log)")
    lines.append("")
    return "\n".join(lines)


def write_convert_log_to_staging(
    staging: Path,
    report: ConversionReport,
    ctx: ConvertLogContext,
) -> Path | None:
    """Write ``convert.log`` into staging. On failure, warn and return None."""
    path = staging / CONVERT_LOG_NAME
    try:
        path.write_text(format_convert_log(report, ctx), encoding="utf-8")
        return path
    except OSError as e:
        report.warnings.append(f"Failed to write {CONVERT_LOG_NAME}: {e}")
        return None


def format_batch_log(
    batch: BatchReport,
    *,
    item_labels: list[str],
    bundle_name: str,
) -> str:
    lines: list[str] = [
        f"RE2 Outfit Converter v{__version__}  —  batch convert log",
        "",
        f"Bundle: {bundle_name}",
        f"Packages: {len(batch.items)}",
        "",
        "=== Progress ===",
    ]
    if batch.progress_log:
        lines.extend(batch.progress_log)
    else:
        lines.append("(none)")
    lines.extend(["", "=== Packages ==="])
    for i, (label, item) in enumerate(
            zip(item_labels, batch.items), start=1):
        lines.append(f"{i}. {label}")
        if item.warnings:
            for w in item.warnings:
                lines.append(f"   warning: {w}")
    if batch.warnings:
        lines.extend(["", "=== Batch warnings ==="])
        lines.extend(batch.warnings)
    lines.append("")
    return "\n".join(lines)


def write_batch_log_to_staging(
    staging_root: Path,
    batch: BatchReport,
    *,
    item_labels: list[str],
    bundle_name: str,
) -> Path | None:
    path = staging_root / BATCH_LOG_NAME
    try:
        path.write_text(
            format_batch_log(
                batch, item_labels=item_labels, bundle_name=bundle_name),
            encoding="utf-8",
        )
        return path
    except OSError as e:
        batch.warnings.append(f"Failed to write {BATCH_LOG_NAME}: {e}")
        return None
