"""
core/display.py
================
Display-by-type — единен източник за това КАК да се покаже промяна на серия.

% change няма смисъл за rate-level (HICP YoY, ECB rates, sovereign yields) и
signed-index серии (CISS, ESI, sentiment confidence). За тях показваме
basis points (за rates) или absolute delta (за signed indices).
За level series (price index, count) — % както е стандарт.

Решението е по `peer_group` от каталога + transform-aware override:
  - peer_group ∈ BPS_PEER_GROUPS → bps
  - peer_group ∈ ABS_PEER_GROUPS → absolute
  - transform ∈ {"yoy_pct","mom_pct","qoq_pct"} → bps (delta of % е в bps)
  - sid ∈ BPS_SIDS_OVERRIDE → bps
  - default → percent

Public API:
    change_kind(sid, meta) -> "percent" | "bps" | "absolute"
    compute_change(series, kind, periods) -> pd.Series
    fmt_change(value, kind) -> str
    fmt_value(value, digits) -> str
    short_period_label(periods) -> str  # "1д" / "1с" / "1м" / "1кв"
    long_period_label() -> str          # "1г"
    change_header(kind, period_lbl) -> str  # "Δ1г bps" / "1г %" / "Δ1м"
"""
from __future__ import annotations

import math
from typing import Optional

import pandas as pd


# ============================================================
# CLASSIFICATION (EU-specific peer groups от catalog/series.py)
# ============================================================

# Peer groups със стойности в rate units (%, около 0-10) — Δ в bps
BPS_PEER_GROUPS = {
    # Inflation & expectations
    "headline_measures",      # EA_HICP_HEADLINE (YoY %)
    "core_measures",          # EA_HICP_CORE, EA_HICP_SERVICES (YoY %)
    "expectations",           # EA_SPF_HICP_LT (long-term inflation forecast %)
    # Rates
    "policy_rates",           # ECB_DFR, ECB_MRO, ECB_MLF (%)
    "sovereign_yields",       # EA_BUND_10Y/2Y, IT_10Y, FR_10Y, DE_10Y (%)
    # Labor
    "unemployment",           # EA_UNRATE (%)
    "employment",             # EA_LFS_EMP (% of population)
    # Money & credit (already YoY rates)
    "monetary_aggregates",    # EA_M3_YOY (YoY %)
    "bank_lending",           # EA_BANK_LOANS_NFC, EA_BANK_LOANS_HH (YoY %)
    # Term structure (derived spreads)
    "term_structure",         # 10Y-2Y, BTP-Bund (pp = bps)
    "credit_spreads",         # sovereign spreads (pp = bps)
}

# Peer groups със signed индекси (около 0) или 0-100 sentiment — absolute Δ
ABS_PEER_GROUPS = {
    "sentiment",              # EA_ESI, EA_INDUSTRY_CONF, EA_CONSTRUCTION_CONF, etc.
    "labor_sentiment",        # EA_EMPLOYMENT_EXP (balance index)
    "financial_stress",       # EA_CISS (0-1 stress index)
}

# Series-override: sid-level прецедент над peer_group default
BPS_SIDS_OVERRIDE: set[str] = set()
# Empty за v1; може да добавим ако някоя серия има non-standard peer


# Transform-ите които превръщат level в rate (delta of result е в bps)
RATE_TRANSFORMS = {"yoy_pct", "mom_pct", "qoq_pct"}


def change_kind(sid: str, meta: dict) -> str:
    """Връща 'percent' | 'bps' | 'absolute' за дадена серия.

    Приоритет (по ред на проверка):
      1. BPS_SIDS_OVERRIDE — explicit override
      2. transform ∈ RATE_TRANSFORMS → "bps" (delta of rate)
      3. peer_group ∈ BPS_PEER_GROUPS → "bps"
      4. peer_group ∈ ABS_PEER_GROUPS → "absolute"
      5. default → "percent"
    """
    if sid in BPS_SIDS_OVERRIDE:
        return "bps"
    transform = meta.get("transform", "level")
    if transform in RATE_TRANSFORMS:
        return "bps"
    pg = meta.get("peer_group", "")
    if pg in BPS_PEER_GROUPS:
        return "bps"
    if pg in ABS_PEER_GROUPS:
        return "absolute"
    return "percent"


# ============================================================
# CHANGE COMPUTATION
# ============================================================

def compute_change(series: pd.Series, kind: str, periods: int) -> pd.Series:
    """Изчислява промяна за дадена серия и kind.

    - "percent":  pct_change(periods) * 100  (вече в %, 10.0 = 10%)
    - "bps":      diff(periods) * 100         (1.0 pp = 100 bps)
    - "absolute": diff(periods)               (raw delta)
    """
    s = series.dropna()
    if s.empty or periods <= 0:
        return pd.Series(dtype=float, index=series.index)
    if kind == "percent":
        return s.pct_change(periods=periods) * 100
    if kind == "bps":
        return s.diff(periods=periods) * 100
    # absolute
    return s.diff(periods=periods)


def latest_change(series: pd.Series, kind: str, periods: int) -> Optional[float]:
    """Последната не-NaN стойност на change(series, kind, periods)."""
    ch = compute_change(series, kind, periods)
    if ch.empty:
        return None
    valid = ch.dropna()
    if valid.empty:
        return None
    return float(valid.iloc[-1])


# ============================================================
# FORMATTING
# ============================================================

def _is_finite_number(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f


def fmt_change(value, kind: str) -> str:
    """Форматира промяна в правилните units. Връща '—' за NaN/None."""
    f = _is_finite_number(value)
    if f is None:
        return "—"
    if kind == "percent":
        return f"{f:+.2f}%"
    if kind == "bps":
        return f"{f:+.0f} bps"
    return f"{f:+.2f}"


def fmt_value(value, digits: int = 3) -> str:
    """Форматира raw стойност на серия (без знак)."""
    f = _is_finite_number(value)
    if f is None:
        return "—"
    return f"{f:.{digits}f}"


# ============================================================
# PERIOD LABELS
# ============================================================

def short_period_label(periods: int) -> str:
    """Bulgarian abbreviation за short delta period (1d/1w/1m/1q)."""
    return {252: "1д", 52: "1с", 12: "1м", 4: "1кв"}.get(periods, "1м")


def long_period_label(periods: int = 0) -> str:  # noqa: ARG001
    """Long delta винаги е 1 година."""
    return "1г"


def change_header(kind: str, period_lbl: str) -> str:
    """Header за колона с промяна (напр. 'Δ1г bps', '1м %', 'Δ1д')."""
    if kind == "percent":
        return f"{period_lbl} %"
    if kind == "bps":
        return f"Δ{period_lbl} bps"
    return f"Δ{period_lbl}"
