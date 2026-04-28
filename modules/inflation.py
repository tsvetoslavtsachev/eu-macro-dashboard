"""
modules/inflation.py
====================
Inflation lens за Eurozone.

Phase 2: оценява HICP_HEADLINE / HICP_CORE / HICP_SERVICES.
ЕЦБ-ова target = 2% medium-term. Composite = percentile spectrum (без invert),
тоест високи стойности дават висок score = "елевирана инфлация".

Различно framing от labor (където висок score = здрав labor):
  Тук висок score = висока инфлация = проблем за ЕЦБ.
  Регимите отразяват това: < 20 → дефлационен риск, > 80 → остра инфлация.

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
    "EA_HICP_HEADLINE": {"label": "HICP всички продукти (YoY %)", "invert": False, "is_rate": True},
    "EA_HICP_CORE":     {"label": "HICP базова (excl. енергия и храни, YoY %)", "invert": False, "is_rate": True},
    "EA_HICP_SERVICES": {"label": "HICP услуги (YoY %)", "invert": False, "is_rate": True},
}

# Composite weights — services и core тежат повече от headline (ECB practice:
# подложни компоненти > volatile headline)
COMPOSITE_SERIES  = ["EA_HICP_HEADLINE", "EA_HICP_CORE", "EA_HICP_SERVICES"]
COMPOSITE_WEIGHTS = [0.30,                0.40,           0.30]


# Регими: висок percentile = висока инфлация в исторически контекст
REGIMES = [
    (80, "ОСТРА ИНФЛАЦИЯ",    "#d50000"),  # rare top-of-history pressure
    (65, "ЕЛЕВИРАНА",         "#ff6d00"),
    (45, "БЛИЗО ДО ЦЕЛТА",    "#69f0ae"),
    (30, "ПОД ЦЕЛТА",         "#ffd600"),
    (0,  "ДЕФЛАЦИОНЕН РИСК",  "#0091ea"),
]


def run(snapshot: dict[str, pd.Series]) -> dict[str, Any]:
    """Изчислява Inflation lens за EA."""
    indicators: dict[str, dict] = {}
    for sid, meta in SERIES.items():
        if sid in snapshot and not snapshot[sid].empty:
            indicators[sid] = score_series(
                snapshot[sid],
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
        if sid in snapshot and not snapshot[sid].empty:
            sparklines[sid] = build_sparkline(snapshot[sid], months=36)
            hist_context[sid] = build_historical_context(
                snapshot[sid],
                float(snapshot[sid].iloc[-1]),
                history_start=HISTORY_START,
            )

    return {
        "module": "inflation",
        "label": "Инфлация",
        "icon": "🔥",
        "scores": {
            "composite_pressure": {"score": composite, "label": "Композитен натиск"},
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
