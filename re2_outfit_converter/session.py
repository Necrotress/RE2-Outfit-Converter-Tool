"""Shared load path for GUI and CLI: open inputs, analyze, link AddonFor."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .analyzer import AnalysisResult, analyze, find_mod_roots
from .archive import ExtractError, ModSource


@dataclass
class LoadedPackage:
    """One analyzed Fluffy package (may share a ModSource with siblings)."""

    source: ModSource
    analysis: AnalysisResult
    label: str = ""


@dataclass
class LoadResult:
    packages: list[LoadedPackage] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    infos: list[str] = field(default_factory=list)


def package_label(analysis: AnalysisResult, source: ModSource) -> str:
    return analysis.modinfo.name or source.original.name


def link_orphan_addons(
    analyses: list[AnalysisResult],
    *,
    warn: bool = False,
) -> None:
    """Fill missing AddonFor so face/hair addons share the main mod's IDs.

    Used by GUI load, batch convert, and CLI. Mutates ``analysis.modinfo``.
    """
    if len(analyses) < 2:
        return
    main_seed = ""
    for analysis in analyses:
        if not analysis.claire_outfits:
            continue
        mi = analysis.modinfo
        main_seed = (mi.nameasbundle or mi.name or "").strip()
        if main_seed:
            break
    if not main_seed:
        return
    for analysis in analyses:
        if analysis.claire_outfits or analysis.modinfo.addonfor:
            continue
        if not analysis.has_claire_files:
            continue
        analysis.modinfo.addonfor = main_seed
        if warn:
            analysis.warnings.append(
                f"Treating as AddonFor '{main_seed}' "
                "(no AddonFor in modinfo; linked for face/hair isolation)."
            )


def load_inputs(
    paths: list[Path],
    *,
    skip_non_claire_in_batch: bool = True,
) -> LoadResult:
    """Open folders/archives, find mod roots, analyze, link orphan addons.

    Callers own cleanup: close each unique ``ModSource`` when done
    (``close_loaded`` helper).
    """
    result = LoadResult()
    multi = len(paths) > 1

    for path in paths:
        path = Path(path)
        try:
            source = ModSource(path)
        except ExtractError as e:
            result.errors.append(f"{path.name}: {e}")
            continue
        except Exception as e:
            result.errors.append(f"{path.name}: {e}")
            continue

        unpacked = [
            n for n in source.nested_notes
            if n.startswith("Unpacked nested archive:")
        ]
        if unpacked:
            result.infos.append(
                f"{path.name}: unpacked {len(unpacked)} nested "
                f"archive(s) inside."
            )
        for note in source.nested_notes:
            if not note.startswith("Unpacked nested archive:"):
                result.errors.append(f"{path.name}: {note}")

        roots = find_mod_roots(source.folder)
        if not roots:
            source.close()
            result.errors.append(
                f"{path.name}: No 'natives' folder found - this doesn't "
                "look like a Fluffy Mod Manager mod"
                + (" (nested archives were unpacked, but none "
                   "contained a mod)." if unpacked else ".")
            )
            continue

        added = 0
        for root in roots:
            try:
                analysis = analyze(root)
            except Exception as e:
                result.errors.append(f"{path.name}: {e}")
                continue
            if analysis.error:
                label = root.name if root.name else path.name
                result.errors.append(f"{label}: {analysis.error}")
                continue
            if (
                skip_non_claire_in_batch
                and not analysis.claire_outfits
                and not analysis.is_passthrough_candidate
                and (multi or len(roots) > 1)
            ):
                label = analysis.modinfo.name or root.name or path.name
                result.errors.append(
                    f"{label}: skipped (no Claire outfit / AddonFor)")
                continue
            result.packages.append(LoadedPackage(
                source=source,
                analysis=analysis,
                label=package_label(analysis, source),
            ))
            added += 1

        if added == 0:
            source.close()

    link_orphan_addons(
        [p.analysis for p in result.packages],
        warn=True,
    )
    return result


def close_loaded(packages: list[LoadedPackage]) -> None:
    """Close unique ModSource objects (multi-root packages share one source)."""
    seen: set[int] = set()
    for pkg in packages:
        sid = id(pkg.source)
        if sid in seen:
            continue
        seen.add(sid)
        pkg.source.close()
