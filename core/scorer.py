"""
core/scorer.py
==============
Преобразува сурови pd.Series стойности в нормализиран health score (0–100).

Data-source agnostic — работи с pd.Series независимо дали идва от ECB,
Eurostat или другаде.

Методология (виж ../macro-satellite/LENS_SCORING_METHODOLOGY.md — единният
примитив за трите икономики; огледало на analysis/health.py::series_health_z):
• transform (каталожен) → темп вместо ниво за номинални серии (HICP индекс, M3)
• робастен z спрямо ПЛЪЗГАЩ 10-г. прозорец: z = (x − median₁₀) / (1.4826·MAD₁₀)
• полярност → health-z (по-високо = по-здраво; U-форма за HICP/норма)
• score = 50·(1 + tanh(z_h / 2)) → 50 = близката норма; ±2σ ≈ 88/12

Гаси percentile-of-full-history дефекта: номинално растящ индекс вече НЕ клони
към 100 (съди се спрямо собствената си близка норма, не спрямо 1999).

Всеки индикатор излиза с:
  - score (0–100; 50 = норма)        - health_z (робастен z, ориентиран по здраве)
  - percentile (trailing-10г ранг)   - current_value (сурово ниво)
  - display_value (трансформирано)   - display_is_pct (дали е % промяна)
  - last_date                        - yoy_change (%/pp)
"""
from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np
import pandas as pd

from core.primitives import apply_transform, robust_stats_latest, _infer_yoy_periods, momentum_signal

# ── константи (синхронни с analysis/health.py + catalog/polarity.py) ──────────
TANH_SLOPE = 2.0       # score = 50·(1+tanh(z_h/SLOPE)); ±2σ ≈ 88/12
U_BAND = 1.0           # U-форма: толерантна лента (в σ) преди здравето да падне
WINDOW_YEARS = 10      # близката норма = последните 10 години
MIN_OBS = 36           # ≥3 г. в прозореца, иначе fallback към пълна история
PCT_TRANSFORMS = {"yoy_pct", "mom_pct", "qoq_pct"}  # display като % промяна
# „Посока" сигнал: промяна на health-z за ~3 месеца (annotation, НЕ влиза в score).
# dead-band е ЕДНА глобална константа за всички серии/икономики (универсално,
# self-scaling по собствения robust scale) — не per-series tuning.
DIR_DEADBAND = 0.15    # |Δhealth-z| (в σ) за ▲/▼; под него → ▬ (плоско)


def percentile_rank(current: float, history: pd.Series) -> float:
    """% от историческите стойности по-ниски от текущата (0..100)."""
    if len(history) == 0:
        return 50.0
    return float(np.sum(history < current) / len(history) * 100)


def z_score(current: float, history: pd.Series) -> float:
    """Стандартизирана стойност спрямо историческото разпределение."""
    if len(history) == 0 or history.std() == 0:
        return 0.0
    return float((current - history.mean()) / history.std())


def normalize(value: float, lo: float, hi: float, invert: bool = False) -> float:
    """Линейна нормализация към 0–100. lo→0, hi→100 (или обратно с invert)."""
    if hi == lo:
        return 50.0
    score = (value - lo) / (hi - lo) * 100
    score = max(0.0, min(100.0, score))
    return 100.0 - score if invert else score


def _health_z(val: float, med: float, scale: float, polarity: Any) -> float:
    """Робастен z → health-z (по-високо = по-здраво). Огледало на
    analysis/health.py::series_health_z полярностната логика."""
    # U-форма: отклонение в двете посоки = по-зле
    if isinstance(polarity, tuple) and polarity and polarity[0] == "U":
        if scale == 0 or np.isnan(scale):
            return float(U_BAND)
        center = float(polarity[2]) if polarity[1] == "target" else med
        return float(U_BAND - abs((val - center) / scale))
    # Линейна полярност
    if scale == 0 or np.isnan(scale):
        return 0.0  # без вариация → на нормата
    z_raw = (val - med) / scale
    sign = float(polarity) if polarity in (1, -1, +1) else 1.0
    return float(sign * z_raw)


