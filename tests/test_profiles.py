from __future__ import annotations

import pytest

from lebench.core.profiles import (
    PRODUCT_TYPES,
    get_profile,
    get_intensity,
    resolve_modules,
)


def test_five_profiles_exist():
    assert PRODUCT_TYPES == ("vps", "dedicated", "gpu", "lightweight", "bare_metal")
    for name in PRODUCT_TYPES:
        p = get_profile(name)
        assert p.product_type == name
        assert "system" in p.site_required


def test_baremetal_alias_rejected():
    with pytest.raises(KeyError, match="bare_metal"):
        get_profile("baremetal")


def test_quick_modules_include_system():
    profile = get_profile("vps")
    intensity = get_intensity("quick")
    mods = resolve_modules(profile, intensity)
    assert "system" in mods
    assert "cpu" in mods
    assert "memory" in mods


def test_explicit_modules_no_silent_append():
    profile = get_profile("vps")
    intensity = get_intensity("standard")
    mods = resolve_modules(profile, intensity, include=["system", "cpu"])
    assert mods == ["system", "cpu"]


def test_skip_modules():
    profile = get_profile("vps")
    intensity = get_intensity("standard")
    mods = resolve_modules(profile, intensity, skip=["network", "ping"])
    assert "network" not in mods
    assert "ping" not in mods
