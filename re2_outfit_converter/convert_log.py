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
        package_name=package_name or "",
    )


def _name_summaries(report: ConversionReport, ctx: ConvertLogContext) -> list[str]:
    """Short Name: lines for Operations when an in-game name was written."""
    names: list[str] = []
    seen: set[str] = set()

    def _add(label: str) -> None:
        text = label.strip()
        if not text or text in seen:
            return
        seen.add(text)
        names.append(f"Name: {text}")

    if ctx.display_name:
        _add(repr(ctx.display_name))

    for line in report.rename_ops:
        if not line.startswith("set in-game outfit name"):
            continue
        # "...: 'Display'" or '...: "Display"'
        if ": " in line:
            tail = line.rsplit(": ", 1)[-1].strip()
            if (tail.startswith("'") and tail.endswith("'")) or (
                    tail.startswith('"') and tail.endswith('"')):
                _add(tail)
            elif tail:
                _add(repr(tail))
    return names


def _face_summaries(report: ConversionReport) -> list[str]:
    """Short Face: lines when face mesh IDs were isolated."""
    out: list[str] = []
    for line in report.rename_ops:
        if line.startswith("isolated face "):
            out.append(f"Face: {line.removeprefix('isolated face ').strip()}")
    return out


def _military_face_summaries(report: ConversionReport) -> list[str]:
    """Short Default face: lines when auto-seed / Tank Top strip ran."""
    out: list[str] = []
    for line in report.rename_ops:
        if line.startswith("face: seeded Claire default face for "):
            name = line.removeprefix(
                "face: seeded Claire default face for ").split(" (", 1)[0]
            out.append(f"Default face ({name}): seeded Claire default")
        elif line.startswith("face: stripped Military *_04 face textures"):
            out.append("Default face (Tank Top): stripped Military face textures")
        elif line.startswith("face: kept mod face data"):
            out.append("Default face: kept mod face data")
    if not out and any(" clean face:" in line for line in report.rename_ops):
        out.append("Default face: seeded Claire default")
    return out


def operation_extra_lines(
    report: ConversionReport,
    ctx: ConvertLogContext,
) -> list[str]:
    """Name / face / Military one-liners for the Operations section."""
    return (
        _name_summaries(report, ctx)
        + _face_summaries(report)
        + _military_face_summaries(report)
    )


_CHANGE_KINDS: tuple[tuple[str, str], ...] = (
    # (singular label used as line prefix, plural noun for empty footer)
    ("prefab", "prefab"),
    ("rename", "rename"),
    ("removal", "removal"),
    ("patch", "patch"),
)


def all_change_buckets(
    report: ConversionReport,
) -> list[tuple[str, list[str]]]:
    """All change groups (including empty) in pipeline order."""
    by_label = {
        "prefab": list(report.pfb_ops),
        "rename": list(report.rename_ops),
        "removal": list(report.removed_ops),
        "patch": list(report.patch_ops),
    }
    return [(label, by_label[label]) for label, _ in _CHANGE_KINDS]


def change_buckets(
    report: ConversionReport,
) -> list[tuple[str, list[str]]]:
    """Non-empty change groups: (singular label, lines) in pipeline order."""
    return [(label, items) for label, items in all_change_buckets(report) if items]


def format_changes_heading(buckets: list[tuple[str, list[str]]]) -> str:
    """e.g. 'Changes (42 — 5 prefabs, 30 renames, 3 removals, 4 patches)'."""
    total = sum(len(items) for _, items in buckets)
    parts: list[str] = []
    for label, items in buckets:
        n = len(items)
        noun = label if n == 1 else (
            "removals" if label == "removal" else f"{label}s"
        )
        parts.append(f"{n} {noun}")
    detail = ", ".join(parts)
    return f"=== Changes ({total} — {detail}) ==="


def _empty_noun(label: str) -> str:
    """Noun used in 'No … changes' footers."""
    return {
        "prefab": "prefab",
        "rename": "rename",
        "removal": "removal",
        "patch": "patch",
    }[label]