def _health_direction(
    transformed: pd.Series, scored_val: float, med: float, scale: float, polarity: Any,
) -> str:
    """Посока на ЗДРАВЕТО за ~3 месеца: 'up' (подобрява) / 'down' / 'flat'.

    Простичко: знак на 3-мес. движение на скорираната серия, обърнат по полярност
    (U → към/от целта). Нормира се по същия robust scale, dead-band = DIR_DEADBAND.
    Чист annotation — НЕ влиза в score-а.
    """
    if scale == 0 or np.isnan(scale):
        return "flat"
    n3 = max(1, round(_infer_yoy_periods(transformed) / 4))  # ~3м: месечни=3, седм.=13, трим.=1
    if len(transformed) <= n3:
        return "flat"
    prev = float(transformed.iloc[-1 - n3])
    if isinstance(polarity, tuple) and polarity and polarity[0] == "U":
        center = float(polarity[2]) if polarity[1] == "target" else med
        d_hz = (abs(prev - center) - abs(scored_val - center)) / scale  # + = към целта
    else:
        sgn = float(polarity) if polarity in (1, -1, +1) else 1.0
        d_hz = sgn * (scored_val - prev) / scale
    if d_hz > DIR_DEADBAND:
        return "up"
    if d_hz < -DIR_DEADBAND:
        return "down"
    return "flat"


def _trailing_window(s: pd.Series, window_years: int) -> pd.Series:
    """Последните window_years години (ДО последната точка)."""
    if isinstance(s.index, pd.DatetimeIndex) and len(s):
        cutoff = s.index[-1] - pd.DateOffset(years=window_years)
        return s[s.index >= cutoff]
    return s


def _polarity_repr(polarity: Any) -> str:
    """Стрингов repr за JSON (избягва tuple в output)."""
    if isinstance(polarity, tuple) and polarity and polarity[0] == "U":
        return f"U:{polarity[1]}" + (f"={polarity[2]}" if polarity[1] == "target" else "")
    return f"{polarity:+d}" if polarity in (1, -1, +1) else str(polarity)


def score_series(
    series: pd.Series,
    history_start: str = "1999-01-01",
    invert: bool = False,
    name: str = "",
    is_rate: bool = False,
    *,
    transform: str = "level",
    polarity: Any = None,
    scoring_mode: str = "level",
    window_years: int = WINDOW_YEARS,
    min_obs: int = MIN_OBS,
) -> dict:
    """Сурова серия → health score dict (робастен z спрямо плъзгащ 10-г. прозорец).

    Args:
        history_start: legacy/back-compat (вече НЕ дефинира нормата — прозорецът е плъзгащ).
        invert: legacy флаг — ако `polarity` е None, invert=True → полярност −1.
        is_rate: True ако стойността вече е в % (rate/YoY) → yoy_change като pp delta.
        transform: каталожна трансформация (yoy_pct/level/...) — прилага се ПРЕДИ scoring.
        polarity: +1 / −1 / ("U","self") / ("U","target",X). None → от invert.
        scoring_mode: "level" (default — ниво-vs-10г-норма) или "momentum" (external
            леща — робастен z на изгладения Δ; скорира рязката промяна, не нивото).

    score 50 = близката норма; >50 по-здраво, <50 по-зле (полярностно ориентирано).
    """
    series = series.dropna()
    if len(series) == 0:
        return _empty_score(name)

    if polarity is None:
        polarity = -1 if invert else +1

    current_val = float(series.iloc[-1])
    yoy = _calc_change(series, as_pp=is_rate)
    yoy_unit = "pp" if is_rate else "%"

    # Каталожна трансформация → темп за номиналните серии (гаси percentile pinning)
    transformed = apply_transform(series, transform).dropna()
    is_pct = transform in PCT_TRANSFORMS
    if transformed.empty:        # серия твърде къса за YoY → fallback към сурово ниво
        transformed = series
        is_pct = False

    scored_val = float(transformed.iloc[-1])
    last_date = (
        str(transformed.index[-1].date())
        if isinstance(transformed.index, pd.DatetimeIndex)
        else str(series.index[-1].date())
    )

    # Базис за робастната норма: момент (изгладен Δ) за external леща, иначе нивото.
    # Дисплеят (scored_val/percentile) си остава трансформираната серия и в двата режима.
    score_basis = momentum_signal(transformed) if scoring_mode == "momentum" else transformed

    # Робастна норма спрямо плъзгащ прозорец; fallback → пълна история на базиса
    stats = robust_stats_latest(score_basis, window_years=window_years, min_obs=min_obs)
    used_window = window_years
    if stats is None:
        stats = robust_stats_latest(score_basis, window_years=200, min_obs=12)
        used_window = 200

    if stats is None:  # твърде къса дори за fallback → неутрално
        return {
            "name": name or series.name or "unknown",
            "score": 50.0, "health_z": 0.0, "percentile": 50.0, "z_score": 0.0,
            "current_value": round(current_val, 4),
            "display_value": round(scored_val, 4), "display_is_pct": is_pct,
            "last_date": last_date, "yoy_change": yoy, "yoy_unit": yoy_unit,
            "transform": transform, "polarity": _polarity_repr(polarity),
            "direction": "flat", "invert": invert, "history_n": len(transformed),
        }

    val, med, scale = stats
    hz = _health_z(val, med, scale, polarity)
    score = round(50.0 * (1.0 + math.tanh(hz / TANH_SLOPE)), 1)
    direction = _health_direction(transformed, scored_val, med, scale, polarity)

    # Trailing percentile (на трансф. стойност в прозореца) — второстепенна прозрачност
    win = _trailing_window(transformed, used_window)
    pct = round(percentile_rank(scored_val, win), 1)

    return {
        "name": name or series.name or "unknown",
        "score": score,
        "health_z": round(hz, 2),
        "percentile": pct,
        "z_score": round(hz, 2),   # = health_z → сортиране по отдалеченост от нормата
        "current_value": round(current_val, 4),
        "display_value": round(scored_val, 4),
        "display_is_pct": is_pct,
        "last_date": last_date,
        "yoy_change": yoy,
        "yoy_unit": yoy_unit,
        "transform": transform,
        "scoring_mode": scoring_mode,
        "polarity": _polarity_repr(polarity),
        "direction": direction,
        "invert": invert,
        "history_n": len(win),
    }


