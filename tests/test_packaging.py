"""Tag strip / apply helpers."""

from pathlib import Path
import re

from re2_outfit_converter.analyzer import AnalysisResult
from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
from re2_outfit_converter.packaging import (
    _resolve_tag_marker,
    _strip_converter_tags,
    input_base_name,
    output_base_name,
    unique_path,
    update_modinfo,
)


def test_strip_default_and_custom_tags():
    assert _strip_converter_tags("MyMod [Elza]") == "MyMod"
    assert _strip_converter_tags("MyMod [Tank]") == "MyMod"
    assert _strip_converter_tags("MyMod {X}", ["{X}"]) == "MyMod"
    assert _strip_converter_tags("MyMod -B-", ["-B-"]) == "MyMod"


def test_resolve_tag_marker():
    elza = CLAIRE_OUTFIT_BY_KEY["elza"]
    assert _resolve_tag_marker(elza, None) == "[Elza]"
    assert _resolve_tag_marker(elza, "{X}") == "{X}"
    assert _resolve_tag_marker(elza, "  ") == ""


def test_unique_path_keeps_the_zip_suffix(tmp_path: Path):
    first = tmp_path / "Costume Name Pack.zip"
    first.write_bytes(b"a")
    second = unique_path(first)
    assert second.name == "Costume Name Pack (2).zip"
    assert second.suffix == ".zip"


def test_input_base_name_strips_archives():
    assert input_base_name(Path("Casual Claire.rar")) == "Casual Claire"
    assert input_base_name(Path("MyMod.zip")) == "MyMod"
    assert input_base_name(Path("folder")) == "folder"


def test_output_base_name_prefers_source_name():
    noir = CLAIRE_OUTFIT_BY_KEY["noir"]
    analysis = AnalysisResult()
    analysis.modinfo.name = "Addon Name"
    assert output_base_name(
        analysis, noir, source_name="Dropped File", tag_output=True,
    ) == "Dropped File [Noir]"


def test_update_modinfo_adds_description_when_missing(tmp_path: Path):
    root = tmp_path / "mod"
    root.mkdir()
    (root / "modinfo.ini").write_text("Name=MyMod\nVersion=1.0\n", encoding="utf-8")
    warn = update_modinfo(root, CLAIRE_OUTFIT_BY_KEY["elza"], tag_output=True)
    assert warn is None
    text = (root / "modinfo.ini").read_text(encoding="utf-8")
    assert "Description=[Elza]" in text
    assert text.index("Name=MyMod") < text.index("Description=[Elza]")
    assert text.index("Description=[Elza]") < text.index("Version=1.0")


def test_update_modinfo_appends_tag_to_existing_description(tmp_path: Path):
    root = tmp_path / "mod"
    root.mkdir()
    (root / "modinfo.ini").write_text(
        "Name=MyMod\nDescription=Cute Claire\n", encoding="utf-8")
    warn = update_modinfo(root, CLAIRE_OUTFIT_BY_KEY["noir"], tag_output=True)
    assert warn is None
    text = (root / "modinfo.ini").read_text(encoding="utf-8")
    assert "Description=Cute Claire [Noir]" in text


def test_update_modinfo_skips_new_description_when_untagged(tmp_path: Path):
    root = tmp_path / "mod"
    root.mkdir()
    (root / "modinfo.ini").write_text("Name=MyMod\n", encoding="utf-8")
    warn = update_modinfo(root, CLAIRE_OUTFIT_BY_KEY["elza"], tag_output=False)
    assert warn is None
    text = (root / "modinfo.ini").read_text(encoding="utf-8")
    assert "Description=" not in text


def test_update_modinfo_tags_name_when_requested(tmp_path: Path):
    root = tmp_path / "mod"
    root.mkdir()
    (root / "modinfo.ini").write_text(
        "Name=MyMod\nDescription=Hi\n", encoding="utf-8")
    warn = update_modinfo(
        root, CLAIRE_OUTFIT_BY_KEY["noir"],
        tag_output=False, tag_name=True)
    assert warn is None
    text = (root / "modinfo.ini").read_text(encoding="utf-8")
    assert "Name=MyMod [Noir]" in text
    assert "Description=Hi\n" in text or "Description=Hi" in text.splitlines()


def test_update_modinfo_inserts_name_when_missing(tmp_path: Path):
    root = tmp_path / "mod"
    root.mkdir()
    (root / "modinfo.ini").write_text(
        "Description=Hi\nVersion=1.0\n", encoding="utf-8")
    warn = update_modinfo(
        root, CLAIRE_OUTFIT_BY_KEY["noir"],
        tag_output=False, tag_name=True)
    assert warn is None
    text = (root / "modinfo.ini").read_text(encoding="utf-8")
    assert "Name=[Noir]" in text
    assert text.index("Name=[Noir]") < text.index("Description=Hi")


def test_update_modinfo_tags_name_with_bom_and_spaces(tmp_path: Path):
    root = tmp_path / "mod"
    root.mkdir()
    (root / "modinfo.ini").write_bytes(
        b"\xef\xbb\xbfName = MyMod\nDescription=Hi\n")
    warn = update_modinfo(
        root, CLAIRE_OUTFIT_BY_KEY["elza"],
        tag_output=False, tag_name=True)
    assert warn is None
    text = (root / "modinfo.ini").read_text(encoding="utf-8")
    assert re.search(r"Name\s*=\s*MyMod \[Elza\]", text, re.I)
    assert "Description=Hi" in text


def test_resolve_convert_tag_flags_description_follows_zip_by_default():
    from re2_outfit_converter.packaging import resolve_convert_tag_flags

    zip_on, desc_on, name_on = resolve_convert_tag_flags(
        True, converting=True)
    assert (zip_on, desc_on, name_on) == (True, True, False)
    zip_on, desc_on, name_on = resolve_convert_tag_flags(
        False, converting=True, tag_modinfo_description=True,
        tag_modinfo_name=True)
    assert (zip_on, desc_on, name_on) == (False, True, True)
