"""Conversion report types and errors."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ConversionReport:
    converted_ops: list[str] = field(default_factory=list)
    passthrough_ops: list[str] = field(default_factory=list)
    removed_ops: list[str] = field(default_factory=list)
    failed_ops: list[str] = field(default_factory=list)
    patch_ops: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    mode: str = ""  # "dual_pack_strip" | "full_convert"
    output_zip: Path | None = None
    output_folder: Path | None = None

    @property
    def ok(self) -> bool:
        return not self.failed_ops


class ConversionError(Exception):
    pass


class FormatConversionError(ConversionError):
    """Raised when a single asset cannot be safely downgraded."""
