"""
modules/growth.py
=================
Growth lens за Eurozone.

Phase 2: оценява EA Industrial Production (transform=yoy_pct).
Phase 2.5+ ще добави Retail Trade, ESI sentiment, GDP когато се confirm-нат
правилните Eurostat dimensions.

Convention: висок YoY % растеж = висок score = здрава активност.

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
    "EA_IP": {
        "label": "Промишлено производство (EA-21, YoY %)",
        "invert": False,
        "transform": "yoy_pct",
        "is_rate": True,
    },
    "EA_RETAIL_VOL": {
        "label": "Търговия на дребно — обем (YoY %)",
        "invert": False,
        "transform": "yoy_pct",
        "is_rate": True,
    },
    "EA_BUILDING_PRODUCTION": {
        "label": "Строително производство (YoY %)",
        "invert": False,
        "transform": "yoy_pct",
        "is_rate": True,
    },
    "EA_GDP_QOQ": {
        "label": "Реален БВП (QoQ %)",
        "invert": False,
        "transform": "qoq_pct",  # quarterly → QoQ %
        "is_rate": True,
    },
    "EA_ESI": {
        "label": "Икономически Sentiment Indicator",
        "invert": False,
        "transform": "level",
        "is_rate": False,  # ESI е index ~100 base, не percentage
    },
}

# Hard data доминира; sentiment е leading но noisy.
# IP най-широко покритие; retail е consumer proxy; GDP е headline; ESI е forward.
COMPOSITE_SERIES  = ["EA_IP",  "EA_RETAIL_VOL", "EA_BUILDING_PRODUCTION", "EA_GDP_QOQ", "EA_ESI"]
COMPOSITE_WEIGHTS = [0.30,      0.25,            0.15,                     0.20,         0.10]


# Регими (BG): висок YoY% growth → висок score → здрав растеж
REGIMES = [
    (80, "ЕКСПАНЗИЯ",  "#00c853"),
    (65, "РАСТЕЖ",     "#69f0ae"),
    (45, "СТАГНАЦИЯ",  "#ffd600"),
    (30, "СВИВАНЕ",    "#ff6d00"),
    (0,  "РЕЦЕСИЯ",    "#d50000"),
]


def _apply_transform(series: pd.Series, transform: str) -> pd.Series:
    """Прилага catalog-define-натия transform върху raw серия.

    Phase 2: поддържа yoy_pct и level. Phase 3 ще добави mom_pct, qoq_pct,
    first_diff, z_score (а някои от тях вече са в core/primitives.py).
    """
    if transform == "yoy_pct":
        return series.pct_change(periods=12).dropna() * 100
    if transform == "qoq_pct":
        return series.pct_change(periods=4).dropna() * 100
    if transform == "mom_pct":
        return series.pct_change().dropna() * 100
    return series


def run(snapshot: dict[str, pd.Series]) -> dict[str, Any]:
    """Изчислява Growth lens за EA."""
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
                    is_rate=meta.get("is_rate", False),
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
        "module": "growth",
        "label": "Растеж и активност",
        "icon": "📈",
        "scores": {
            "activity": {"score": composite, "label": "Активност"},
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
