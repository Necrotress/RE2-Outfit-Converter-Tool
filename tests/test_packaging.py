"""Tag strip / apply helpers."""

from pathlib import Path

from re2_outfit_converter.analyzer import AnalysisResult
from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
from re2_outfit_converter.packaging import (
    _resolve_tag_marker,
    _strip_converter_tags,
    input_base_name,
    output_base_name,
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
