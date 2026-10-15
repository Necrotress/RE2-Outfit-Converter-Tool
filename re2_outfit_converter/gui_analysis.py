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


def _primary_character_name(characters: dict[str, int]) -> str | None:
    if "Claire" in characters and "Leon" not in characters:
        return "Claire"
    if "Leon" in characters and "Claire" not in characters:
        return "Leon"
    if "Claire" in characters:
        return "Claire"
    if "Leon" in characters:
        return "Leon"
    return None


def _other_character_note(characters: dict[str, int]) -> str:
    """Short note when the pack also has content outside the primary character."""
    primary = _primary_character_name(characters)
    others = sorted(
        name for name in characters
        if primary is None or name != primary
    )
    if not others:
        return ""
    return "also has " + ", ".join(others)


def format_characters(analysis: AnalysisResult) -> str:
    """Legacy helper — prefer outfit-row notes for the GUI."""
    primary = _primary_character_name(analysis.characters)
    note = _other_character_note(analysis.characters)
    if primary and not note:
        return f"{primary} only"
    if primary and note:
        return f"{primary} · {note}"
    return note or "Claire only"


def _analysis_outfits(analysis: AnalysisResult):
    return analysis.outfits or analysis.claire_outfits


def affected_names(characters: dict[str, int]) -> list[str]:
    """Who a pack changes when it is not a Claire or Leon outfit."""
    return sorted(
        name for name in characters if name not in ("Claire", "Leon"))


def is_game_build_load(analyses) -> bool:
    """True when every loaded pack is outside the Claire and Leon outfit rows."""
    items = list(analyses)
    if not items:
        return False
    for analysis in items:
        if _analysis_outfits(analysis):
            return False
        if (
            analysis.modinfo.addonfor
            or analysis.has_claire_files
            or analysis.has_leon_files
        ):
            return False
    return True


def format_outfit_row(analysis: AnalysisResult) -> tuple[str, bool]:
    """Return (outfit_text, ok_color) — short names for end users."""
    outfits = _analysis_outfits(analysis)
    names = [o.name for o in outfits]
    primary = _primary_character_name(analysis.characters) or "Claire"
    if names:
        outfit_text = ", ".join(names)
        outfit_ok = True
    elif analysis.modinfo.addonfor:
        outfit_text = (
            f"Addon for {analysis.modinfo.addonfor} "
            "(load with the main mod)"
        )
        outfit_ok = True
    elif analysis.has_claire_files or analysis.has_leon_files:
        outfit_text = (
            f"{primary} face/hair addon (load with a main outfit mod)"
        )
        outfit_ok = True
    else:
        affected = affected_names(analysis.characters)
        if affected:
            outfit_text = ", ".join(affected)
            outfit_ok = True
        else:
            outfit_text = f"No {primary} outfit detected"
            outfit_ok = False

    note = _other_character_note(analysis.characters)
    if note and names:
        outfit_text = f"{outfit_text}  ·  {note}"
    return outfit_text, outfit_ok


def format_multi_characters(loaded) -> str:
    char_counts: dict[str, int] = {}
    for m in loaded:
        for name, count in m.analysis.characters.items():
            char_counts[name] = char_counts.get(name, 0) + count
    primary = _primary_character_name(char_counts)
    note = _other_character_note(char_counts)
    if primary and not note:
        return f"{primary} only"
    if primary and note:
        return f"{primary} · {note}"
    return note or "Claire only"


def format_multi_outfit_row(loaded) -> tuple[str, bool]:
    """Short outfit list across a multi-mod load."""
    names: list[str] = []
    seen: set[str] = set()
    for m in loaded:
        for o in _analysis_outfits(m.analysis):
            if o.name not in seen:
                names.append(o.name)
                seen.add(o.name)
    passthrough = sum(
        1 for m in loaded if not _analysis_outfits(m.analysis))
    if names:
        text = ", ".join(names)
        ok = True
        if passthrough:
            text += f"  ·  {passthrough} addon(s) with no outfit remap"
    else:
        affected: list[str] = []
        seen_affected: set[str] = set()
        for m in loaded:
            for name in affected_names(m.analysis.characters):
                if name not in seen_affected:
                    affected.append(name)
                    seen_affected.add(name)
        if affected:
            text = ", ".join(sorted(affected))
            ok = True
        else:
            text = "None detected"
            ok = False

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
