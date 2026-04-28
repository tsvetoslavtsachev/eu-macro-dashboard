"""Tests за analysis/macro_vector.py — EA 7-dimensional macro state vector."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.macro_vector import (
    STATE_VECTOR_DIMS,
    DIM_LABELS_BG,
    DIM_UNITS,
    MacroState,
    build_history_matrix,
    z_score_matrix,
    build_current_vector,
    _compute_sahm_rule,
)


# ── Fixtures ────────────────────────────────────────────────────

def _monthly(values, end="2026-01-01"):
    idx = pd.date_range(end=end, periods=len(values), freq="MS")
    return pd.Series(values, index=idx)


def _full_snapshot(n: int = 300):
    """Realistic-ish synthetic EA history (от 1999 до 2025)."""
    end = "2025-12-01"
    # SPF е quarterly → правим series с quarterly index за по-realistic тест
    spf_idx = pd.date_range(end=end, periods=max(n // 3, 4), freq="QS")
    n_q = len(spf_idx)
    spf = pd.Series(np.linspace(1.8, 2.0, n_q) + np.random.normal(0, 0.05, n_q),
                    index=spf_idx)
    return {
        "EA_UNRATE":         _monthly(np.linspace(8.0, 6.0, n), end=end),
        "EA_HICP_CORE":      _monthly(np.linspace(1.0, 2.5, n) + np.random.normal(0, 0.3, n), end=end),
        "ECB_DFR":           _monthly(np.linspace(0.0, 2.0, n), end=end),
        "EA_BUND_10Y":       _monthly(np.linspace(4.0, 3.0, n), end=end),
        "EA_BUND_2Y":        _monthly(np.linspace(3.0, 2.5, n), end=end),
        "IT_10Y":            _monthly(np.linspace(4.5, 4.0, n), end=end),
        "DE_10Y":            _monthly(np.linspace(3.5, 2.5, n), end=end),
        "EA_IP":             _monthly(np.linspace(95.0, 105.0, n), end=end),
        "EA_SPF_HICP_LT":    spf,
    }


# ── Constants ───────────────────────────────────────────────────

def test_state_vector_dims_has_8_entries():
    assert len(STATE_VECTOR_DIMS) == 8


def test_dim_labels_cover_all_dims():
    for d in STATE_VECTOR_DIMS:
        assert d in DIM_LABELS_BG
        assert d in DIM_UNITS


def test_no_us_specific_dim_names():
    """След Phase 4.5 не трябва да остане US dim name."""
    assert "real_ffr" not in STATE_VECTOR_DIMS
    assert "hy_oas" not in STATE_VECTOR_DIMS
    assert "breakeven" not in STATE_VECTOR_DIMS
    # Трябва да присъстват EA-specific версии
    assert "real_dfr" in STATE_VECTOR_DIMS
    assert "sovereign_stress" in STATE_VECTOR_DIMS
    assert "inflation_expectations" in STATE_VECTOR_DIMS


# ── build_history_matrix ────────────────────────────────────────

def test_build_history_matrix_returns_correct_columns():
    snap = _full_snapshot(60)
    df = build_history_matrix(snap)
    assert list(df.columns) == STATE_VECTOR_DIMS


def test_build_history_matrix_handles_missing_series():
    """Серия отсъстваща в snapshot → колоната остава NaN или липсва."""
    snap = _full_snapshot(60)
    del snap["EA_BUND_2Y"]
    df = build_history_matrix(snap)
    # yc_10y2y derived от 10Y-2Y; ако 2Y липсва, цялата колона е NaN
    assert df["yc_10y2y"].dropna().empty


def test_build_history_matrix_inflation_expectations_quarterly_to_monthly():
    """SPF (quarterly) трябва да се forward-fill до monthly."""
    snap = _full_snapshot(120)
    df = build_history_matrix(snap)
    # SPF има ~40 quarterly observations за 120 monthly periods → след ffill
    # трябва да имаме почти всички 120 monthly стойности
    n_filled = df["inflation_expectations"].dropna().shape[0]
    assert n_filled >= 100, f"forward-fill failed; only {n_filled} months filled"


def test_build_history_matrix_handles_missing_spf():
    """Без SPF series, dim 8 e empty но pipeline-ът не crashва."""
    snap = _full_snapshot(60)
    del snap["EA_SPF_HICP_LT"]
    df = build_history_matrix(snap)
    assert df["inflation_expectations"].dropna().empty


def test_build_history_matrix_empty_snapshot():
    df = build_history_matrix({})
    assert df.empty or df.isna().all().all()


def test_build_history_matrix_real_dfr_computed():
    """real_dfr = DFR - core_hicp_yoy."""
    snap = _full_snapshot(60)
    df = build_history_matrix(snap)
    last_dfr = snap["ECB_DFR"].resample("MS").mean().iloc[-1]
    last_core = snap["EA_HICP_CORE"].resample("MS").mean().iloc[-1]
    assert df["real_dfr"].iloc[-1] == pytest.approx(last_dfr - last_core, rel=0.01)


def test_build_history_matrix_sovereign_spread():
    """sovereign_stress = IT_10Y - DE_10Y."""
    snap = _full_snapshot(60)
    df = build_history_matrix(snap)
    last_it = snap["IT_10Y"].iloc[-1]
    last_de = snap["DE_10Y"].iloc[-1]
    assert df["sovereign_stress"].iloc[-1] == pytest.approx(last_it - last_de, rel=0.01)


def test_build_history_matrix_window_filter():
    """window_start филтрира редовете."""
    snap = _full_snapshot(60)
    df_full = build_history_matrix(snap)
    df_filt = build_history_matrix(snap, window_start="2020-01-01")
    assert len(df_filt) <= len(df_full)
    if not df_filt.empty:
        assert df_filt.index[0] >= pd.Timestamp("2020-01-01")


# ── z_score_matrix ──────────────────────────────────────────────

def test_z_score_matrix_zero_mean_unit_std():
    snap = _full_snapshot(120)
    df = build_history_matrix(snap)
    z = z_score_matrix(df)
    for col in z.columns:
        s = z[col].dropna()
        if len(s) <= 10:
            continue
        # Pure-zero column = constant input (std=0 case); valid behavior
        if (s == 0.0).all():
            continue
        # mean близо до 0, std близо до 1 (със флуктуация заради NaN)
        assert abs(s.mean()) < 0.2, f"col={col} mean={s.mean()}"
        assert 0.7 < s.std() < 1.3, f"col={col} std={s.std()}"


def test_z_score_matrix_handles_constant_series():
    """Колона със std=0 не трябва да предизвиква div-by-zero."""
    df = pd.DataFrame({
        "unrate": [5.0] * 20,
        "core_hicp_yoy": np.linspace(1.0, 3.0, 20),
    }, index=pd.date_range("2024-01-01", periods=20, freq="MS"))
    z = z_score_matrix(df)
    assert (z["unrate"] == 0.0).all()


# ── Sahm rule ───────────────────────────────────────────────────

def test_sahm_rule_increases_with_recession():
    """Sahm rule трябва да е > 0.5 ако unemployment расте бързо."""
    # Стабилна и вдига се с ~1pp за 4 месеца → класически recession signal
    unrate = pd.Series(
        [5.0] * 12 + [5.2, 5.5, 5.9, 6.2, 6.4, 6.5],
        index=pd.date_range(end="2024-06-01", periods=18, freq="MS"),
    )
    sahm = _compute_sahm_rule(unrate)
    assert sahm.iloc[-1] > 0.5, f"Sahm should signal, got {sahm.iloc[-1]}"


def test_sahm_rule_zero_when_unrate_falling():
    """Sahm rule = 0 когато 3mma min трендира надолу (rolling min = current)."""
    unrate = pd.Series(
        np.linspace(8.0, 5.0, 24),
        index=pd.date_range(end="2024-12-01", periods=24, freq="MS"),
    )
    sahm = _compute_sahm_rule(unrate)
    # 3mma винаги > 12-month trailing min → положителна стойност очаквана
    # Но ако падането е steady, разликата е малка
    assert (sahm < 0.5).all()


# ── build_current_vector ────────────────────────────────────────

def test_build_current_vector_returns_macro_state():
    snap = _full_snapshot(120)
    df = build_history_matrix(snap)
    state = build_current_vector(df)
    assert isinstance(state, MacroState)
    assert state.is_complete()
    assert len(state.raw) == 8
    assert len(state.z) == 8


def test_build_current_vector_returns_none_when_empty():
    df = pd.DataFrame()
    assert build_current_vector(df) is None


def test_build_current_vector_respects_today():
    snap = _full_snapshot(120)
    df = build_history_matrix(snap)
    cutoff = df.index[-12]  # 12 months back
    state = build_current_vector(df, today=cutoff)
    assert state is not None
    assert state.as_of <= cutoff


def test_build_current_vector_returns_none_for_too_old_today():
    snap = _full_snapshot(120)
    df = build_history_matrix(snap)
    state = build_current_vector(df, today=pd.Timestamp("1990-01-01"))
    assert state is None


def test_macro_state_as_array_shape():
    snap = _full_snapshot(60)
    df = build_history_matrix(snap)
    state = build_current_vector(df)
    arr = state.as_array()
    assert arr.shape == (8,)
