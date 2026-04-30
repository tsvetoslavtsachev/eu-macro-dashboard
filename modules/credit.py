"""
modules/credit.py
=================
Credit & financial conditions lens за Eurozone — НОВ за Phase 1.5.

Преди Phase 1.5 catalog имаше 9 credit серии но без active module —
composite weight (0.20 в config) беше stranded. Този модул затваря gap-а.

Серии:
  - EA_CISS — composite financial stress (peer_group: financial_stress)
  - EA_BTP_BUND_SPREAD, EA_OAT_BUND_SPREAD — derived sovereign spreads
    (peer_group: sovereign_spreads). Computed локално от IT_10Y, FR_10Y, DE_10Y.
  - EA_BANK_LOANS_NFC, EA_BANK_LOANS_HH — credit transmission
    (peer_group: bank_lending)
  - EA_BUND_10Y — risk-free benchmark level
  - EA_M3_YOY — monetary aggregate growth

Convention:
  - Висок composite score = СТРЕСИРАНИ / ИЗПЪНАТИ credit conditions
  - Нисък composite score = ЛАБОРАВНИ / СТИМУЛАТИВНИ conditions
  - Аналогично на inflation lens (висок = problematic)

Регими отразяват credit cycle stage:
  СИЛНО ЛАБОРАВНИ → ЛАБОРАВНИ → НЕУТРАЛНИ → ЕЛЕВИРАНИ → СТРЕСИРАНИ

Pattern: snapshot interface (mirror на ecb.py).
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
    "EA_CISS": {
        "label": "CISS — financial stress индекс",
        "invert": False,           # висок = стрес → high score
        "transform": "level",
        "is_rate": False,          # CISS е index 0-1, не rate
    },
    "EA_BTP_BUND_SPREAD": {
        "label": "BTP-Bund spread (10Y, pp)",
        "invert": False,           # широк = стрес/фрагментация
        "transform": "level",
        "is_rate": True,           # spread в pp
    },
    "EA_OAT_BUND_SPREAD": {
        "label": "OAT-Bund spread (10Y, pp)",
        "invert": False,
        "transform": "level",
        "is_rate": True,
    },
    "EA_BANK_LOANS_NFC": {
        "label": "MFI кредити към корпорации (YoY %)",
        "invert": True,            # свиване = restrictive credit → high score
        "transform": "level",
        "is_rate": True,
    },
    "EA_BANK_LOANS_HH": {
        "label": "MFI кредити към домакинства (YoY %)",
        "invert": True,
        "transform": "level",
        "is_rate": True,
    },
    "EA_BUND_10Y": {
        "label": "Bund 10Y yield (%)",
        "invert": False,           # висок yield = restrictive cost of capital
        "transform": "level",
        "is_rate": True,
    },
    "EA_M3_YOY": {
        "label": "M3 паричен ръст (YoY %)",
        "invert": True,            # свиване = tight monetary
        "transform": "level",
        "is_rate": True,
    },
}

# CISS dominant; sovereign_spreads bundled (avg BTP+OAT); bank_lending bundled.
# Bund 10Y level и M3 secondary.
COMPOSITE_SERIES = [
    "EA_CISS", "EA_BTP_BUND_SPREAD", "EA_OAT_BUND_SPREAD",
    "EA_BANK_LOANS_NFC", "EA_BANK_LOANS_HH",
    "EA_BUND_10Y", "EA_M3_YOY",
]
# Weights normalize so spreads pair и lending pair имат aggregate weights:
#   CISS=0.30, spreads=0.25 (split 0.125 each), lending=0.20 (split 0.10 each),
#   Bund=0.15, M3=0.10. Sum=1.00.
COMPOSITE_WEIGHTS = [0.30, 0.125, 0.125, 0.10, 0.10, 0.15, 0.10]


# Регими (BG): висок score = stressed credit conditions
REGIMES = [
    (80, "СТРЕСИРАНИ",          "#d50000"),   # crisis-like (CISS > 0.4, spreads > 200bp)
    (65, "ЕЛЕВИРАНИ",           "#ff6d00"),   # tight conditions
    (45, "НЕУТРАЛНИ",           "#ffd600"),   # near average
    (30, "ЛАБОРАВНИ",           "#69f0ae"),   # accommodative
    (0,  "СИЛНО ЛАБОРАВНИ",     "#0091ea"),   # ultra-loose (e.g., 2015-2019 NIRP)
]


def _compute_derived_spreads(snapshot: dict[str, pd.Series]) -> dict[str, pd.Series]:
    """Computes BTP-Bund and OAT-Bund spreads from raw IT/FR/DE 10Y yields.

    Returns dict mapping derived SID → spread pd.Series. Empty dict if any
    required input is missing.
    """
    derived: dict[str, pd.Series] = {}

    de = snapshot.get("DE_10Y")
    if de is None or de.empty:
        return derived

    it = snapshot.get("IT_10Y")
    if it is not None and not it.empty:
        spread = (it - de).dropna()
        if not spread.empty:
            derived["EA_BTP_BUND_SPREAD"] = spread

    fr = snapshot.get("FR_10Y")
    if fr is not None and not fr.empty:
        spread = (fr - de).dropna()
        if not spread.empty:
            derived["EA_OAT_BUND_SPREAD"] = spread

    return derived


def run(snapshot: dict[str, pd.Series]) -> dict[str, Any]:
    """Изчислява Credit lens за EA.

    Args:
        snapshot: {series_key: pd.Series} от adapter cache. Спредовете се
            изчисляват локално от IT/FR/DE 10Y ако присъстват.

    Returns:
        Unified module dict (виж labor.py docstring за shape).
    """
    # Augment snapshot с derived spreads (не мутираме оригинала)
    derived = _compute_derived_spreads(snapshot)
    augmented = {**snapshot, **derived}

    indicators: dict[str, dict] = {}
    for sid, meta in SERIES.items():
        s = augmented.get(sid)
        if s is None or s.empty:
            continue
        indicators[sid] = score_series(
            s,
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
        s = augmented.get(sid)
        if s is None or s.empty:
            continue
        sparklines[sid] = build_sparkline(s, months=36)
        hist_context[sid] = build_historical_context(
            s, float(s.iloc[-1]), history_start=HISTORY_START,
        )

    return {
        "module": "credit",
        "label": "Финансови условия и кредит",
        "icon": "🏛",
        "scores": {
            "stress": {"score": composite, "label": "Credit conditions stress"},
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
