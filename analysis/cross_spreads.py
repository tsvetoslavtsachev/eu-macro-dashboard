"""
analysis/cross_spreads.py
==========================
Phase 8 — Methodology subsystem: derived numbers за cross-lens thesis testing.

Функции:
  - compute_real_dfr_forward: real policy rate vs forward inflation
  - compute_real_growth_series: deflate nominal с HICP core
  - compute_yield_curve_spread: 10Y-2Y curve в bps
  - compute_sovereign_stress_spreads: BTP-Bund, OAT-Bund + bps conversion
  - assess_anchored_band: classify SPF vs empirical anchored zones
  - ppi_cpi_lead_lag: PPI nonenergy → core HICP correlation 0/3/6 mo lag

Convention:
  - Spreads се връщат в **percentage points** (pp), не в bps,
    защото catalog series вече са в %. bps формат се прави в display layer.
  - Real rates = nominal − inflation (subtraction, NOT (1+r)/(1+π)−1 — близо до zero).
  - Forward-fill за quarterly SPF когато се join-ва с monthly DFR.

Pattern: pure functions, snapshot in → dict / float out. Без side effects.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from config import (
    ANCHORED_ZONES,
    NOMINAL_SERIES_NEED_DEFLATION,
    CORE_DEFLATOR_KEY,
    POLICY_RATE_KEY,
    FORWARD_INFL_KEY,
    NOMINAL_10Y_KEY,
    NOMINAL_2Y_KEY,
)


# ============================================================
# Types
# ============================================================

@dataclass
class AnchoredBandAssessment:
    """Resultat от assess_anchored_band."""
    sid: str
    value: float
    state: str            # "tightly_anchored" | "anchored" | "drifting" | "de_anchored"
    distance_from_mean: float  # in σ units
    percentile_5y: Optional[float]  # 5-year rolling percentile (None ако недостатъчно история)
    band_mean: float
    band_std: float
    narrative_bg: str


@dataclass
class CurveSpreadResult:
    """Resultat от compute_yield_curve_spread."""
    sid_long: str
    sid_short: str
    spread_pp: float       # 10Y - 2Y в percentage points
    spread_bps: float      # × 100 (за display)
    last_date: pd.Timestamp
    is_inverted: bool      # True ако spread < 0


@dataclass
class RealRateResult:
    """Resultat от compute_real_dfr_forward."""
    nominal_rate: float    # ECB_DFR latest
    forward_inflation: float  # SPF LT latest
    real_rate: float       # nominal - forward
    nominal_date: pd.Timestamp
    forward_date: pd.Timestamp
    is_restrictive: bool   # real rate > 0 (above neutral assumption)


@dataclass
class LeadLagResult:
    """Resultat от ppi_cpi_lead_lag."""
    leader_sid: str
    lagger_sid: str
    correlations: dict[int, float]  # {lag_months: correlation}
    best_lag: int
    best_corr: float


# ============================================================
# Real rates
# ============================================================

def compute_real_dfr_forward(snapshot: dict[str, pd.Series]) -> Optional[RealRateResult]:
    """Real policy rate vs forward inflation expectation.

    real_rate = ECB_DFR − EA_SPF_HICP_LT (latest values).

    SPF е quarterly, DFR daily/weekly — взимаме latest от всеки.
    Returns None ако някоя серия липсва.
    """
    dfr = snapshot.get(POLICY_RATE_KEY)
    spf = snapshot.get(FORWARD_INFL_KEY)

    if dfr is None or dfr.empty or spf is None or spf.empty:
        return None

    nominal = float(dfr.iloc[-1])
    forward = float(spf.iloc[-1])
    real = nominal - forward

    return RealRateResult(
        nominal_rate=nominal,
        forward_inflation=forward,
        real_rate=real,
        nominal_date=dfr.index[-1],
        forward_date=spf.index[-1],
        is_restrictive=real > 0.5,  # > 50bp над forward inflation = restrictive
    )


def compute_real_growth_series(
    nominal: pd.Series,
    deflator: pd.Series,
) -> pd.Series:
    """Deflate nominal series с дефлатор YoY%.

    Args:
        nominal: pd.Series с YoY% values (e.g., wage growth %)
        deflator: pd.Series с YoY% values (e.g., HICP core %)

    Returns:
        Real growth series (pp, monthly aligned). Дефлаторът се forward-fill-ва
        ако е по-рядък.
    """
    if nominal.empty or deflator.empty:
        return pd.Series(dtype=float)

    # Align frequencies — резолюцията е на по-рядката серия
    aligned = pd.concat([nominal, deflator], axis=1, join="inner").ffill()
    aligned.columns = ["nom", "def_"]
    aligned = aligned.dropna()

    if aligned.empty:
        # Quarterly deflator + monthly nominal: reindex deflator
        merged = pd.concat([nominal.rename("nom"), deflator.rename("def_")], axis=1)
        merged["def_"] = merged["def_"].ffill()
        merged = merged.dropna()
        if merged.empty:
            return pd.Series(dtype=float)
        return (merged["nom"] - merged["def_"]).rename("real")

    return (aligned["nom"] - aligned["def_"]).rename("real")


# ============================================================
# Yield curve
# ============================================================

def compute_yield_curve_spread(
    snapshot: dict[str, pd.Series],
    long_key: str = NOMINAL_10Y_KEY,
    short_key: str = NOMINAL_2Y_KEY,
) -> Optional[CurveSpreadResult]:
    """10Y-2Y curve spread (default Bund 10Y - 2Y).

    Връща в pp (catalog convention) + bps (display).
    Inverted curve (< 0) = recession proxy.
    """
    long = snapshot.get(long_key)
    short = snapshot.get(short_key)

    if long is None or long.empty or short is None or short.empty:
        return None

    # Align dates
    aligned = pd.concat([long, short], axis=1, join="inner")
    if aligned.empty:
        return None

    aligned.columns = ["long", "short"]
    last_row = aligned.dropna().iloc[-1]
    spread = float(last_row["long"] - last_row["short"])

    return CurveSpreadResult(
        sid_long=long_key,
        sid_short=short_key,
        spread_pp=spread,
        spread_bps=spread * 100,
        last_date=aligned.dropna().index[-1],
        is_inverted=spread < 0,
    )


# ============================================================
# Sovereign stress (already в catalog като derived series; this е API helper)
# ============================================================

def compute_sovereign_stress_spreads(snapshot: dict[str, pd.Series]) -> dict[str, float]:
    """Latest BTP-Bund и OAT-Bund spreads в pp.

    Returns dict {SID: spread_pp}. Empty dict ако DE_10Y липсва.
    """
    de = snapshot.get("DE_10Y")
    if de is None or de.empty:
        return {}

    out: dict[str, float] = {}
    de_latest = float(de.iloc[-1])

    it = snapshot.get("IT_10Y")
    if it is not None and not it.empty:
        out["EA_BTP_BUND_SPREAD"] = float(it.iloc[-1]) - de_latest

    fr = snapshot.get("FR_10Y")
    if fr is not None and not fr.empty:
        out["EA_OAT_BUND_SPREAD"] = float(fr.iloc[-1]) - de_latest

    return out


# ============================================================
# Anchored band assessment
# ============================================================

def assess_anchored_band(
    value: float,
    sid: str,
    series: Optional[pd.Series] = None,
) -> Optional[AnchoredBandAssessment]:
    """Classify дали value е в anchored band за дадена серия.

    Args:
        value: текущо четене (float)
        sid: catalog key — трябва да присъства в config.ANCHORED_ZONES
        series: optional full pd.Series за percentile calculation

    Returns:
        AnchoredBandAssessment или None ако SID няма дефинирана band.
    """
    zone = ANCHORED_ZONES.get(sid)
    if zone is None:
        return None

    mean = zone["mean"]
    std = zone["std"]
    deviation = abs(value - mean)

    if deviation <= 0.5 * std:
        state = "tightly_anchored"
        narrative = f"{sid} = {value:.2f}% — в tight band [{zone['tight_band'][0]:.2f}, {zone['tight_band'][1]:.2f}], очакванията здраво закотвени."
    elif deviation <= std:
        state = "anchored"
        narrative = f"{sid} = {value:.2f}% — в anchored band [{zone['anchored_band'][0]:.2f}, {zone['anchored_band'][1]:.2f}] (±1σ)."
    elif deviation <= 2 * std:
        state = "drifting"
        narrative = f"{sid} = {value:.2f}% — drift (±1σ до ±2σ от историческия mean {mean:.2f}%). Watch list."
    else:
        state = "de_anchored"
        narrative = f"{sid} = {value:.2f}% — DE-ANCHORED (beyond ±2σ от {mean:.2f}%). ECB credibility risk."

    # 5-year rolling percentile
    p5y: Optional[float] = None
    if series is not None and not series.empty:
        last_date = series.index.max()
        five_yr_ago = last_date - pd.DateOffset(years=5)
        recent_5y = series.loc[five_yr_ago:]
        if len(recent_5y) >= 4:  # минимум 1 година quarterly
            rank = (recent_5y < value).sum() / len(recent_5y) * 100
            p5y = float(rank)

    return AnchoredBandAssessment(
        sid=sid,
        value=value,
        state=state,
        distance_from_mean=(value - mean) / std if std > 0 else 0.0,
        percentile_5y=p5y,
        band_mean=mean,
        band_std=std,
        narrative_bg=narrative,
    )


# ============================================================
# PPI-CPI lead-lag
# ============================================================

def ppi_cpi_lead_lag(
    snapshot: dict[str, pd.Series],
    ppi_key: str = "EA_PPI_INTERMEDIATE",
    cpi_key: str = "EA_HICP_CORE",
    lags: tuple[int, ...] = (0, 3, 6, 9, 12),
) -> Optional[LeadLagResult]:
    """Correlation на PPI (transformed YoY) срещу CPI (already YoY) при различни lag-ове.

    PPI YoY води CPI core typically с 3-6 месеца. Высок positive correlation
    при lag 3-6 потвърждава pipeline thesis.

    Args:
        snapshot: dict с raw series.
        ppi_key: PPI series (level index — функцията computes YoY internally).
        cpi_key: CPI series (already YoY %).
        lags: lag values в months за тестване.

    Returns:
        LeadLagResult или None ако серии липсват.
    """
    ppi_raw = snapshot.get(ppi_key)
    cpi = snapshot.get(cpi_key)

    if ppi_raw is None or ppi_raw.empty or cpi is None or cpi.empty:
        return None

    # Compute PPI YoY%
    ppi_yoy = ppi_raw.pct_change(periods=12).dropna() * 100
    if ppi_yoy.empty:
        return None

    correlations: dict[int, float] = {}
    for lag in lags:
        # Shift PPI напред (lag months) — i.e. PPI at t-lag → CPI at t
        ppi_shifted = ppi_yoy.shift(lag)
        joined = pd.concat([ppi_shifted, cpi], axis=1, join="inner").dropna()
        if len(joined) < 24:  # минимум 2 години overlap
            continue
        corr = float(joined.iloc[:, 0].corr(joined.iloc[:, 1]))
        if not np.isnan(corr):
            correlations[lag] = corr

    if not correlations:
        return None

    best_lag = max(correlations, key=lambda k: correlations[k])
    return LeadLagResult(
        leader_sid=ppi_key,
        lagger_sid=cpi_key,
        correlations=correlations,
        best_lag=best_lag,
        best_corr=correlations[best_lag],
    )