def format_empty_changes_note(empty_labels: list[str]) -> str:
    """Footer when some (or all) change categories had nothing.

    Examples:
    - all empty → 'No file changes.'
    - prefab + removal → 'No prefab or removal changes.'
    - three+ → 'No prefab, removal, or patch changes.'
    """
    if not empty_labels:
        return ""
    if len(empty_labels) == len(_CHANGE_KINDS):
        return "No file changes."
    nouns = [_empty_noun(label) for label in empty_labels]
    if len(nouns) == 1:
        return f"No {nouns[0]} changes."
    if len(nouns) == 2:
        return f"No {nouns[0]} or {nouns[1]} changes."
    return f"No {', '.join(nouns[:-1])}, or {nouns[-1]} changes."


def format_convert_log(
    report: ConversionReport,
    ctx: ConvertLogContext,
    *,
    include_title: bool = True,
) -> str:
    lines: list[str] = []
    if include_title:
        lines.extend([
            f"RE2 Outfit Converter v{__version__}  —  convert log",
            "",
        ])

    input_lines = [
        f"Mod name: {ctx.mod_name}",
        f"Detected outfits: {ctx.outfits}",
        f"Characters: {ctx.characters}",
    ]
    if ctx.addonfor:
        input_lines.append(f"AddonFor: {ctx.addonfor}")
    lines.extend(["=== Input ===", *input_lines])

    extras = operation_extra_lines(report, ctx)
    if ctx.op_lines or extras:
        lines.extend(["", "=== Operations ==="])
        if ctx.op_lines:
            lines.extend(ctx.op_lines)
        else:
            lines.append("(none)")
        lines.extend(extras)

    all_buckets = all_change_buckets(report)
    filled = [(label, items) for label, items in all_buckets if items]
    empty_labels = [label for label, items in all_buckets if not items]
    lines.append("")
    if filled:
        lines.append(format_changes_heading(filled))
        for label, items in filled:
            for item in items:
                lines.append(f"{label}: {item}")
        if empty_labels:
            lines.append("")
            lines.append(format_empty_changes_note(empty_labels))
    else:
        lines.append(format_empty_changes_note(empty_labels))

    if report.warnings:
        lines.extend(["", "=== Warnings ===", *report.warnings])

    lines.extend(["", "=== Output ==="])
    if ctx.package_name:
        lines.append(ctx.package_name)
    else:
        mode = "folder" if ctx.as_folder else "zip"
        lines.append(f"Fluffy-ready {mode} (includes this convert.log)")
    lines.append("")
    return "\n".join(lines)


def _write_log_file(
    path: Path,
    text: str,
    warnings: list[str],
) -> Path | None:
    try:
        path.write_text(text, encoding="utf-8")
        return path
    except OSError as e:
        warnings.append(f"Failed to write {CONVERT_LOG_NAME}: {e}")
        return None


def write_convert_log_to_staging(
    staging: Path,
    report: ConversionReport,
    ctx: ConvertLogContext,
) -> Path | None:
    """Write ``convert.log`` into staging. On failure, warn and return None."""
    return _write_log_file(
        staging / CONVERT_LOG_NAME,
        format_convert_log(report, ctx),
        report.warnings,
    )


def format_batch_convert_log(
    batch: BatchReport,
    *,
    folder_names: list[str],
    item_contexts: list[ConvertLogContext],
    bundle_name: str,
) -> str:
    """Full per-package convert details aggregated into one root convert.log."""
    lines: list[str] = [
        f"RE2 Outfit Converter v{__version__}  —  convert log",
        "",
        "=== Bundle ===",
        f"Name: {bundle_name}",
        f"Packages: {len(batch.items)}",
        "",
    ]
    for folder_name, item, ctx in zip(
            folder_names, batch.items, item_contexts, strict=True):
        lines.extend([
            "#" * 80,
            f"# Package: {folder_name}",
            "#" * 80,
            "",
            format_convert_log(item, ctx, include_title=False).rstrip(),
            "",
        ])
    if batch.warnings:
        lines.extend(["=== Batch warnings ===", *batch.warnings, ""])
    return "\n".join(lines)


def write_batch_log_to_staging(
    staging_root: Path,
    batch: BatchReport,
    *,
    folder_names: list[str],
    item_contexts: list[ConvertLogContext],
    bundle_name: str,
) -> Path | None:
    """Write one aggregated ``convert.log`` at the multi-mod zip root."""
    return _write_log_file(
        staging_root / CONVERT_LOG_NAME,
        format_batch_convert_log(
            batch,
            folder_names=folder_names,
            item_contexts=item_contexts,
            bundle_name=bundle_name,
        ),
        batch.warnings,
    )
