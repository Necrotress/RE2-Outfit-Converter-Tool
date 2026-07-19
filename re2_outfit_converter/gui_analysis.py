"""Analysis panel text helpers for the GUI."""

from __future__ import annotations

from .analyzer import AnalysisResult
from .archive import ModSource


def mod_label(analysis: AnalysisResult, source: ModSource) -> str:
    return analysis.modinfo.name or source.original.name


def format_mod_row(analysis: AnalysisResult, source: ModSource) -> str:
    mi = analysis.modinfo
    mod_desc = mod_label(analysis, source)
    extras = []
    if mi.version:
        extras.append(f"v{mi.version}")
    if mi.author:
        extras.append(f"by {mi.author}")
    if mi.addonfor:
        extras.append(f"AddonFor: {mi.addonfor}")
    return mod_desc + (f"   ({' · '.join(extras)})" if extras else "")


def format_characters(analysis: AnalysisResult) -> str:
    chars = ", ".join(
        f"{name} ({count} files)"
        for name, count in sorted(analysis.characters.items()))
    return chars or "None detected"


def format_outfit_row(analysis: AnalysisResult) -> tuple[str, bool]:
    """Return (outfit_text, ok_color)."""
    outfit_bits = []
    for o in analysis.claire_outfits:
        slots = sorted({p.slot for p in analysis.claire_pfbs
                        if p.slot in o.all_slots})
        detail = []
        if slots:
            detail.append("PFB slots: " + ", ".join(slots))
        if o.body_id in analysis.claire_body_ids:
            detail.append(f"mesh {o.body_id}")
        outfit_bits.append(
            f"{o.name}" + (f"  [{'; '.join(detail)}]" if detail else ""))
    if outfit_bits:
        outfit_text = "\n".join(outfit_bits)
        outfit_ok = True
    elif analysis.modinfo.addonfor:
        outfit_text = (
            f"Addon for {analysis.modinfo.addonfor} "
            "(no body remap — batch with the main mod to convert)")
        outfit_ok = True
    elif analysis.has_claire_files:
        outfit_text = (
            "Claire face/hair addon (no outfit remap — "
            "batch with a main outfit mod to convert)")
        outfit_ok = True
    else:
        outfit_text = "No Claire outfit detected"
        outfit_ok = False
    if analysis.warnings:
        outfit_text += "\n" + "\n".join(
            f"! {w}" for w in analysis.warnings[:6])
    return outfit_text, outfit_ok


def format_multi_characters(loaded) -> str:
    char_counts: dict[str, int] = {}
    for m in loaded:
        for name, count in m.analysis.characters.items():
            char_counts[name] = char_counts.get(name, 0) + count
    chars = ", ".join(
        f"{name} ({count} files)"
        for name, count in sorted(char_counts.items()))
    return chars or "None detected"


def collect_warnings(report) -> tuple[object | None, list[str]]:
    """Extract output path and flattened warnings from a convert report."""
    from .reports import BatchReport, ConversionReport

    warnings: list[str] = []
    out = None
    if isinstance(report, BatchReport):
        out = report.output_zip
        warnings = list(report.warnings)
        for item in report.items:
            warnings.extend(item.warnings)
    elif isinstance(report, ConversionReport):
        out = report.output_zip or report.output_folder
        warnings = list(report.warnings)
    return out, warnings


def count_patch_skips(warnings: list[str]) -> int:
    return sum(
        1 for w in warnings
        if "path patch" in w.lower()
        or ("skipped" in w.lower() and "patch" in w.lower())
        or "length mismatch" in w.lower()
        or "too large" in w.lower()
    )
