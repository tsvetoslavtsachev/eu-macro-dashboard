"""Tests за analysis/cross_spreads.py — Phase 8 methodology subsystem."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.cross_spreads import (
    compute_real_dfr_forward,
    compute_real_growth_series,
    compute_yield_curve_spread,
    compute_sovereign_stress_spreads,
    assess_anchored_band,
    ppi_cpi_lead_lag,
    AnchoredBandAssessment,
    CurveSpreadResult,
    RealRateResult,
    LeadLagResult,
)


# ── Fixtures ──────────────────────────────────────────────────

def monthly(values: list[float], end: str = "2026-04-01") -> pd.Series:
    idx = pd.date_range(end=end, periods=len(values), freq="MS")
    return pd.Series(values, index=idx)


def quarterly(values: list[float], end: str = "2026-04-01") -> pd.Series:
    idx = pd.date_range(end=end, periods=len(values), freq="QS")
    return pd.Series(values, index=idx)


# ── compute_real_dfr_forward ──────────────────────────────────

def test_real_dfr_forward_basic():
    snap = {
        "ECB_DFR": monthly([2.0, 2.0, 2.0]),
        "EA_SPF_HICP_LT": quarterly([1.9, 2.0, 2.0]),
    }
    r = compute_real_dfr_forward(snap)
    assert r is not None
    assert r.nominal_rate == 2.0
    assert r.forward_inflation == 2.0
    assert r.real_rate == pytest.approx(0.0, abs=0.001)


def test_real_dfr_forward_restrictive():
    snap = {
        "ECB_DFR": monthly([3.0]),
        "EA_SPF_HICP_LT": quarterly([2.0]),
    }
    r = compute_real_dfr_forward(snap)
    assert r.real_rate == pytest.approx(1.0)
    assert r.is_restrictive is True


def test_real_dfr_forward_returns_none_if_missing():
    assert compute_real_dfr_forward({}) is None
    assert compute_real_dfr_forward({"ECB_DFR": monthly([2.0])}) is None


# ── compute_real_growth_series ────────────────────────────────

def test_real_growth_series_subtracts_deflator():
    nom = monthly([5.0, 5.0, 5.0, 5.0])
    deflator = monthly([2.0, 2.0, 2.0, 2.0])
    real = compute_real_growth_series(nom, deflator)
    assert not real.empty
    assert real.iloc[-1] == pytest.approx(3.0)


def test_real_growth_handles_quarterly_deflator():
    """Monthly nominal + quarterly deflator → forward-fill alignment."""
    nom = monthly([4.0] * 12)
    deflator = quarterly([2.0] * 4)
    real = compute_real_growth_series(nom, deflator)
    # След ffill, всеки месец трябва да има real = 4 - 2 = 2
    assert not real.empty
    assert real.iloc[-1] == pytest.approx(2.0)


def test_real_growth_empty_inputs():
    assert compute_real_growth_series(pd.Series(dtype=float), monthly([2.0])).empty
    assert compute_real_growth_series(monthly([2.0]), pd.Series(dtype=float)).empty


# ── compute_yield_curve_spread ────────────────────────────────

def test_yield_curve_spread_normal():
    snap = {
        "EA_BUND_10Y": monthly([3.0, 3.5, 3.5]),
        "EA_BUND_2Y":  monthly([2.0, 2.5, 2.5]),
    }
    r = compute_yield_curve_spread(snap)
    assert r is not None
    assert r.spread_pp == pytest.approx(1.0)
    assert r.spread_bps == pytest.approx(100.0)
    assert r.is_inverted is False


def test_yield_curve_spread_inverted():
    snap = {
        "EA_BUND_10Y": monthly([2.0]),
        "EA_BUND_2Y":  monthly([3.0]),
    }
    r = compute_yield_curve_spread(snap)
    assert r.spread_pp == pytest.approx(-1.0)
    assert r.is_inverted is True


def test_yield_curve_spread_returns_none_if_missing():
    assert compute_yield_curve_spread({}) is None


# ── compute_sovereign_stress_spreads ──────────────────────────

def test_sovereign_spreads_btp_oat():
    snap = {
        "DE_10Y": monthly([2.0, 2.0]),
        "IT_10Y": monthly([5.0, 5.5]),
        "FR_10Y": monthly([2.5, 3.0]),
    }
    spreads = compute_sovereign_stress_spreads(snap)
    assert spreads["EA_BTP_BUND_SPREAD"] == pytest.approx(3.5)
    assert spreads["EA_OAT_BUND_SPREAD"] == pytest.approx(1.0)


def test_sovereign_spreads_no_de_returns_empty():
    snap = {"IT_10Y": monthly([5.0])}
    assert compute_sovereign_stress_spreads(snap) == {}


def test_sovereign_spreads_only_one_country():
    snap = {"DE_10Y": monthly([2.0]), "IT_10Y": monthly([5.0])}
    spreads = compute_sovereign_stress_spreads(snap)
    assert "EA_BTP_BUND_SPREAD" in spreads
    assert "EA_OAT_BUND_SPREAD" not in spreads


# ── assess_anchored_band ──────────────────────────────────────

def test_anchored_band_tight():
    """Value близо до mean (1.91) → tightly_anchored."""
    r = assess_anchored_band(1.92, "EA_SPF_HICP_LT")
    assert r is not None
    assert r.state == "tightly_anchored"
    assert abs(r.distance_from_mean) < 0.5


def test_anchored_band_anchored():
    """Value в ±1σ band (но beyond ±0.5σ) → anchored.

    mean=1.91, std=0.13. 2.00 → distance 0.09 ≈ 0.69σ → anchored.
    """
    r = assess_anchored_band(2.00, "EA_SPF_HICP_LT")
    assert r.state == "anchored"


def test_anchored_band_drifting():
    """Value beyond ±1σ but within ±2σ → drifting.

    mean=1.91, std=0.13. 2.10 → distance 0.19 ≈ 1.46σ → drifting.
    """
    r = assess_anchored_band(2.10, "EA_SPF_HICP_LT")
    assert r.state == "drifting"


def test_anchored_band_de_anchored():
    """Value beyond ±2σ → de_anchored."""
    r = assess_anchored_band(2.50, "EA_SPF_HICP_LT")
    assert r.state == "de_anchored"


def test_anchored_band_unknown_sid_returns_none():
    assert assess_anchored_band(2.0, "UNKNOWN_SERIES") is None


def test_anchored_band_with_5y_percentile():
    """Percentile се изчислява от 5y rolling window."""
    # 20 quarterly readings = 5 години
    series = quarterly([1.8, 1.85, 1.9, 1.95, 2.0] * 4, end="2026-01-01")
    r = assess_anchored_band(2.05, "EA_SPF_HICP_LT", series=series)
    assert r.percentile_5y is not None
    assert 0 <= r.percentile_5y <= 100


# ── ppi_cpi_lead_lag ──────────────────────────────────────────

def test_ppi_cpi_lead_lag_returns_full_result():
    """Sanity test: при достатъчно история функцията връща result с всички lag-ове."""
    n_months = 120
    np.random.seed(42)
    # PPI level расте от 100 до 130 за 10 години → стабилен YoY ~3%
    ppi_raw = pd.Series(
        np.cumsum(np.random.randn(n_months) * 0.5) + np.linspace(100, 130, n_months),
        index=pd.date_range(end="2026-04-01", periods=n_months, freq="MS"),
    )
    cpi = pd.Series(
        np.linspace(1.0, 3.0, n_months) + np.random.randn(n_months) * 0.5,
        index=ppi_raw.index,
    )

    snap = {"EA_PPI_INTERMEDIATE": ppi_raw, "EA_HICP_CORE": cpi}
    r = ppi_cpi_lead_lag(snap, lags=(0, 3, 6, 9, 12))
    assert r is not None
    assert r.leader_sid == "EA_PPI_INTERMEDIATE"
    assert r.lagger_sid == "EA_HICP_CORE"
    # Всички lag-ове трябва да дадат correlation
    assert set(r.correlations.keys()) == {0, 3, 6, 9, 12}
    assert r.best_lag in r.correlations
    assert r.best_corr == r.correlations[r.best_lag]


def test_ppi_cpi_lead_lag_returns_none_if_missing():
    assert ppi_cpi_lead_lag({}) is None
    assert ppi_cpi_lead_lag({"EA_PPI_INTERMEDIATE": monthly([100.0] * 36)}) is None


def test_ppi_cpi_lead_lag_skips_short_overlap():
    """Ако overlap < 24 месеца, lag-ът се пропуска."""
    short_ppi = monthly([100.0 + i * 0.5 for i in range(20)])  # 20 obs
    short_cpi = monthly([2.0] * 20)
    r = ppi_cpi_lead_lag({"EA_PPI_INTERMEDIATE": short_ppi, "EA_HICP_CORE": short_cpi})
    # След pct_change(12), PPI има 8 obs → < 24 threshold → empty result
    assert r is None