def composite_score(scores: list, weights: Optional[list] = None) -> float:
    """Weighted average на score dict-ове или числа."""
    if not scores:
        return 50.0

    vals = []
    for s in scores:
        if isinstance(s, dict):
            vals.append(s.get("score", 50.0))
        else:
            vals.append(float(s))

    if weights is None:
        weights = [1.0] * len(vals)

    total = sum(w * v for w, v in zip(weights, vals))
    return round(total / sum(weights), 1)


def get_regime(score: float, regimes: list) -> tuple:
    """(label, color) за score спрямо regime таблица.
    regimes = [(threshold, label, color), ...] — сортирани низходящо."""
    for threshold, label, color in sorted(regimes, reverse=True):
        if score >= threshold:
            return label, color
    return regimes[-1][1], regimes[-1][2]


def build_sparkline(series: pd.Series, months: int = 24) -> dict:
    """Последните N месеца като sparkline данни."""
    cutoff = pd.Timestamp.now() - pd.DateOffset(months=months)
    recent = series[series.index >= cutoff].dropna()
    if len(recent) == 0:
        return {"dates": [], "values": []}
    return {
        "dates": [str(d.date()) for d in recent.index],
        "values": [round(float(v), 4) for v in recent.values],
    }


def build_historical_context(
    series: pd.Series,
    current_val: float,
    history_start: str = "1999-01-01",
) -> dict:
    """Min, max, mean, percentile band от history_start насам."""
    history = series[series.index >= pd.Timestamp(history_start)].dropna()
    if len(history) == 0:
        return {}
    return {
        "min": round(float(history.min()), 4),
        "max": round(float(history.max()), 4),
        "mean": round(float(history.mean()), 4),
        "median": round(float(history.median()), 4),
        "p25": round(float(history.quantile(0.25)), 4),
        "p75": round(float(history.quantile(0.75)), 4),
        "since": history_start,
        "n_obs": len(history),
    }


# ─── helpers ─────────────────────────────────────────────────────

def _calc_change(series: pd.Series, as_pp: bool = False) -> Optional[float]:
    """YoY промяна между current и стойност отпреди година.

    Args:
        as_pp: ако True → връща absolute pp delta (cur − old);
               ако False → връща relative % change ((cur − old) / |old| * 100).

    pp mode се ползва за rate/percentage series (UNRATE, HICP YoY, DFR), където
    relative % change на percentage е объркваща (HICP от 2.4% → 2.0% YoY е
    "-0.4pp", не "-16.7%").
    """
    try:
        now = series.index[-1]
        year_ago = now - pd.DateOffset(years=1)
        past = series[series.index <= year_ago]
        if len(past) == 0:
            return None
        old_val = float(past.iloc[-1])
        cur_val = float(series.iloc[-1])
        if as_pp:
            return round(cur_val - old_val, 2)
        if old_val == 0:
            return None
        return round((cur_val - old_val) / abs(old_val) * 100, 2)
    except Exception:
        return None


# Backward-compat alias (старият export name)
_calc_yoy = _calc_change


def _empty_score(name: str) -> dict:
    return {
        "name": name,
        "score": 50.0,
        "health_z": 0.0,
        "percentile": 50.0,
        "z_score": 0.0,
        "current_value": None,
        "display_value": None,
        "display_is_pct": False,
        "last_date": None,
        "yoy_change": None,
        "yoy_unit": "%",
        "transform": "level",
        "polarity": "+1",
        "direction": "flat",
        "invert": False,
        "history_n": 0,
    }
