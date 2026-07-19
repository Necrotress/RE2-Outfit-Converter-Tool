"""Conversion / batch report types and errors."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .analyzer import AnalysisResult


@dataclass
class ConversionReport:
    pfb_ops: list[str] = field(default_factory=list)
    rename_ops: list[str] = field(default_factory=list)
    patch_ops: list[str] = field(default_factory=list)
    removed_ops: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    output_zip: Path | None = None
    output_folder: Path | None = None


@dataclass
class BatchItem:
    """One queued mod for a batch conversion."""
    analysis: AnalysisResult
    label: str = ""


@dataclass
class BatchReport:
    items: list[ConversionReport] = field(default_factory=list)
    output_zip: Path | None = None
    warnings: list[str] = field(default_factory=list)


class ConversionError(Exception):
    pass


class NothingToConvertError(ConversionError):
    """Raised when a mod has no remapable assets for the source outfit."""
