"""Background analyze / convert workers for the GUI."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .converter import BatchItem, convert, convert_batch
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
):
    """Run single or batch convert. Raises ConversionError / OSError."""
    if len(loaded) == 1:
        item = loaded[0]
        return convert(
            item.analysis, source_outfit, target_outfit, out_path,
            progress=progress,
            outfit_display_name=outfit_display_name,
            tag_output=tag_output,
            tag_marker=tag_marker,
            strip_tag_markers=strip_tags,
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
    )


# Re-export for callers that want typed errors.
__all__ = ["analyze_paths", "convert_loaded", "ConversionError"]
