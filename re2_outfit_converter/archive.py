"""Getting mods into a folder we can analyze: folders, zip, rar, 7z."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

_SEVEN_ZIP = (
    Path(r"C:\Program Files\7-Zip\7z.exe"),
    Path(r"C:\Program Files (x86)\7-Zip\7z.exe"),
)
ARCHIVE_EXTS = frozenset({".zip", ".rar", ".7z"})
# Nested archive packs (zip-of-zips). Cap depth to avoid zip bombs / cycles.
_MAX_NEST_DEPTH = 3


class ExtractError(Exception):
    pass


def find_7zip() -> Path | None:
    for cand in _SEVEN_ZIP:
        if cand.is_file():
            return cand
    exe = shutil.which("7z")
    return Path(exe) if exe else None


def is_archive(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in ARCHIVE_EXTS


def _safe_extract_zip(archive: Path, dest: Path) -> None:
    """Extract a zip, rejecting path-traversal entries (zip-slip)."""
    dest = dest.resolve()
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            target = (dest / info.filename).resolve()
            try:
                target.relative_to(dest)
            except ValueError as e:
                raise ExtractError(
                    f"Unsafe path in {archive.name}: {info.filename!r}"
                ) from e
        zf.extractall(dest)


def _extract_archive_file(archive: Path, dest: Path) -> None:
    """Extract one archive file into dest (must not already exist as a file)."""
    dest.mkdir(parents=True, exist_ok=True)
    ext = archive.suffix.lower()
    if ext == ".zip":
        try:
            _safe_extract_zip(archive, dest)
        except zipfile.BadZipFile as e:
            raise ExtractError(f"Corrupt zip file: {archive.name}: {e}") from e
        return

    seven = find_7zip()
    if seven is None:
        raise ExtractError(
            f"Extracting {ext} archives requires 7-Zip "
            "(https://www.7-zip.org/). Prefer a .zip if you can."
        )
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    proc = subprocess.run(
        [str(seven), "x", "-y", f"-o{dest}", str(archive)],
        capture_output=True, text=True,
        creationflags=flags,
    )
    if proc.returncode != 0:
        raise ExtractError(
            f"7-Zip failed to extract {archive.name}:\n"
            f"{proc.stderr.strip()}"
        )
    _assert_extract_contained(dest, archive.name)


def _assert_extract_contained(dest: Path, archive_name: str) -> None:
    """Reject path traversal after 7-Zip extract (zip-slip equivalent)."""
    root = dest.resolve()
    for path in dest.rglob("*"):
        try:
            path.resolve().relative_to(root)
        except ValueError as e:
            raise ExtractError(
                f"Unsafe path extracted from {archive_name}: "
                f"{path.relative_to(dest).as_posix()!r}"
            ) from e


def expand_nested_archives(
    root: Path, *, max_depth: int = _MAX_NEST_DEPTH,
) -> list[str]:
    """Extract nested .zip/.rar/.7z under root in place (up to max_depth).

    Each archive becomes a folder next to it named after the archive stem
    (with a numeric suffix if needed). The archive file is removed after a
    successful extract so find_mod_roots can see natives/modinfo.ini.

    Returns human-readable notes for UI warnings (empty if nothing nested).
    """
    notes: list[str] = []
    for _ in range(max_depth):
        archives = sorted(
            (p for p in root.rglob("*") if is_archive(p)),
            key=lambda p: (len(p.parts), str(p).lower()),
        )
        if not archives:
            break
        for archive in archives:
            if not archive.is_file():
                continue
            parent = archive.parent
            dest = parent / archive.stem
            n = 2
            while dest.exists():
                dest = parent / f"{archive.stem} ({n})"
                n += 1
            try:
                _extract_archive_file(archive, dest)
            except ExtractError as e:
                notes.append(str(e))
                continue
            try:
                archive.unlink()
            except OSError:
                pass
            notes.append(
                f"Unpacked nested archive: {archive.name} -> {dest.name}/"
            )
    else:
        # Still nested archives after max_depth — leave them and note it.
        leftover = [p.name for p in root.rglob("*") if is_archive(p)]
        if leftover:
            notes.append(
                "Stopped unpacking nested archives after "
                f"{max_depth} levels (left: {', '.join(leftover[:6])}"
                + ("…" if len(leftover) > 6 else "")
                + ")."
            )
    return notes


class ModSource:
    """Folder or archive input. Archives extract to a temp dir cleaned by close()."""

    def __init__(self, path: Path):
        self.original = Path(path)
        self._tempdir: tempfile.TemporaryDirectory[str] | None = None
        self.nested_notes: list[str] = []
        self.folder = self._prepare()

    def _prepare(self) -> Path:
        if self.original.is_dir():
            # Work on a staging copy when nested archives are present so we
            # never delete the user's original zip files from a dropped folder.
            nested = [p for p in self.original.rglob("*") if is_archive(p)]
            if not nested:
                return self.original
            self._tempdir = tempfile.TemporaryDirectory(prefix="re2oc_")
            dest = Path(self._tempdir.name) / self.original.name
            shutil.copytree(self.original, dest)
            self.nested_notes = expand_nested_archives(dest)
            return dest

        if not is_archive(self.original):
            raise ExtractError(
                f"Unsupported input: {self.original.name}\n"
                "Drop a mod folder or a .zip / .rar / .7z archive."
            )
        self._tempdir = tempfile.TemporaryDirectory(prefix="re2oc_")
        dest = Path(self._tempdir.name)
        _extract_archive_file(self.original, dest)
        self.nested_notes = expand_nested_archives(dest)
        return dest

    def close(self) -> None:
        if self._tempdir is not None:
            self._tempdir.cleanup()
            self._tempdir = None

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
