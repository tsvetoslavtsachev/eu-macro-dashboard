"""Tests за period-aware staleness в export/data_status.py — Phase 8d."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from export.data_status import (
    assess_data_staleness,
    PERIOD_LENGTH_DAYS,
    RELEASE_LAG_DAYS,
)


# ── Period-aware staleness ────────────────────────────────────

def test_monthly_fresh():
    """Last obs преди < 30 дни — FRESH."""
    today = date(2026, 4, 30)
    status, age = assess_data_staleness("2026-04-01", "monthly", today=today)
    assert status == "FRESH"
    assert age == 29


def test_monthly_expected_in_release_window():
    """Last obs > 30d, но < 60d (в release window) — EXPECTED."""
    today = date(2026, 4, 30)
    status, age = assess_data_staleness("2026-03-01", "monthly", today=today)
    assert status == "EXPECTED"


def test_monthly_data_stale():
    """Last obs > period + release_lag (30+30=60d) — DATA_STALE."""
    today = date(2026, 4, 30)
    status, age = assess_data_staleness("2026-01-15", "monthly", today=today)
    assert status == "DATA_STALE"
    assert age >= 60


def test_quarterly_fresh():
    """EU quarterly последен release в 90 дни — FRESH."""
    today = date(2026, 4, 30)
    status, age = assess_data_staleness("2026-02-01", "quarterly", today=today)
    assert status == "FRESH"


def test_quarterly_expected_50d_lag():
    """EU quarterly: 90 < age < 140 (period 90 + lag 50) → EXPECTED.

    Това е критично за EU защото GDP/LFS/compensation са slow releases.
    """
    today = date(2026, 4, 30)
    # Last obs преди 100d (около 2026-01-20)
    last = "2026-01-20"
    status, age = assess_data_staleness(last, "quarterly", today=today)
    assert status == "EXPECTED"
    assert 90 < age < 140


def test_quarterly_data_stale():
    """EU quarterly > 140 days = просрочен release."""
    today = date(2026, 4, 30)
    status, _ = assess_data_staleness("2025-10-01", "quarterly", today=today)
    assert status == "DATA_STALE"


def test_weekly_fresh_for_ciss():
    """CISS weekly: < 7d → FRESH."""
    today = date(2026, 4, 30)
    status, _ = assess_data_staleness("2026-04-26", "weekly", today=today)
    assert status == "FRESH"


def test_unknown_for_missing_observation():
    status, age = assess_data_staleness(None, "monthly")
    assert status == "UNKNOWN"
    assert age is None


def test_unknown_for_invalid_date_string():
    status, age = assess_data_staleness("not-a-date", "monthly")
    assert status == "UNKNOWN"


def test_period_length_constants_match_handoff():
    """Handoff doc казва EU quarterly release_lag = 50d."""
    assert RELEASE_LAG_DAYS["quarterly"] == 50
    assert PERIOD_LENGTH_DAYS["quarterly"] == 90
    # Total threshold за DATA_STALE = 140d за quarterly
    assert PERIOD_LENGTH_DAYS["quarterly"] + RELEASE_LAG_DAYS["quarterly"] == 140


def test_future_observation_returns_fresh():
    """Last obs в бъдещето (от calendar drift) → FRESH с negative age."""
    today = date(2026, 4, 30)
    status, age = assess_data_staleness("2026-05-15", "monthly", today=today)
    assert status == "FRESH"
    assert age < 0
