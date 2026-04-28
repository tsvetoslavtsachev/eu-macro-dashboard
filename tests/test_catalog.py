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
    """Всеки запис трябва да има пълните 14 задължителни полета."""
    required = {
        "source", "id", "region", "name_bg", "name_en", "lens",
        "peer_group", "tags", "transform", "historical_start",
        "release_schedule", "typical_release", "revision_prone",
        "narrative_hint",
    }
    for key, meta in SERIES_CATALOG.items():
        assert required.issubset(set(meta.keys())), \
            f"{key} missing fields: {required - set(meta.keys())}"


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
