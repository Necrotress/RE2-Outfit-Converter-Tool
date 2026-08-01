"""Analysis panel text helpers for the GUI."""

from __future__ import annotations

from .analyzer import AnalysisResult
from .archive import ModSource
from .session import package_label as mod_label


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


def _other_character_note(characters: dict[str, int]) -> str:
    """Short note when the pack also has non-Claire content."""
    others = sorted(name for name in characters if name != "Claire")
    if not others:
        return ""
    return "also has " + ", ".join(others)


def format_characters(analysis: AnalysisResult) -> str:
    """Legacy helper — prefer outfit-row notes for the GUI."""
    return _other_character_note(analysis.characters) or "Claire only"


def format_outfit_row(analysis: AnalysisResult) -> tuple[str, bool]:
    """Return (outfit_text, ok_color) — short names for end users."""
    names = [o.name for o in analysis.claire_outfits]
    if names:
        outfit_text = ", ".join(names)
        outfit_ok = True
    elif analysis.modinfo.addonfor:
        outfit_text = (
            f"Addon for {analysis.modinfo.addonfor} "
            "(load with the main mod)"
        )
        outfit_ok = True
    elif analysis.has_claire_files:
        outfit_text = "Claire face/hair addon (load with a main outfit mod)"
        outfit_ok = True
    else:
        outfit_text = "No Claire outfit detected"
        outfit_ok = False

    note = _other_character_note(analysis.characters)
    if note and names:
        outfit_text = f"{outfit_text}  ·  {note}"
    elif note and not names and outfit_ok:
        outfit_text = f"{outfit_text}  ·  {note}"
    return outfit_text, outfit_ok


def format_multi_characters(loaded) -> str:
    char_counts: dict[str, int] = {}
    for m in loaded:
        for name, count in m.analysis.characters.items():
            char_counts[name] = char_counts.get(name, 0) + count
    return _other_character_note(char_counts) or "Claire only"


def format_multi_outfit_row(loaded) -> tuple[str, bool]:
    """Short outfit list across a multi-mod load."""
    names: list[str] = []
    seen: set[str] = set()
    for m in loaded:
        for o in m.analysis.claire_outfits:
            if o.name not in seen:
                names.append(o.name)
                seen.add(o.name)
    passthrough = sum(1 for m in loaded if not m.analysis.claire_outfits)
    if names:
        text = ", ".join(names)
        ok = True
    else:
        text = "None detected"
        ok = False
    if passthrough:
        text += f"  ·  {passthrough} addon(s) with no outfit remap"

    char_counts: dict[str, int] = {}
    for m in loaded:
        for name, count in m.analysis.characters.items():
            char_counts[name] = char_counts.get(name, 0) + count
    note = _other_character_note(char_counts)
    if note and names:
        text = f"{text}  ·  {note}"
    return text, ok


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
