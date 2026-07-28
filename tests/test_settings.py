"""Settings load / normalize / menu-label helpers."""

from __future__ import annotations

import json
import time
from pathlib import Path

from re2_outfit_converter import settings as settings_mod
from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY


def test_normalize_migrates_legacy_skip_popup():
    out = settings_mod.normalize_settings({"skip_same_outfit_popup": True})
    assert out["skip_convert_confirm"] is True
    assert "skip_same_outfit_popup" not in out


def test_outfit_menu_label_round_trip():
    cfg = settings_mod.normalize_settings({})
    elza = CLAIRE_OUTFIT_BY_KEY["elza"]
    label = settings_mod.outfit_menu_label(cfg, elza)
    assert settings_mod.outfit_from_menu_label(cfg, label) is elza


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
