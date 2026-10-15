"""Build a Fluffy costume name pack (shared mes_sys MSG files)."""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

from .msg_name import (
    CLAIRE_NAME_PACK_KEYS,
    LEON_NAME_PACK_KEYS,
    MSG_DIR_SYS,
    SHARED_COSTUME_NAME_LABELS,
    SHARED_COSTUME_NAME_VANILLA,
    read_shared_costume_names,
    resolve_shared_costume_names,
    sys_message_rel,
    write_shared_costume_names,
)
from .packaging import safe_name

PACK_TITLE = "Costume Name Pack"
COSTUME_MSG_REL = f"{MSG_DIR_SYS}/mes_sys_costume.msg.14"
COSTUME_MSG_RELS = (
    sys_message_rel("mes_sys_costume", "Ray tracing"),
    COSTUME_MSG_REL,
)
_SKIP_ARCHIVE_SUFFIXES = {".rar", ".7z"}


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


def find_existing_name_pack(output_dir: Path) -> Path | None:
    """Return the name pack in ``output_dir`` to edit, or None.

    Prefers the ``Costume Name Pack`` folder, then a canonical zip, then
    the newest other pack. A folder wins over a zip with the same name so
    a later save edits that folder.
    """
    root = Path(output_dir)
    if not root.is_dir():
        return None

    canonical: list[Path] = []
    others: list[Path] = []
    for child in root.iterdir():
        if not _looks_like_name_pack(child):
            continue
        if _is_canonical_pack_name(child.name):
            canonical.append(child)
        else:
            others.append(child)

    pool = canonical or others
    if not pool:
        return None
    folders = [path for path in pool if path.is_dir()]
    chosen = folders or pool
    return max(chosen, key=lambda path: path.stat().st_mtime)


def read_name_pack_fields(pack_path: Path) -> dict[str, str]:
    """Read dialog field values from a name-pack zip or folder.

    Custom names are returned as stored; vanilla slots are ``""`` so the
    editor placeholders still show the default.
    """
    path = Path(pack_path)
    rel = _costume_msg_rel(path)
    if rel is None:
        raise FileNotFoundError(
            f"{path.name} is missing a costume name file")
    if path.is_dir():
        names = read_shared_costume_names(path / Path(*rel.split("/")))
    else:
        with zipfile.ZipFile(path) as zf:
            member = _zip_find(zf, rel)
            if member is None:
                raise FileNotFoundError(
                    f"{path.name} is missing a costume name file")
            with tempfile.TemporaryDirectory(prefix="re2oc_namepack_read_") as tmp:
                dest = Path(tmp) / Path(member).name
                dest.write_bytes(zf.read(member))
                names = read_shared_costume_names(dest)
    return {
        key: (text if text != SHARED_COSTUME_NAME_VANILLA[key] else "")
        for key, text in names.items()
    }


def name_pack_game_build(pack_path: Path) -> str | None:
    """Return the build whose costume message file is in this pack."""
    rel = _costume_msg_rel(Path(pack_path))
    if rel is None:
        return None
    lowered = rel.replace("\\", "/").lower()
    if lowered.startswith("natives/stm/") or lowered.endswith(".msg.50397457"):
        return "Ray tracing"
    return "Classic"


def _costume_msg_rel(path: Path) -> str | None:
    """Relative costume-message path inside a name-pack folder or zip."""
    if path.is_dir():
        for rel in COSTUME_MSG_RELS:
            if (path / Path(*rel.split("/"))).is_file():
                return rel
        return None
    if not path.is_file():
        return None
    try:
        with zipfile.ZipFile(path) as zf:
            for rel in COSTUME_MSG_RELS:
                if _zip_find(zf, rel):
                    return rel
    except (OSError, zipfile.BadZipFile):
        return None
    return None


def pack_folder_name() -> str:
    """Directory name Fluffy lists for the costume name pack."""
    return safe_name(PACK_TITLE)


def build_costume_name_pack(
    output_dir: Path,
    field_values: dict[str, str],
    *,
    as_folder: bool = True,
    dest: Path | None = None,
    game_build: str | None = None,
) -> Path:
    """Write the costume name pack as one folder and update its files.

    ``field_values`` maps slot key → typed text (empty = vanilla).
    Requires at least one non-vanilla edit (Claire and/or Leon).
    The folder is always ``Costume Name Pack`` in the output directory.
    ``modinfo.ini`` and the message files inside it are replaced. Other
    name-pack zips or numbered copies in that directory are removed so
    Fluffy does not list a second pack. ``as_folder`` is accepted so older
    callers still run; the pack is never written as a zip.
    """
    _ = as_folder
    resolved = resolve_shared_costume_names(field_values)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    parent = Path(dest).parent if dest is not None else output_dir
    parent.mkdir(parents=True, exist_ok=True)
    folder = parent / pack_folder_name()

    with tempfile.TemporaryDirectory(prefix="re2oc_namepack_") as tmp:
        staging = Path(tmp)
        write_shared_costume_names(
            staging, resolved, game_build=game_build)
        (staging / "modinfo.ini").write_text(
            "\n".join([
                f"Name={PACK_TITLE}",
                f"Description={name_pack_description(resolved)}",
                "Version=1.0",
                "",
            ]),
            encoding="utf-8",
        )
        _install_folder(staging, folder)

    _retire_other_name_packs(parent, keep=folder)
    return folder


def _retire_other_name_packs(directory: Path, keep: Path) -> None:
    """Remove other costume name packs so Fluffy lists this folder once."""
    keep_resolved = keep.resolve()
    for child in list(directory.iterdir()):
        try:
            if child.resolve() == keep_resolved:
                continue
        except OSError:
            continue
        if not _looks_like_name_pack(child):
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _install_folder(staging: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for item in staging.iterdir():
        target = dest / item.name
        if item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def _is_canonical_pack_name(name: str) -> bool:
    lower = name.lower()
    return lower in {
        f"{safe_name(PACK_TITLE).lower()}.zip",
        safe_name(PACK_TITLE).lower(),
    }


def _looks_like_name_pack(path: Path) -> bool:
    try:
        if path.is_dir():
            ini = path / "modinfo.ini"
            return (
                ini.is_file()
                and _costume_msg_rel(path) is not None
                and _is_pack_title(_read_text(ini))
            )
        if not path.is_file():
            return False
        if path.suffix.lower() in _SKIP_ARCHIVE_SUFFIXES:
            return False
        with zipfile.ZipFile(path) as zf:
            return _zip_is_name_pack(zf)
    except (OSError, zipfile.BadZipFile, UnicodeError):
        return False


def _zip_is_name_pack(zf: zipfile.ZipFile) -> bool:
    ini_name = _zip_find(zf, "modinfo.ini")
    msg_name = next(
        (found for rel in COSTUME_MSG_RELS if (found := _zip_find(zf, rel))),
        None,
    )
    if ini_name is None or msg_name is None:
        return False
    try:
        text = zf.read(ini_name).decode("utf-8-sig", errors="replace")
    except OSError:
        return False
    return _is_pack_title(text)


def _zip_find(zf: zipfile.ZipFile, rel: str) -> str | None:
    want = rel.replace("\\", "/").lower()
    for name in zf.namelist():
        if name.replace("\\", "/").lower() == want:
            return name
    return None


def _is_pack_title(modinfo_text: str) -> bool:
    for line in modinfo_text.lstrip("\ufeff").splitlines():
        key, sep, value = line.partition("=")
        if not sep:
            continue
        if key.strip().lstrip("\ufeff").lower() == "name":
            return value.strip() == PACK_TITLE
    return False


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")
