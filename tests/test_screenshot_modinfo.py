"""Screenshot casing helper (used for all outfit targets)."""

from pathlib import Path

from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
from re2_outfit_converter.packaging import _update_modinfo


def test_screenshot_case_fixed_in_modinfo(tmp_path: Path):
    root = tmp_path / "mod"
    root.mkdir()
    (root / "screen.jpg").write_bytes(b"jpg")
    (root / "modinfo.ini").write_text(
        "Name=X\nScreenshot=Screen.jpg\nDescription=Hi\n", encoding="utf-8")
    warn = _update_modinfo(
        root, CLAIRE_OUTFIT_BY_KEY["elza"], tag_output=False)
    assert warn is None
    text = (root / "modinfo.ini").read_text(encoding="utf-8")
    assert "Screenshot=screen.jpg" in text or "screenshot=screen.jpg" in text.lower()
    assert "Screen.jpg" not in text
