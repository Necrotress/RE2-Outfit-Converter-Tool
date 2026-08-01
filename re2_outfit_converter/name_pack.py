"""Build a Fluffy costume name pack (shared mes_sys MSG files)."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from .msg_name import (
    CLAIRE_NAME_PACK_KEYS,
    LEON_NAME_PACK_KEYS,
    SHARED_COSTUME_NAME_KEYS,
    SHARED_COSTUME_NAME_LABELS,
    SHARED_COSTUME_NAME_VANILLA,
    resolve_shared_costume_names,
    write_shared_costume_names,
)
from .packaging import safe_name, unique_path, zip_directory


def name_pack_description(resolved: dict[str, str]) -> str:
    """modinfo Description with Fluffy ``\\n`` line breaks for changed slots.

    Only lists slots that differ from vanilla, e.g. ``[Jacket] -> New Name``
    (ASCII arrow; Fluffy drops Unicode ``→``). Groups Claire then Leon.
    """
    lines = ["Costume menu names:"]

    def _add_group(title: str, keys: tuple[str, ...]) -> None:
        group: list[str] = []
        for key in keys:
            text = resolved[key]
            vanilla = SHARED_COSTUME_NAME_VANILLA[key]
            if text != vanilla:
                group.append(
                    f"[{SHARED_COSTUME_NAME_LABELS[key]}] -> {text}")
        if group:
            lines.append(title)
            lines.extend(group)

    _add_group("Claire:", CLAIRE_NAME_PACK_KEYS)
    _add_group("Leon:", LEON_NAME_PACK_KEYS)
    # Fluffy treats the two-char sequence \\n as a forced linebreak.
    return "\\n".join(lines)


def build_costume_name_pack(
    output_dir: Path,
    field_values: dict[str, str],
    *,
    as_folder: bool = False,
) -> Path:
    """Write a Fluffy-ready name pack zip (or folder) under ``output_dir``.

    ``field_values`` maps slot key → typed text (empty = vanilla).
    Requires at least one non-vanilla edit (Claire and/or Leon).
    """
    resolved = resolve_shared_costume_names(field_values)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pack_title = "Costume Name Pack"
    with tempfile.TemporaryDirectory(prefix="re2oc_namepack_") as tmp:
        staging = Path(tmp)
        write_shared_costume_names(staging, resolved)
        (staging / "modinfo.ini").write_text(
            "\n".join([
                f"Name={pack_title}",
                f"Description={name_pack_description(resolved)}",
                "Version=1.0",
                "",
            ]),
            encoding="utf-8",
        )
        if as_folder:
            dest = unique_path(output_dir / safe_name(pack_title))
            dest.mkdir(parents=True)
            for item in staging.iterdir():
                target = dest / item.name
                if item.is_dir():
                    shutil.copytree(item, target)
                else:
                    shutil.copy2(item, target)
            return dest

        zip_path = unique_path(output_dir / f"{safe_name(pack_title)}.zip")
        zip_directory(staging, zip_path)
        return zip_path
