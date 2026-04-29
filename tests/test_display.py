"""Tests за core/display.py — display-by-type formatting."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.display import (
    BPS_PEER_GROUPS,
    ABS_PEER_GROUPS,
    BPS_SIDS_OVERRIDE,
    RATE_TRANSFORMS,
    change_kind,
    compute_change,
    latest_change,
    fmt_change,
    fmt_value,
    short_period_label,
    long_period_label,
    change_header,
)


# ── change_kind ────────────────────────────────────────────────

def test_bps_peer_group_returns_bps():
    """policy_rates → bps."""
    meta = {"peer_group": "policy_rates", "transform": "level"}
    assert change_kind("ECB_DFR", meta) == "bps"


def test_abs_peer_group_returns_absolute():
    """sentiment → absolute (ESI is signed index)."""
    meta = {"peer_group": "sentiment", "transform": "level"}
    assert change_kind("EA_ESI", meta) == "absolute"


def test_unknown_peer_group_returns_percent():
    """hard_activity (level index) → percent change."""
    meta = {"peer_group": "hard_activity", "transform": "level"}
    assert change_kind("EA_IP", meta) == "percent"


def test_yoy_pct_transform_overrides_to_bps():
    """transform=yoy_pct → bps (delta of rate is in bps), регardless of peer_group."""
    meta = {"peer_group": "balance_sheet", "transform": "yoy_pct"}
    assert change_kind("ECB_BALANCE_SHEET", meta) == "bps"


def test_qoq_pct_transform_returns_bps():
    meta = {"peer_group": "hard_activity", "transform": "qoq_pct"}
    assert change_kind("EA_GDP_QOQ", meta) == "bps"


def test_mom_pct_transform_returns_bps():
    meta = {"peer_group": "hard_activity", "transform": "mom_pct"}
    assert change_kind("ANY", meta) == "bps"


def test_sids_override_takes_precedence():
    """BPS_SIDS_OVERRIDE override-ва peer_group."""
    # Inject test-only override чрез monkey-patch (BPS_SIDS_OVERRIDE е set, mutable)
    from core import display as display_mod
    display_mod.BPS_SIDS_OVERRIDE.add("TEST_OVERRIDE")
    try:
        meta = {"peer_group": "hard_activity", "transform": "level"}  # would be percent
        assert change_kind("TEST_OVERRIDE", meta) == "bps"
    finally:
        display_mod.BPS_SIDS_OVERRIDE.discard("TEST_OVERRIDE")


def test_no_meta_defaults_to_percent():
    assert change_kind("UNKNOWN", {}) == "percent"


# ── EU peer group classification ───────────────────────────────

def test_eu_inflation_series_are_bps():
    """HICP YoY series → bps (already in % units)."""
    for pg in ("headline_measures", "core_measures", "expectations"):
        assert pg in BPS_PEER_GROUPS, f"{pg} should be BPS"


def test_eu_credit_series_are_bps():
    """Bank lending growth, M3 YoY, sovereign yields → bps."""
    for pg in ("monetary_aggregates", "bank_lending", "sovereign_yields"):
        assert pg in BPS_PEER_GROUPS


def test_eu_sentiment_series_are_absolute():
    """ESI, sectoral confidence, CISS → absolute."""
    for pg in ("sentiment", "labor_sentiment", "financial_stress"):
        assert pg in ABS_PEER_GROUPS


# ── compute_change ─────────────────────────────────────────────

def test_compute_change_percent_returns_pct_change_in_percent():
    s = pd.Series([100.0, 102.0, 105.0],
                  index=pd.date_range("2024-01-01", periods=3, freq="MS"))
    ch = compute_change(s, "percent", periods=1)
    # last = (105-102)/102 * 100 = +2.94%
    assert ch.iloc[-1] == pytest.approx((105.0 - 102.0) / 102.0 * 100, abs=0.01)


def test_compute_change_bps_multiplies_diff_by_100():
    """diff(periods)*100 → 1pp = 100bps."""
    s = pd.Series([2.00, 2.20, 2.10],
                  index=pd.date_range("2024-01-01", periods=3, freq="MS"))
    ch = compute_change(s, "bps", periods=1)
    # last diff = 2.10 - 2.20 = -0.10 → -10 bps
    assert ch.iloc[-1] == pytest.approx(-10.0)


def test_compute_change_absolute_returns_raw_diff():
    s = pd.Series([95.0, 93.0, 91.0],
                  index=pd.date_range("2024-01-01", periods=3, freq="MS"))
    ch = compute_change(s, "absolute", periods=1)
    assert ch.iloc[-1] == pytest.approx(-2.0)


def test_compute_change_empty_series_returns_empty():
    s = pd.Series([], dtype=float)
    ch = compute_change(s, "percent", periods=1)
    assert ch.empty


def test_compute_change_zero_periods_returns_all_nan():
    """periods=0 е no-op; pct_change връща all-NaN result, latest_change → None."""
    s = pd.Series([1.0, 2.0, 3.0], index=pd.date_range("2024-01-01", periods=3, freq="MS"))
    result = compute_change(s, "percent", periods=0)
    # Or empty series, or all-NaN series — both are "no signal"
    assert result.dropna().empty


# ── latest_change ──────────────────────────────────────────────

def test_latest_change_returns_last_valid():
    s = pd.Series([2.00, 2.20, 2.10],
                  index=pd.date_range("2024-01-01", periods=3, freq="MS"))
    assert latest_change(s, "bps", periods=1) == pytest.approx(-10.0)


def test_latest_change_handles_nan():
    import numpy as np
    s = pd.Series([2.0, 2.5, np.nan],
                  index=pd.date_range("2024-01-01", periods=3, freq="MS"))
    # last non-NaN delta = 2.5 - 2.0 = 0.5 → 50 bps
    val = latest_change(s, "bps", periods=1)
    assert val == pytest.approx(50.0)


def test_latest_change_empty_returns_none():
    assert latest_change(pd.Series([], dtype=float), "percent", 1) is None


# ── fmt_change ─────────────────────────────────────────────────

def test_fmt_change_percent():
    assert fmt_change(2.5, "percent") == "+2.50%"
    assert fmt_change(-1.234, "percent") == "-1.23%"


def test_fmt_change_bps():
    assert fmt_change(25.4, "bps") == "+25 bps"
    assert fmt_change(-5.7, "bps") == "-6 bps"


def test_fmt_change_absolute():
    assert fmt_change(0.20, "absolute") == "+0.20"
    assert fmt_change(-3.30, "absolute") == "-3.30"


def test_fmt_change_none_returns_dash():
    assert fmt_change(None, "percent") == "—"
    assert fmt_change(float("nan"), "bps") == "—"


# ── fmt_value ──────────────────────────────────────────────────

def test_fmt_value_default_3_digits():
    assert fmt_value(22667.30) == "22667.300"


def test_fmt_value_custom_digits():
    assert fmt_value(2.0, digits=2) == "2.00"


def test_fmt_value_none():
    assert fmt_value(None) == "—"


# ── period labels ─────────────────────────────────────────────

def test_short_period_label_known():
    assert short_period_label(252) == "1д"
    assert short_period_label(52) == "1с"
    assert short_period_label(12) == "1м"
    assert short_period_label(4) == "1кв"


def test_short_period_label_unknown_defaults_monthly():
    assert short_period_label(99) == "1м"


def test_long_period_label_always_year():
    assert long_period_label() == "1г"


def test_change_header_formats():
    assert change_header("percent", "1г") == "1г %"
    assert change_header("bps", "1м") == "Δ1м bps"
    assert change_header("absolute", "1кв") == "Δ1кв"


# ── Integration: real EU catalog series ───────────────────────

def test_real_catalog_series_get_correct_kind():
    """Smoke test срещу реалния EU каталог."""
    from catalog.series import SERIES_CATALOG

    # Известни expected kind-ове
    expectations = {
        "EA_HICP_HEADLINE":  "bps",   # rate (YoY %)
        "EA_HICP_CORE":      "bps",
        "EA_UNRATE":         "bps",   # already %
        "EA_LFS_EMP":        "bps",
        "EA_SPF_HICP_LT":    "bps",   # expectations rate
        "ECB_DFR":           "bps",   # policy rate
        "EA_BUND_10Y":       "bps",   # sovereign yield
        "EA_M3_YOY":         "bps",   # already YoY %
        "EA_BANK_LOANS_NFC": "bps",
        "EA_CISS":           "absolute",   # signed index
        "EA_ESI":            "absolute",   # sentiment balance
        "EA_INDUSTRY_CONF":  "absolute",
        "EA_CONSUMER_CONF":  "absolute",
        "EA_EMPLOYMENT_EXP": "absolute",
        "EA_IP":             "bps",   # transform=yoy_pct → rate
        "EA_RETAIL_VOL":     "bps",   # transform=yoy_pct
        "EA_GDP_QOQ":        "bps",   # transform=qoq_pct
        "ECB_BALANCE_SHEET": "bps",   # transform=yoy_pct
        "EA_PERMIT_DW":      "bps",   # transform=yoy_pct
    }

    for sid, expected in expectations.items():
        if sid not in SERIES_CATALOG:
            continue  # skip if not in catalog (defensive)
        meta = SERIES_CATALOG[sid]
        kind = change_kind(sid, meta)
        assert kind == expected, f"{sid}: expected {expected}, got {kind} (peer={meta.get('peer_group')}, transform={meta.get('transform')})"
