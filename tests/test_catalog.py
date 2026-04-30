"""Tests за catalog/series.py и catalog/cross_lens_pairs.py."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from catalog.series import (
    SERIES_CATALOG,
    ALLOWED_LENSES,
    ALLOWED_SOURCES,
    ALLOWED_REGIONS,
    ALLOWED_TRANSFORMS,
    ALLOWED_TAGS,
    ALLOWED_SCHEDULES,
    series_by_lens,
    series_by_peer_group,
    series_by_tag,
    series_by_source,
    all_series_ids,
    get_series,
    validate_catalog,
)
from catalog.cross_lens_pairs import CROSS_LENS_PAIRS, validate_pairs


# ── Catalog validation ─────────────────────────────────────────

def test_catalog_validates_clean():
    """Phase 1 catalog трябва да минава validation без errors."""
    errors = validate_catalog()
    assert errors == [], f"Catalog validation errors: {errors}"


def test_catalog_has_minimum_series_per_lens():
    """Всеки lens (5) трябва да има поне 1 серия в Phase 1."""
    for lens in ALLOWED_LENSES:
        series = series_by_lens(lens)
        assert len(series) >= 1, f"Lens '{lens}' has no series"


def test_get_series_raises_on_unknown_key():
    import pytest
    with pytest.raises(KeyError):
        get_series("DOES_NOT_EXIST")


def test_series_by_source_returns_correct_subset():
    ecb = series_by_source("ecb")
    eurostat = series_by_source("eurostat")
    assert all(s["source"] == "ecb" for s in ecb)
    assert all(s["source"] == "eurostat" for s in eurostat)
    assert len(ecb) + len(eurostat) <= len(SERIES_CATALOG)


def test_all_series_have_required_metadata():
    """Всеки запис трябва да има пълните 15 задължителни полета (Phase 1.5: + is_rate)."""
    required = {
        "source", "id", "region", "name_bg", "name_en", "lens",
        "peer_group", "tags", "transform", "is_rate", "historical_start",
        "release_schedule", "typical_release", "revision_prone",
        "narrative_hint",
    }
    for key, meta in SERIES_CATALOG.items():
        assert required.issubset(set(meta.keys())), \
            f"{key} missing fields: {required - set(meta.keys())}"


def test_is_rate_is_bool():
    """is_rate field трябва да е bool."""
    for key, meta in SERIES_CATALOG.items():
        assert isinstance(meta["is_rate"], bool), \
            f"{key}: is_rate not bool, got {type(meta['is_rate'])}"


def test_phase_15_new_series_present():
    """Phase 1.5 добавя 6 серии: comp_per_employee, HICP energy/food, PPI, BTP/OAT spreads."""
    new_series = [
        "EA_COMP_PER_EMPLOYEE",
        "EA_HICP_ENERGY",
        "EA_HICP_FOOD",
        "EA_PPI_INTERMEDIATE",
        "EA_BTP_BUND_SPREAD",
        "EA_OAT_BUND_SPREAD",
    ]
    for sid in new_series:
        assert sid in SERIES_CATALOG, f"Missing Phase 1.5 series: {sid}"


def test_new_peer_groups_de_singletoned():
    """Phase 1.5 въвежда нови peer_groups: wages, producer_prices, sovereign_spreads."""
    expected = {"wages", "producer_prices", "sovereign_spreads"}
    actual = {meta["peer_group"] for meta in SERIES_CATALOG.values()}
    assert expected.issubset(actual), f"Missing peer_groups: {expected - actual}"


def test_headline_measures_no_longer_singleton():
    """Phase 1.5: headline_measures имаше 1 серия (HEADLINE); сега има 3 (+ energy + food)."""
    members = series_by_peer_group("headline_measures")
    assert len(members) >= 3, f"headline_measures should have 3+, got {len(members)}"


def test_sovereign_spreads_has_two_members():
    """sovereign_spreads трябва да има BTP-Bund + OAT-Bund."""
    members = series_by_peer_group("sovereign_spreads")
    assert len(members) == 2
    sids = {m["_key"] for m in members}
    assert sids == {"EA_BTP_BUND_SPREAD", "EA_OAT_BUND_SPREAD"}


def test_derived_source_allowed():
    """source='derived' трябва да се поддържа за computed series."""
    derived = series_by_source("derived")
    assert len(derived) >= 2  # BTP-Bund + OAT-Bund
    for s in derived:
        assert s["source"] == "derived"


def test_lens_values_are_in_whitelist():
    for key, meta in SERIES_CATALOG.items():
        for lens in meta["lens"]:
            assert lens in ALLOWED_LENSES, f"{key}: invalid lens '{lens}'"


def test_source_values_are_in_whitelist():
    for key, meta in SERIES_CATALOG.items():
        assert meta["source"] in ALLOWED_SOURCES, \
            f"{key}: invalid source '{meta['source']}'"


def test_region_values_are_in_whitelist():
    for key, meta in SERIES_CATALOG.items():
        assert meta["region"] in ALLOWED_REGIONS, \
            f"{key}: invalid region '{meta['region']}'"


# ── Cross-lens pairs validation ────────────────────────────────

def test_cross_lens_pairs_validates():
    """Phase 1 pairs може да са празни, но не трябва да има validation errors."""
    errors = validate_pairs()
    assert errors == [], f"Pairs validation errors: {errors}"


def test_cross_lens_pairs_is_list():
    assert isinstance(CROSS_LENS_PAIRS, list)


def test_cross_lens_pairs_phase_15_populated():
    """Phase 1.5 populate-ва 6 EA-specific pairs."""
    assert len(CROSS_LENS_PAIRS) == 6, f"expected 6 pairs, got {len(CROSS_LENS_PAIRS)}"
    expected_ids = {
        "stagflation_test", "ecb_transmission", "fragmentation_risk",
        "inflation_anchoring", "pipeline_inflation", "sentiment_vs_hard_data",
    }
    actual_ids = {p["id"] for p in CROSS_LENS_PAIRS}
    assert actual_ids == expected_ids, f"missing/extra: {expected_ids ^ actual_ids}"


def test_cross_lens_pairs_reference_valid_lenses():
    """Всеки pair slot трябва да реферира към валиден lens."""
    for p in CROSS_LENS_PAIRS:
        for slot_name in ("slot_a", "slot_b"):
            slot = p[slot_name]
            assert slot["lens"] in ALLOWED_LENSES, \
                f"pair {p['id']}.{slot_name}: invalid lens '{slot['lens']}'"


def test_cross_lens_pairs_reference_existing_peer_groups():
    """Всеки peer_group в pair slots трябва да съществува в catalog."""
    catalog_peer_groups = {meta["peer_group"] for meta in SERIES_CATALOG.values()}
    for p in CROSS_LENS_PAIRS:
        for slot_name in ("slot_a", "slot_b"):
            for pg in p[slot_name]["peer_groups"]:
                assert pg in catalog_peer_groups, \
                    f"pair {p['id']}.{slot_name}: peer_group '{pg}' not in catalog"


def test_cross_lens_pairs_have_full_interpretations():
    """Всеки pair трябва да има 5 interpretation states с non-empty narratives."""
    expected_states = {"both_up", "both_down", "a_up_b_down", "a_down_b_up", "transition"}
    for p in CROSS_LENS_PAIRS:
        states = set(p["interpretations"].keys())
        assert states == expected_states, \
            f"pair {p['id']}: states mismatch: {expected_states ^ states}"
        for state, narrative in p["interpretations"].items():
            assert isinstance(narrative, str) and len(narrative) > 20, \
                f"pair {p['id']}.{state}: narrative too short or invalid"


# ── Helper queries ─────────────────────────────────────────────

def test_series_by_lens_includes_multi_lens():
    """Серия с lens=['credit', 'ecb'] трябва да се появи в двата заявени lens-а."""
    # В catalog-а нямаме multi-lens записи в Phase 1, но helper-ът трябва да поддържа.
    # Test чрез искуственo вземане:
    items = series_by_lens("credit")
    for item in items:
        assert "credit" in item["lens"], f"{item.get('_key')} doesn't have credit lens"


def test_all_series_ids_returns_list():
    ids = all_series_ids()
    assert isinstance(ids, list)
    assert len(ids) == len(SERIES_CATALOG)
