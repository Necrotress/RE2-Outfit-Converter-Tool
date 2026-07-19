"""Private ID allocation tests."""

import pytest

from re2_outfit_converter.isolation import allocate_private_ids
from re2_outfit_converter.reports import ConversionError


def test_allocate_stable_for_same_seed():
    a = allocate_private_ids("MyMod", set())
    b = allocate_private_ids("MyMod", set())
    assert a == b
    assert a[0] != a[1]
    assert a[0].startswith("pl18") and len(a[0]) == 6


def test_allocate_skips_reserved():
    reserved = {f"pl{1800 + i}" for i in range(98)}
    face, hair = allocate_private_ids("x", set(reserved))
    assert face not in reserved and hair not in reserved
    assert face != hair


def test_allocate_exhaustion():
    reserved = {f"pl{1800 + i}" for i in range(100)}
    with pytest.raises(ConversionError):
        allocate_private_ids("full", set(reserved))
