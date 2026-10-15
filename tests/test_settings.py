"""Settings load / normalize / menu-label helpers."""

from __future__ import annotations

import json
import time
from pathlib import Path

from re2_outfit_converter import settings as settings_mod
from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY


def test_normalize_drops_the_old_confirm_and_menu_flags():
    out = settings_mod.normalize_settings({
        "skip_same_outfit_popup": True,
        "skip_convert_confirm": False,
        "menu_show_outfit_name": False,
        "menu_show_outfit_tag": False,
    })
    assert "skip_convert_confirm" not in out
    assert "skip_same_outfit_popup" not in out
    assert "menu_show_outfit_name" not in out
    assert "menu_show_outfit_tag" not in out


def test_normalize_splits_legacy_tag_output():
    on = settings_mod.normalize_settings({"tag_output": True})
    assert on["tag_zip_name"] is True
    assert on["tag_modinfo_description"] is True
    assert on["tag_modinfo_name"] is False
    off = settings_mod.normalize_settings({"tag_output": False})
    assert off["tag_zip_name"] is False
    assert off["tag_modinfo_description"] is False
    assert off["tag_modinfo_name"] is False


def test_normalize_keeps_explicit_tag_split():
    out = settings_mod.normalize_settings({
        "tag_zip_name": False,
        "tag_modinfo_description": True,
        "tag_modinfo_name": True,
        "tag_build_zip_name": False,
        "tag_build_modinfo_description": False,
    })
    assert out["tag_zip_name"] is False
    assert out["tag_modinfo_description"] is True
    assert out["tag_modinfo_name"] is False
    assert out["tag_output"] is False
    assert out["tag_build_zip_name"] is False
    assert out["tag_build_modinfo_description"] is False


def test_normalize_zip_tag_follows_legacy_when_description_already_split():
    out = settings_mod.normalize_settings({
        "tag_output": False,
        "tag_modinfo_description": True,
    })
    assert out["tag_zip_name"] is False
    assert out["tag_modinfo_description"] is True
    assert out["tag_modinfo_name"] is False


def test_normalize_name_pack_geometry():
    out = settings_mod.normalize_settings({
        "name_pack_geometry": "  520x580+40+80  ",
    })
    assert out["name_pack_geometry"] == "520x580+40+80"
    empty = settings_mod.normalize_settings({})
    assert empty["name_pack_geometry"] == ""
    assert empty["tag_modinfo_name"] is False
    assert empty["tag_build_zip_name"] is True
    assert empty["tag_build_modinfo_description"] is True
    assert "face_look" not in empty
    assert "face_look" not in settings_mod.normalize_settings(
        {"face_look": "vanilla"})


def test_clamp_dialog_geometry_caps_height():
    from re2_outfit_converter.gui_settings import clamp_dialog_geometry
    assert clamp_dialog_geometry(
        "500x4000+40+10", max_w=800, max_h=900,
        min_w=440, min_h=280,
    ) == "500x900+40+10"
    assert clamp_dialog_geometry(
        "+12+34", max_w=800, max_h=900,
    ) == "+12+34"


def test_dialog_position_strips_size():
    from re2_outfit_converter.gui_settings import dialog_position
    assert dialog_position("500x4000+40+10") == "+40+10"
    assert dialog_position("+12+34") == "+12+34"
    assert dialog_position("") == ""


def test_outfit_menu_label_is_name_or_tag():
    cfg = settings_mod.normalize_settings({})
    elza = CLAIRE_OUTFIT_BY_KEY["elza"]
    assert cfg["menu_outfit_labels"] == "name"
    label = settings_mod.outfit_menu_label(cfg, elza)
    assert label == elza.name
    assert settings_mod.outfit_from_menu_label(cfg, label) is elza
    cfg["menu_outfit_labels"] = "tag"
    tag = settings_mod.outfit_menu_label(cfg, elza)
    assert tag == "[Elza]"
    assert elza.name not in tag
    assert settings_mod.outfit_from_menu_label(cfg, tag) is elza


def test_load_prefers_newer_mtime(tmp_path: Path, monkeypatch):
    local = tmp_path / "local" / "settings.json"
    roam = tmp_path / "roam" / "settings.json"
    local.parent.mkdir()
    roam.parent.mkdir()
    local.write_text(json.dumps({"output_dir": "old-local"}), encoding="utf-8")
    time.sleep(0.05)
    roam.write_text(json.dumps({"output_dir": "new-roam"}), encoding="utf-8")

    monkeypatch.setattr(settings_mod, "settings_path", lambda: local)
    monkeypatch.setattr(settings_mod, "roaming_settings_path", lambda: roam)

    loaded = settings_mod.load_settings()
    assert loaded["output_dir"] == "new-roam"
