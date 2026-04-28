"""
modules/ecb.py
==============
ECB monetary policy stance lens — НОВ EA-specific lens (без US аналог).

Phase 2: оценява policy rates (DFR/MRO/MLF) и balance sheet trend.
Phase 2.5+ ще добави TLTRO outstanding и derived measures (real DFR срещу
HICP core).

Convention:
  - composite измерва restrictiveness на policy stance
  - висок score = restrictive (висока DFR, свиващ се баланс)
  - нисък score = stimulative (нула или отрицателна DFR, експандиращ баланс)

Регими отразяват ECB stance:
  ВЕРОЯТНО ПРЕТЕГНАТА → НЕУТРАЛНА → УМЕРЕНО РЕСТРИКТИВНА → РЕСТРИКТИВНА → ПРОБЛЕМАТИЧНО ТЯСНА

Phase 2 НЕ изчислява real rate (изисква HICP join, което е cross-lens задача).

Pattern: snapshot interface.
"""
from __future__ import annotations
from typing import Any

import pandas as pd

from core.scorer import (
    score_series, build_sparkline, build_historical_context, get_regime,
)
from config import HISTORY_START


# ─── Catalog ─────────────────────────────────────────────────────
SERIES = {
    "ECB_DFR": {
        "label": "ЕЦБ Deposit Facility Rate (%)",
        "invert": False,        # висока DFR = restrictive (high score)
        "transform": "level",
    },
    "ECB_MRO": {
        "label": "ЕЦБ Main Refinancing Rate (%)",
        "invert": False,
        "transform": "level",
    },
    "ECB_BALANCE_SHEET": {
        "label": "ЕЦБ баланс — общи активи (YoY %)",
        # Catalog meta-та е transform=yoy_pct, но ECB SDW връща LEVEL.
        # Тук transform-ваме явно. invert=True защото свиващ се баланс
        # (отрицателен YoY%) = restrictive (high stance score).
        "invert": True,
        "transform": "yoy_pct",
    },
}

# DFR доминира stance signal-а; balance sheet е secondary; MRO е tertiary
# (след 2014 е largely symbolic, DFR е binding rate).
COMPOSITE_SERIES  = ["ECB_DFR", "ECB_BALANCE_SHEET", "ECB_MRO"]
COMPOSITE_WEIGHTS = [0.55,        0.30,                 0.15]


# Регими (BG): висок score = restrictive
REGIMES = [
    (80, "ПРОБЛЕМАТИЧНО ТЯСНА",   "#d50000"),  # > 90 percentile DFR
    (65, "РЕСТРИКТИВНА",          "#ff6d00"),
    (45, "НЕУТРАЛНА",             "#ffd600"),
    (30, "СТИМУЛАТИВНА",          "#69f0ae"),
    (0,  "СИЛНО СТИМУЛАТИВНА",    "#0091ea"),
]


def _apply_transform(series: pd.Series, transform: str) -> pd.Series:
    if transform == "yoy_pct":
        return series.pct_change(periods=12).dropna() * 100
    if transform == "qoq_pct":
        return series.pct_change(periods=4).dropna() * 100
    if transform == "mom_pct":
        return series.pct_change().dropna() * 100
    return series


def run(snapshot: dict[str, pd.Series]) -> dict[str, Any]:
    """Изчислява ECB policy stance composite."""
    indicators: dict[str, dict] = {}
    transformed: dict[str, pd.Series] = {}

    for sid, meta in SERIES.items():
        if sid in snapshot and not snapshot[sid].empty:
            transform = meta.get("transform", "level")
            ts = _apply_transform(snapshot[sid], transform)
            transformed[sid] = ts
            if not ts.empty:
                indicators[sid] = score_series(
                    ts,
                    history_start=HISTORY_START,
                    invert=meta["invert"],
                    name=meta["label"],
                )

    composite = _composite(indicators, COMPOSITE_SERIES, COMPOSITE_WEIGHTS)
    regime_label, regime_color = get_regime(composite, REGIMES)

    sparklines: dict[str, dict] = {}
    hist_context: dict[str, dict] = {}
    for sid in SERIES:
        if sid in transformed and not transformed[sid].empty:
            sparklines[sid] = build_sparkline(transformed[sid], months=36)
            hist_context[sid] = build_historical_context(
                transformed[sid],
                float(transformed[sid].iloc[-1]),
                history_start=HISTORY_START,
            )

    return {
        "module": "ecb",
        "label": "ЕЦБ парична политика",
        "icon": "🏦",
        "scores": {
            "stance": {"score": composite, "label": "Stance restrictiveness"},
        },
        "composite": composite,
        "regime": regime_label,
        "regime_color": regime_color,
        "indicators": indicators,
        "sparklines": sparklines,
        "historical_context": hist_context,
        "key_readings": _key_readings(indicators),
    }


# ─── Helpers ─────────────────────────────────────────────────────

def _composite(scores: dict, series_list: list, weights: list) -> float:
    vals = [scores[s]["score"] for s in series_list if s in scores]
    wts = [weights[i] for i, s in enumerate(series_list) if s in scores]
    if not vals:
        return 50.0
    return round(sum(v * w for v, w in zip(vals, wts)) / sum(wts), 1)


def _key_readings(indicators: dict) -> list[dict]:
    out = []
    for sid in SERIES:
        if sid in indicators:
            s = indicators[sid]
            out.append({
                "id": sid,
                "label": s["name"],
                "value": s["current_value"],
                "date": s["last_date"],
                "yoy": s["yoy_change"],
                "percentile": s["percentile"],
                "score": s["score"],
            })
    return out
