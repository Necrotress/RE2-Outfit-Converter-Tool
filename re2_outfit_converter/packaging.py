"""Output naming, modinfo tags, and zip/folder packaging."""

from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

from .analyzer import AnalysisResult
from .outfits import (
    CLAIRE_OUTFITS,
    LEGACY_OUTFIT_TAGS,
    OUTFIT_TAGS,
    Outfit,
    default_tag_marker,
)

_LEGACY_BLURB_RE = re.compile(
    r"\s*\|\s*Converted from .+? to .+? by RE2 Outfit Converter\.?",
    re.IGNORECASE,
)
_TAG_RE = re.compile(
    r"\s*\[(?:"
    + "|".join(
        re.escape(t)
        for t in (*OUTFIT_TAGS, *LEGACY_OUTFIT_TAGS,
                  *(o.name for o in CLAIRE_OUTFITS))
    )
    + r")\]",
    re.IGNORECASE,
)
_UNSAFE_NAME_RE = re.compile(r'[<>:"/\\|?*]')


def _ini_key(key: str) -> str:
    """INI key for comparison (BOM / surrounding spaces ignored)."""
    return key.strip().lstrip("\ufeff").lower()


def resolve_tag_marker(target: Outfit, tag_marker: str | None) -> str:
    if tag_marker is None:
        return default_tag_marker(target)
    return str(tag_marker).strip()


def safe_name(name: str) -> str:
    return _UNSAFE_NAME_RE.sub("", name).strip() or "mod"


def input_base_name(path: Path) -> str:
    """Base name of a dropped mod file/folder (archive extension stripped)."""
    name = path.name
    lower = name.lower()
    for ext in (".zip", ".rar", ".7z"):
        if lower.endswith(ext):
            return name[: -len(ext)]
    return name


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    n = 2
    while True:
        cand = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not cand.exists():
            return cand
        n += 1


def unique_folder_name(
    analysis: AnalysisResult,
    used: set[str],
    preferred: str | None = None,
    strip_tag_markers: list[str] | None = None,
    *,
    strip_tags: bool = True,
) -> str:
    """Stable inner-folder name for batch zips (no outfit tag appended).

    When ``strip_tags`` is False (e.g. preserving an on-disk folder name),
    only ``safe_name`` sanitizes illegal path characters — outfit markers
    like ``[Noir]`` in the original folder name are kept.
    """
    base = preferred or analysis.modinfo.name or (
        analysis.root.name if analysis.root else "mod")
    if strip_tags:
        base = strip_converter_tags(base, strip_tag_markers).strip() or "mod"
    else:
        base = str(base).strip() or "mod"
    name = safe_name(base)
    n = 2
    candidate = name
    while candidate.lower() in used:
        candidate = f"{name} ({n})"
        n += 1
    return candidate


def append_tag_marker(
    value: str,
    marker: str,
    strip_tag_markers: list[str] | None = None,
) -> str:
    value = strip_converter_tags(value, strip_tag_markers).strip()
    if not marker:
        return value
    if marker.lower() in value.lower():
        return value
    return f"{value} {marker}".strip() if value else marker


def fix_screenshot_case(staging: Path, lines: list[str]) -> list[str]:
    """Make Screenshot= match the real filename casing (Fluffy is picky)."""
    shot_idx = None
    shot_val = ""
    for i, line in enumerate(lines):
        key, sep, value = line.partition("=")
        if sep and _ini_key(key) == "screenshot":
            shot_idx = i
            shot_val = value.strip()
            break
    if shot_idx is None or not shot_val:
        return lines
    match = next(
        (p for p in staging.iterdir()
         if p.is_file() and p.name.lower() == shot_val.lower()),
        None,
    )
    if match is None or match.name == shot_val:
        return lines
    key = lines[shot_idx].partition("=")[0]
    lines[shot_idx] = f"{key}={match.name}"
    return lines


def resolve_convert_tag_flags(
    tag_output: bool,
    *,
    converting: bool,
    tag_modinfo_description: bool | None = None,
    tag_modinfo_name: bool = False,
) -> tuple[bool, bool, bool]:
    """Return ``(tag_zip, tag_description, tag_name)`` for one convert."""
    zip_on = bool(tag_output) and converting
    desc = tag_output if tag_modinfo_description is None else tag_modinfo_description
    desc_on = bool(desc) and converting
    name_on = bool(tag_modinfo_name) and converting
    return zip_on, desc_on, name_on


def update_modinfo(
    staging: Path,
    target: Outfit,
    tag_output: bool = True,
    tag_marker: str | None = None,
    strip_tag_markers: list[str] | None = None,
    *,
    tag_name: bool = False,
) -> str | None:
    """Update Description/Name tags and screenshot casing. Returns warning on failure.

    ``tag_output`` tags ``Description=``. ``tag_name`` tags ``Name=``.
    """
    ini = staging / "modinfo.ini"
    if not ini.is_file():
        return None
    try:
        lines = ini.read_text(
            encoding="utf-8-sig", errors="replace").splitlines()
        marker = resolve_tag_marker(target, tag_marker)
        out = []
        saw_description = False
        saw_name = False
        for line in lines:
            key, sep, value = line.partition("=")
            if not sep:
                out.append(line)
                continue
            k = _ini_key(key)
            if k == "description":
                saw_description = True
                if tag_output:
                    value = append_tag_marker(value, marker, strip_tag_markers)
                    line = f"{key}={value}"
            elif k == "name":
                saw_name = True
                if tag_name:
                    value = append_tag_marker(value, marker, strip_tag_markers)
                    line = f"{key}={value}"
            out.append(line)
        if tag_name and marker and not saw_name:
            tagged = append_tag_marker("", marker, strip_tag_markers)
            out.insert(0, f"Name={tagged}")
        if tag_output and marker and not saw_description:
            tagged = append_tag_marker("", marker, strip_tag_markers)
            out.insert(_description_insert_index(out), f"Description={tagged}")
        out = fix_screenshot_case(staging, out)
        ini.write_text("\n".join(out) + "\n", encoding="utf-8")
        return None
    except OSError as e:
        return f"Failed to update modinfo.ini: {e}"


