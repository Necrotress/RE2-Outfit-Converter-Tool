"""App paths and settings.json load / save / normalize."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .outfits import CONVERTIBLE_OUTFITS, default_outfit_tag_markers, default_tag_marker


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
    if "skip_convert_confirm" in settings:
        settings["skip_convert_confirm"] = bool(
            settings["skip_convert_confirm"])
        settings.pop("skip_same_outfit_popup", None)
    elif "skip_same_outfit_popup" in settings:
        settings["skip_convert_confirm"] = bool(
            settings.pop("skip_same_outfit_popup"))
    else:
        settings["skip_convert_confirm"] = False
    settings["skip_completion_dialog"] = bool(
        settings.get("skip_completion_dialog", False))
    settings["menu_show_outfit_name"] = bool(
        settings.get("menu_show_outfit_name", True))
    settings["menu_show_outfit_tag"] = bool(
        settings.get("menu_show_outfit_tag", True))
    settings["tag_output"] = bool(settings.get("tag_output", True))
    if not isinstance(settings.get("outfit_tags"), dict):
        settings["outfit_tags"] = default_outfit_tag_markers()
    return settings


def load_settings() -> dict:
    for path in (settings_path(), roaming_settings_path()):
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
    """Persist settings to disk. Returns True on success."""
    settings = dict(settings)
    settings.pop("skip_same_outfit_popup", None)
    if not isinstance(settings.get("outfit_tags"), dict):
        settings["outfit_tags"] = default_outfit_tag_markers()
    payload = json.dumps(settings, indent=2)
    for path in (settings_path(), roaming_settings_path()):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload, encoding="utf-8")
            return True
        except OSError:
            continue
    return False


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
    parts: list[str] = []
    if settings.get("menu_show_outfit_name", True):
        parts.append(outfit.name)
    if settings.get("menu_show_outfit_tag", True):
        marker = (tag_marker_for(settings, outfit) or "").strip()
        if marker:
            parts.append(marker)
    return " ".join(parts) if parts else outfit.name


def outfit_menu_labels(settings: dict) -> list[str]:
    return [outfit_menu_label(settings, o) for o in CONVERTIBLE_OUTFITS]


def outfit_from_menu_label(settings: dict, label: str):
    text = (label or "").strip()
    for outfit in CONVERTIBLE_OUTFITS:
        if outfit_menu_label(settings, outfit) == text or outfit.name == text:
            return outfit
    return None
