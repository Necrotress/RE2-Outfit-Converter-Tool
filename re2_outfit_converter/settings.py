"""App paths and settings.json load / save / normalize."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .outfits import (
    ALL_CONVERTIBLE_OUTFITS,
    CONVERTIBLE_OUTFITS,
    convertible_outfits_for,
    default_outfit_tag_markers,
    default_tag_marker,
)


def app_dir() -> Path:
    """Directory that contains the program (exe folder or project root)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def default_output_dir() -> Path:
    return app_dir() / "Output"


def settings_path() -> Path:
    return app_dir() / "settings.json"


def roaming_settings_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "RE2 Outfit Converter" / "settings.json"


def icon_path() -> Path | None:
    """App icon (dev tree or frozen PyInstaller bundle)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        cand = Path(sys._MEIPASS) / "re2_outfit_converter" / "assets" / "app_icon.ico"
    else:
        cand = Path(__file__).resolve().parent / "assets" / "app_icon.ico"
    return cand if cand.is_file() else None


def normalize_settings(data: dict) -> dict:
    """Migrate legacy keys and ensure defaults the UI expects."""
    settings = dict(data)
    settings.pop("skip_convert_confirm", None)
    settings.pop("skip_same_outfit_popup", None)
    settings.pop("menu_show_outfit_name", None)
    settings.pop("menu_show_outfit_tag", None)
    settings["skip_completion_dialog"] = bool(
        settings.get("skip_completion_dialog", False))
    settings["menu_outfit_labels"] = (
        "tag" if settings.get("menu_outfit_labels") == "tag" else "name")
    settings.pop("face_look", None)
    # Each missing split flag inherits legacy ``tag_output`` on its own.
    # Requiring both keys to be absent used to default zip tagging back on
    # when only Description had been saved.
    if "tag_zip_name" not in settings:
        settings["tag_zip_name"] = bool(settings.get("tag_output", True))
    if "tag_modinfo_description" not in settings:
        settings["tag_modinfo_description"] = bool(
            settings.get("tag_output", True))
    settings["tag_zip_name"] = bool(settings.get("tag_zip_name", True))
    settings["tag_modinfo_description"] = bool(
        settings.get("tag_modinfo_description", True))
    # Name tags collide with AddonFor packs. Keep the key, always off.
    settings["tag_modinfo_name"] = False
    if "tag_build_zip_name" not in settings:
        settings["tag_build_zip_name"] = True
    if "tag_build_modinfo_description" not in settings:
        settings["tag_build_modinfo_description"] = True
    settings["tag_build_zip_name"] = bool(
        settings.get("tag_build_zip_name", True))
    settings["tag_build_modinfo_description"] = bool(
        settings.get("tag_build_modinfo_description", True))
    settings["use_blender"] = bool(settings.get("use_blender", True))
    blender_path = settings.get("blender_path")
    settings["blender_path"] = (
        blender_path.strip() if isinstance(blender_path, str) else "")
    settings["tag_output"] = settings["tag_zip_name"]
    settings["write_convert_log"] = bool(
        settings.get("write_convert_log", True))
    settings.pop("ui_mode", None)
    settings["settings_outfit_tags_open"] = bool(
        settings.get("settings_outfit_tags_open", True))
    settings["settings_claire_tags_open"] = bool(
        settings.get("settings_claire_tags_open", True))
    settings["settings_leon_tags_open"] = bool(
        settings.get("settings_leon_tags_open", False))
    geo = settings.get("settings_geometry")
    settings["settings_geometry"] = (
        str(geo).strip() if isinstance(geo, str) else "")
    name_geo = settings.get("name_pack_geometry")
    settings["name_pack_geometry"] = (
        str(name_geo).strip() if isinstance(name_geo, str) else "")
    settings.pop("military_face", None)
    defaults = default_outfit_tag_markers()
    raw_tags = settings.get("outfit_tags")
    if not isinstance(raw_tags, dict):
        settings["outfit_tags"] = defaults
    else:
        # Keep user values; fill any newly added Leon/Claire keys.
        merged = dict(defaults)
        # Legacy key from early Leon draft (Mafia → Arklay Sheriff).
        if (
            "leon_mafia" in raw_tags
            and "leon_sheriff" not in raw_tags
            and isinstance(raw_tags.get("leon_mafia"), str)
        ):
            raw_tags = dict(raw_tags)
            raw_tags["leon_sheriff"] = raw_tags["leon_mafia"]
        for key, value in raw_tags.items():
            if key in defaults and isinstance(value, str):
                merged[key] = value.strip()
        settings["outfit_tags"] = merged
    return settings


def _settings_candidates() -> list[Path]:
    """Local + roaming paths, newest readable file first.

    Prefer newer mtime so a writable roaming copy is not shadowed by a stale
    local ``settings.json`` next to a read-only frozen install.
    """
    candidates: list[tuple[float, Path]] = []
    for path in (settings_path(), roaming_settings_path()):
        try:
            if path.is_file():
                candidates.append((path.stat().st_mtime, path))
        except OSError:
            continue
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [path for _, path in candidates]


def load_settings() -> dict:
    for path in _settings_candidates():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            return normalize_settings(data)
        try:
            path.with_suffix(path.suffix + ".bak").write_text(
                path.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError:
            pass
    return normalize_settings({})


def write_settings(settings: dict) -> bool:
    """Persist settings to disk. Returns True on success.

    Writes local first when possible; always also tries roaming so a later
    read-only install can still pick up the newest prefs by mtime.
    """
    settings = dict(settings)
    settings.pop("skip_same_outfit_popup", None)
    settings.pop("military_face", None)
    if not isinstance(settings.get("outfit_tags"), dict):
        settings["outfit_tags"] = default_outfit_tag_markers()
    payload = json.dumps(settings, indent=2)
    wrote = False
    for path in (settings_path(), roaming_settings_path()):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload, encoding="utf-8")
            wrote = True
        except OSError:
            continue
    return wrote


def initial_output_dir(settings: dict) -> str:
    saved = settings.get("output_dir", "").strip()
    if saved:
        saved_path = Path(saved)
        if saved_path.name.lower() == "converted" and saved_path.parent == app_dir():
            saved = ""
        elif saved_path.is_dir():
            return str(saved_path)
    path = default_output_dir()
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def outfit_tag_markers(settings: dict) -> dict[str, str]:
    defaults = default_outfit_tag_markers()
    raw = settings.get("outfit_tags")
    if not isinstance(raw, dict):
        return defaults
    merged = dict(defaults)
    for key, value in raw.items():
        if key in defaults and isinstance(value, str):
            merged[key] = value.strip()
    return merged


def tag_marker_for(settings: dict, outfit) -> str:
    return outfit_tag_markers(settings).get(
        outfit.key, default_tag_marker(outfit))


def strip_tag_markers(settings: dict) -> list[str]:
    return list(outfit_tag_markers(settings).values())


def outfit_menu_label(settings: dict, outfit) -> str:
    """Convert-menu text: the outfit name, or its tag, never both."""
    if settings.get("menu_outfit_labels") == "tag":
        marker = (tag_marker_for(settings, outfit) or "").strip()
        return marker or outfit.name
    return outfit.name


def outfit_menu_labels(
    settings: dict,
    *,
    character: str | None = None,
) -> list[str]:
    outfits = (
        convertible_outfits_for(character)
        if character
        else list(CONVERTIBLE_OUTFITS)
    )
    return [outfit_menu_label(settings, o) for o in outfits]


def outfit_from_menu_label(
    settings: dict,
    label: str,
    *,
    character: str | None = None,
):
    text = (label or "").strip()
    outfits = (
        convertible_outfits_for(character)
        if character
        else list(ALL_CONVERTIBLE_OUTFITS)
    )
    for outfit in outfits:
        marker = (tag_marker_for(settings, outfit) or "").strip()
        if text in (
            outfit_menu_label(settings, outfit), outfit.name, marker,
        ):
            return outfit
    return None
