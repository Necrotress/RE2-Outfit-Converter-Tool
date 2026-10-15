"""Background analyze / convert workers for the GUI."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

from .converter import (
    BatchItem,
    convert,
    convert_batch,
    convert_game_build,
    convert_with_ops,
)
from .outfit_ops import OutfitOp
from .packaging import input_base_name
from .reports import ConversionError
from .session import load_inputs


def analyze_paths(paths: list[Path]):
    """Load and analyze inputs. Returns (packages, errors, infos)."""
    result = load_inputs(paths)
    return result.packages, result.errors, result.infos


def convert_loaded(
    loaded,
    source_outfit,
    target_outfit,
    out_path: Path,
    *,
    outfit_display_name: str | None,
    tag_output: bool,
    tag_marker: str,
    strip_tags: list[str],
    bundle_name: str,
    mod_label: Callable,
    progress: Callable[[str], None] | None = None,
    ops: Sequence[OutfitOp] | None = None,
    write_log: bool = True,
    outfit_display_names: dict[str, str] | None = None,
    tag_modinfo_description: bool | None = None,
    tag_modinfo_name: bool = False,
    game_build: str | None = None,
    tag_build_zip_name: bool = True,
    tag_build_modinfo_description: bool = True,
    settings: dict | None = None,
):
    """Run single or batch convert. Raises ConversionError / OSError."""
    if len(loaded) == 1:
        item = loaded[0]
        if ops is not None:
            return convert_with_ops(
                item.analysis, ops, out_path,
                progress=progress,
                outfit_display_name=outfit_display_name,
                tag_output=tag_output,
                tag_marker=tag_marker,
                strip_tag_markers=strip_tags,
                source_name=input_base_name(item.source.original),
                write_log=write_log,
                outfit_display_names=outfit_display_names,
                tag_modinfo_description=tag_modinfo_description,
                tag_modinfo_name=tag_modinfo_name,
                game_build=game_build,
                tag_build_zip_name=tag_build_zip_name,
                tag_build_modinfo_description=tag_build_modinfo_description,
                settings=settings,
            )
        return convert(
            item.analysis, source_outfit, target_outfit, out_path,
            progress=progress,
            outfit_display_name=outfit_display_name,
            tag_output=tag_output,
            tag_marker=tag_marker,
            strip_tag_markers=strip_tags,
            source_name=input_base_name(item.source.original),
            write_log=write_log,
            outfit_display_names=outfit_display_names,
            tag_modinfo_description=tag_modinfo_description,
            tag_modinfo_name=tag_modinfo_name,
            game_build=game_build,
            tag_build_zip_name=tag_build_zip_name,
            tag_build_modinfo_description=tag_build_modinfo_description,
            settings=settings,
        )
    items = [
        BatchItem(
            analysis=m.analysis,
            label=mod_label(m.analysis, m.source),
        )
        for m in loaded
    ]
    return convert_batch(
        items, source_outfit, target_outfit, out_path,
        bundle_name,
        progress=progress,
        outfit_display_name=outfit_display_name,
        tag_output=tag_output,
        tag_marker=tag_marker,
        strip_tag_markers=strip_tags,
        ops=ops,
        write_log=write_log,
        outfit_display_names=outfit_display_names,
        tag_modinfo_description=tag_modinfo_description,
        tag_modinfo_name=tag_modinfo_name,
        game_build=game_build,
        tag_build_zip_name=tag_build_zip_name,
        tag_build_modinfo_description=tag_build_modinfo_description,
        settings=settings,
    )


def convert_game_builds(
    loaded,
    out_path: Path,
    *,
    game_build: str,
    bundle_name: str,
    progress: Callable[[str], None] | None = None,
    write_log: bool = True,
    tag_build_zip_name: bool = True,
    tag_build_modinfo_description: bool = True,
    settings: dict | None = None,
):
    """Platform-only convert for the Game build screen."""
    if not loaded:
        raise ConversionError("No mods loaded.")
    analyses = [item.analysis for item in loaded]
    source_name = None
    if len(loaded) == 1:
        source_name = input_base_name(loaded[0].source.original)
    return convert_game_build(
        analyses, out_path,
        game_build=game_build,
        progress=progress,
        source_name=source_name,
        bundle_name=bundle_name,
        write_log=write_log,
        tag_build_zip_name=tag_build_zip_name,
        tag_build_modinfo_description=tag_build_modinfo_description,
        settings=settings,
    )


# Re-export for callers that want typed errors.
__all__ = [
    "analyze_paths", "convert_loaded", "convert_game_builds", "ConversionError",
]
