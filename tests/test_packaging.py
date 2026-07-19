"""Tag strip / apply helpers."""

from re2_outfit_converter.outfits import CLAIRE_OUTFIT_BY_KEY
from re2_outfit_converter.packaging import (
    _resolve_tag_marker,
    _strip_converter_tags,
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
