"""
modules/labor.py
================
Labor market lens за Eurozone.

Phase 2: minimum viable — оценява UNRATE като headline labor signal.
Phase 2.5+ ще добави LFS employment, job vacancies, wages когато се confirm-нат
правилните Eurostat dimensions.

Pattern: snapshot interface (вместо legacy client).
  run(snapshot: dict[str, pd.Series]) -> dict с unified shape:
    {module, label, icon, scores, composite, regime, regime_color,
     indicators, sparklines, key_readings}
"""
from __future__ import annotations
from typing import Any

import pandas as pd

from core.scorer import (
    score_series, build_sparkline, build_historical_context, get_regime,
)
from config import HISTORY_START


# ─── Catalog отговаря на Phase 1.5 (catalog/series.py) ─────────────
SERIES = {
    "EA_UNRATE": {
        "label": "Безработица (EA-21, %)",
        "invert": True,
        "transform": "level",
        "is_rate": True,
    },
    "EA_LFS_EMP": {
        "label": "Заетост 20-64г (LFS, % от популация)",
        "invert": False,   # висока employment rate = здрав labor
        "transform": "level",
        "is_rate": True,
    },
    "EA_EMPLOYMENT_EXP": {
        "label": "Очаквания за заетост (3m напред)",
        "invert": False,   # положителни очаквания = здрав labor
        "transform": "level",
        "is_rate": False,  # balance index, не percentage
    },
    "EA_COMP_PER_EMPLOYEE": {
        "label": "Компенсация на наетите (D1, EA-20, YoY %)",
        "invert": False,   # ускоряващи заплати = здрав labor (но: stagflation тест)
        "transform": "yoy_pct",  # raw е level в EUR mln
        "is_rate": True,
    },
}

# UNRATE доминира (lagging но broadly available); LFS_EMP е structural;
# WAGES е forward-looking (важно за stagflation cross-lens);
# EMPLOYMENT_EXP е forward (но кратка история — малко тегло)
CYCLICAL_SERIES  = ["EA_UNRATE", "EA_LFS_EMP", "EA_EMPLOYMENT_EXP", "EA_COMP_PER_EMPLOYEE"]
CYCLICAL_WEIGHTS = [0.40,         0.25,          0.10,                0.25]


# Регими (BG), inverted convention: висок score = здрав labor market
REGIMES = [
    (80, "ГОРЕЩ",      "#00c853"),  # много нисък unemployment
    (65, "ЗДРАВ",      "#69f0ae"),  # под средното
    (45, "ОХЛАЖДАЩ",   "#ffd600"),  # около средното
    (30, "СЛАБ",       "#ff6d00"),  # над средното
    (0,  "СТРЕСИРАН",  "#d50000"),  # рекордно високо
]


def _apply_transform(series: pd.Series, transform: str) -> pd.Series:
    """Прилага catalog transform върху raw серия."""
    if transform == "yoy_pct":
        return series.pct_change(periods=12).dropna() * 100
    if transform == "qoq_pct":
        return series.pct_change(periods=4).dropna() * 100
    if transform == "mom_pct":
        return series.pct_change().dropna() * 100
    return series


def run(snapshot: dict[str, pd.Series]) -> dict[str, Any]:
    """Изчислява Labor lens за EA от snapshot.

    Args:
        snapshot: {series_key: pd.Series} от adapter cache.

    Returns:
        Unified module dict (виж docstring).
    """
    indicators: dict[str, dict] = {}
    transformed: dict[str, pd.Series] = {}
    for sid, meta in SERIES.items():
        if sid in snapshot and not snapshot[sid].empty:
            ts = _apply_transform(snapshot[sid], meta.get("transform", "level"))
            transformed[sid] = ts
            if not ts.empty:
                indicators[sid] = score_series(
                    ts,
                    history_start=HISTORY_START,
                    invert=meta["invert"],
                    name=meta["label"],
                    is_rate=meta.get("is_rate", False),
                )

    composite = _composite(indicators, CYCLICAL_SERIES, CYCLICAL_WEIGHTS)
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
        "module": "labor",
        "label": "Пазар на труда",
        "icon": "👷",
        "scores": {
            "cyclical_health": {"score": composite, "label": "Цикличeн състояние"},
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
                "yoy_unit": s.get("yoy_unit", "%"),
                "percentile": s["percentile"],
                "score": s["score"],
            })
    return out