def _description_insert_index(lines: list[str]) -> int:
    """Place a new Description= after Name=, else at the end."""
    last_name = None
    for i, line in enumerate(lines):
        key, sep, _value = line.partition("=")
        if sep and _ini_key(key) == "name":
            last_name = i
    if last_name is not None:
        return last_name + 1
    return len(lines)


def strip_converter_tags(
    text: str, extra_markers: list[str] | None = None,
) -> str:
    text = _LEGACY_BLURB_RE.sub("", text)
    text = _TAG_RE.sub("", text)
    for marker in extra_markers or ():
        marker = str(marker).strip()
        if not marker:
            continue
        text = re.sub(
            r"\s*" + re.escape(marker), "", text, flags=re.IGNORECASE)
    return text.rstrip()


def append_extra_marker(value: str, marker: str) -> str:
    """Append ``marker`` without stripping an outfit tag already on ``value``."""
    marker = (marker or "").strip()
    if not marker:
        return value
    if marker.lower() in value.lower():
        return value.strip()
    value = value.strip()
    return f"{value} {marker}".strip() if value else marker


def build_tag_marker(analysis: AnalysisResult, game_build: str) -> str:
    """``[RTX]`` or ``[Non-RTX]`` when the output build is not the one detected."""
    if game_build == "Ray tracing" and analysis.game_label != "Ray tracing":
        return "[RTX]"
    if game_build == "Classic" and analysis.has_rt:
        return "[Non-RTX]"
    return ""


def append_description_marker(staging: Path, marker: str) -> None:
    """Append ``marker`` to modinfo Description, leaving other tags in place."""
    marker = (marker or "").strip()
    if not marker:
        return
    ini = staging / "modinfo.ini"
    if not ini.is_file():
        return
    lines = ini.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    out: list[str] = []
    saw = False
    for line in lines:
        key, sep, value = line.partition("=")
        if sep and _ini_key(key) == "description":
            saw = True
            value = append_extra_marker(value, marker)
            line = f"{key}={value}"
        out.append(line)
    if not saw:
        out.insert(_description_insert_index(out), f"Description={marker}")
    ini.write_text("\n".join(out) + "\n", encoding="utf-8")


def output_base_name(
    analysis: AnalysisResult,
    target: Outfit,
    folder_name: str | None = None,
    tag_output: bool = True,
    tag_marker: str | None = None,
    strip_tag_markers: list[str] | None = None,
    source_name: str | None = None,
    extra_marker: str = "",
) -> str:
    if folder_name:
        return safe_name(folder_name)
    base = (
        (source_name or "").strip()
        or analysis.modinfo.name
        or (analysis.root.name if analysis.root else "mod")
    )
    base = strip_converter_tags(base, strip_tag_markers).strip() or "mod"
    marker = resolve_tag_marker(target, tag_marker)
    if tag_output and marker:
        name = safe_name(f"{base} {marker}")
    else:
        name = safe_name(base)
    extra = (extra_marker or "").strip()
    if extra:
        name = safe_name(f"{name} {extra}")
    return name


def make_folder(
    staging: Path,
    analysis: AnalysisResult,
    target: Outfit,
    output_dir: Path,
    folder_name: str | None = None,
    tag_output: bool = True,
    tag_marker: str | None = None,
    strip_tag_markers: list[str] | None = None,
    source_name: str | None = None,
    extra_marker: str = "",
) -> Path:
    safe = output_base_name(
        analysis, target, folder_name, tag_output=tag_output,
        tag_marker=tag_marker, strip_tag_markers=strip_tag_markers,
        source_name=source_name, extra_marker=extra_marker)
    dest = unique_path(output_dir / safe)
    # Move staging tree instead of a second full copy (temp cleanup tolerates
    # a vanished directory).
    shutil.move(str(staging), str(dest))
    return dest


def make_zip(
    staging: Path,
    analysis: AnalysisResult,
    target: Outfit,
    output_dir: Path,
    tag_output: bool = True,
    tag_marker: str | None = None,
    strip_tag_markers: list[str] | None = None,
    source_name: str | None = None,
    extra_marker: str = "",
) -> Path:
    """Write a Fluffy-ready single-mod zip (modinfo + natives at archive root)."""
    safe = output_base_name(
        analysis, target, tag_output=tag_output, tag_marker=tag_marker,
        strip_tag_markers=strip_tag_markers, source_name=source_name,
        extra_marker=extra_marker)
    zip_path = unique_path(output_dir / f"{safe}.zip")
    zip_directory(staging, zip_path)
    return zip_path


def zip_directory(root: Path, zip_path: Path) -> None:
    """Zip all files under root; paths inside the archive are relative to root.

    Uses deflate level 1 — much faster than the zlib default on texture-heavy
    mods, with only a modest size increase.
    """
    with zipfile.ZipFile(
        zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1,
    ) as zf:
        for f in root.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(root).as_posix())


# Back-compat aliases (tests / older call sites).
_resolve_tag_marker = resolve_tag_marker
_safe_name = safe_name
_unique_path = unique_path
_unique_folder_name = unique_folder_name
_append_tag_marker = append_tag_marker
_fix_screenshot_case = fix_screenshot_case
_update_modinfo = update_modinfo
_strip_converter_tags = strip_converter_tags
_output_base_name = output_base_name
_make_folder = make_folder
_make_zip = make_zip
_zip_directory = zip_directory
