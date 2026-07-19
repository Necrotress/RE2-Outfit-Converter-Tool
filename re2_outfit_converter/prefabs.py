"""PFB outfit-slot remapping."""

from __future__ import annotations

from pathlib import Path

from .analyzer import PfbSlot
from .outfits import Outfit
from .paths import PARTS_DIR, PFB_EXT_RE, ensure_dir_ci
from .reports import ConversionReport


def convert_pfb_slots(staging: Path, src_pfbs: list[PfbSlot],
                       source: Outfit, target: Outfit,
                       report: ConversionReport) -> None:
    by_part: dict[str, list[PfbSlot]] = {}
    for p in src_pfbs:
        by_part.setdefault(p.part, []).append(p)

    target_dir = ensure_dir_ci(staging, PARTS_DIR)
    for part, pfbs in by_part.items():
        primary = next((p for p in pfbs if p.slot == source.primary_slot), pfbs[0])
        primary_path = staging / primary.relpath
        if not primary_path.is_file():
            report.warnings.append(
                f"Skipped {part} PFB conversion: {primary.relpath} missing.")
            continue
        data = primary_path.read_bytes()
        m = PFB_EXT_RE.search(primary.relpath)
        ext = m.group(1) if m else ".pfb.16"

        for p in pfbs:
            (staging / p.relpath).unlink(missing_ok=True)

        for slot in target.all_slots:
            new_name = f"pl1000_{part}_{slot}{ext}"
            (target_dir / new_name).write_bytes(data)
            report.pfb_ops.append(f"{Path(primary.relpath).name}  ->  {new_name}")
