"""Unit tests for the procedural play library generator."""
import pytest

from app.services.play_library import (
    TEMPLATE_PLAYS,
    MASTER_2026_PLAYS,
    expand_play,
    validate_svg_data,
    build_template_seed_data,
    build_master_playbook_data,
)


# ── Template plays ────────────────────────────────────────────────────────────

def test_exactly_12_templates():
    assert len(TEMPLATE_PLAYS) == 12, f"Expected 12 templates, got {len(TEMPLATE_PLAYS)}"


def test_exactly_30_master_plays():
    assert len(MASTER_2026_PLAYS) == 30, f"Expected 30 master plays, got {len(MASTER_2026_PLAYS)}"


def test_template_names_unique():
    names = [p.name for p in TEMPLATE_PLAYS]
    assert len(names) == len(set(names)), "Duplicate template names found"


def test_master_names_unique():
    names = [p.name for p in MASTER_2026_PLAYS]
    assert len(names) == len(set(names)), "Duplicate master play names found"


# ── expand_play structural tests ──────────────────────────────────────────────

@pytest.mark.parametrize("defn", TEMPLATE_PLAYS, ids=lambda d: d.name)
def test_template_has_10_frames(defn):
    svg = expand_play(defn)
    assert svg["version"] == 2
    assert len(svg["frames"]) >= 10, f"{defn.name}: expected >=10 frames"


@pytest.mark.parametrize("defn", MASTER_2026_PLAYS, ids=lambda d: d.name)
def test_master_play_has_10_frames(defn):
    svg = expand_play(defn)
    assert len(svg["frames"]) >= 10, f"{defn.name}: expected >=10 frames"


@pytest.mark.parametrize("defn", TEMPLATE_PLAYS + MASTER_2026_PLAYS, ids=lambda d: d.name)
def test_five_team1_players_per_frame(defn):
    svg = expand_play(defn)
    for fi, frame in enumerate(svg["frames"]):
        team1 = [p for p in frame["players"] if p["team"] == 1]
        assert len(team1) == 5, f"{defn.name} frame {fi}: {len(team1)} team-1 players"


@pytest.mark.parametrize("defn", TEMPLATE_PLAYS + MASTER_2026_PLAYS, ids=lambda d: d.name)
def test_players_in_bounds(defn):
    svg = expand_play(defn)
    for fi, frame in enumerate(svg["frames"]):
        for p in frame["players"]:
            assert 0 <= p["x"] <= 500, f"{defn.name} frame {fi} player {p['id']} x={p['x']} out of bounds"
            assert 0 <= p["y"] <= 280, f"{defn.name} frame {fi} player {p['id']} y={p['y']} out of bounds"


@pytest.mark.parametrize("defn", TEMPLATE_PLAYS + MASTER_2026_PLAYS, ids=lambda d: d.name)
def test_player_ids_consistent_across_frames(defn):
    """Same player IDs should appear in every frame."""
    svg = expand_play(defn)
    frames = svg["frames"]
    first_ids = {p["id"] for p in frames[0]["players"]}
    for fi, frame in enumerate(frames[1:], 1):
        ids = {p["id"] for p in frame["players"]}
        assert ids == first_ids, f"{defn.name} frame {fi}: player IDs changed"


# ── validate_svg_data ─────────────────────────────────────────────────────────

def test_validate_passes_for_all_templates():
    for defn in TEMPLATE_PLAYS:
        svg = expand_play(defn)
        errors = validate_svg_data(svg)
        assert not errors, f"{defn.name} validation errors: {errors}"


def test_validate_passes_for_all_master_plays():
    for defn in MASTER_2026_PLAYS:
        svg = expand_play(defn)
        errors = validate_svg_data(svg)
        assert not errors, f"{defn.name} validation errors: {errors}"


def test_validate_catches_wrong_version():
    errors = validate_svg_data({"version": 1, "frames": []})
    assert any("version" in e for e in errors)


def test_validate_catches_too_few_frames():
    svg = expand_play(TEMPLATE_PLAYS[0])
    svg["frames"] = svg["frames"][:5]
    errors = validate_svg_data(svg)
    assert any("10" in e or "frames" in e for e in errors)


# ── Build helpers ─────────────────────────────────────────────────────────────

def test_build_template_seed_data_has_12_entries():
    seeds = build_template_seed_data()
    assert len(seeds) == 12
    for s in seeds:
        assert s["is_template"] is True
        assert s["svg_data_version"] == 2
        assert len(s["svg_data"]["frames"]) >= 10


def test_build_master_playbook_data():
    meta, plays = build_master_playbook_data()
    assert meta["name"] == "Master Playbook 2026"
    assert meta["is_system"] is True
    assert len(plays) == 30
    for p in plays:
        assert p["svg_data_version"] == 2
        assert len(p["svg_data"]["frames"]) >= 10
