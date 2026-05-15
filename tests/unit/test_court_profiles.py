"""Unit tests for CourtProfile presets."""
import pytest


def test_nba_dimensions():
    from configs.settings import CourtProfile, CourtLevel
    p = CourtProfile.from_level(CourtLevel.NBA)
    assert p.width_m == 28.65
    assert p.height_m == 15.24
    assert p.half_court is False


def test_primaria_dimensions():
    from configs.settings import CourtProfile, CourtLevel
    p = CourtProfile.from_level(CourtLevel.PRIMARIA)
    assert p.width_m == 24.0
    assert p.height_m == 13.0


def test_mini_basket_is_half_court():
    from configs.settings import CourtProfile, CourtLevel
    p = CourtProfile.from_level(CourtLevel.MINI_BASKET)
    assert p.half_court is True


def test_custom_override():
    from configs.settings import CourtProfile, CourtLevel
    p = CourtProfile(CourtLevel.NBA, width_m=30.0, height_m=16.0)
    assert p.width_m == 30.0
    assert p.height_m == 16.0


def test_all_levels_have_display_px():
    from configs.settings import CourtProfile, CourtLevel
    for level in CourtLevel:
        p = CourtProfile.from_level(level)
        assert p.display_w_px > 0
        assert p.display_h_px > 0
