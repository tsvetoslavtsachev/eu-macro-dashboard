"""Tests за modules/{labor,inflation,growth,ecb}.py — snapshot interface."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import modules.labor as labor_mod
import modules.inflation as inflation_mod
import modules.growth as growth_mod
import modules.ecb as ecb_mod


# ── Test fixtures ──────────────────────────────────────────────

def monthly(values: list[float], end: str = "2026-03-01") -> pd.Series:
    """Helper: създава monthly pd.Series с N стойности завършваща на end."""
    idx = pd.date_range(end=end, periods=len(values), freq="MS")
    return pd.Series(values, index=idx)


def trend(start: float, stop: float, n: int = 60, end: str = "2026-03-01") -> pd.Series:
    return monthly(list(np.linspace(start, stop, n)), end=end)


# ── Unified return shape ──────────────────────────────────────

UNIFIED_KEYS = {
    "module", "label", "icon", "scores", "composite", "regime",
    "regime_color", "indicators", "sparklines", "historical_context",
    "key_readings",
}


def _check_unified_shape(result: dict, module_name: str):
    assert UNIFIED_KEYS.issubset(set(result.keys())), \
        f"{module_name} missing keys: {UNIFIED_KEYS - set(result.keys())}"
    assert result["module"] == module_name
    assert isinstance(result["composite"], (int, float))
    assert 0 <= result["composite"] <= 100, f"composite={result['composite']}"
    assert isinstance(result["regime"], str)
    assert isinstance(result["scores"], dict)


# ── Labor module ───────────────────────────────────────────────

def test_labor_returns_unified_shape():
    snap = {"EA_UNRATE": trend(12.0, 6.0)}
    result = labor_mod.run(snap)
    _check_unified_shape(result, "labor")
    assert result["composite"] > 50  # низката безработица → высок score


def test_labor_handles_empty_snapshot():
    result = labor_mod.run({})
    _check_unified_shape(result, "labor")
    # Без данни: composite = 50 (neutral default)
    assert result["composite"] == 50.0


def test_labor_high_unemployment_low_score():
    """Висок unemployment → нисък score (invert=True)."""
    # Днес е на върха на историческия range
    snap = {"EA_UNRATE": trend(6.0, 12.0)}
    result = labor_mod.run(snap)
    assert result["composite"] < 30, f"expected low score, got {result['composite']}"


def test_labor_regime_has_color():
    snap = {"EA_UNRATE": trend(12.0, 6.0)}
    result = labor_mod.run(snap)
    assert result["regime_color"].startswith("#")
    assert len(result["regime_color"]) == 7


# ── Inflation module ───────────────────────────────────────────

def test_inflation_returns_unified_shape():
    snap = {
        "EA_HICP_HEADLINE": trend(0.5, 2.5),
        "EA_HICP_CORE":     trend(0.8, 2.8),
        "EA_HICP_SERVICES": trend(1.0, 3.5),
    }
    result = inflation_mod.run(snap)
    _check_unified_shape(result, "inflation")


def test_inflation_high_yields_high_score():
    """Висок HICP YoY → висок percentile → висок score (no invert)."""
    snap = {
        "EA_HICP_HEADLINE": trend(0.5, 5.0),    # Излиза над целта
        "EA_HICP_CORE":     trend(0.5, 4.5),
        "EA_HICP_SERVICES": trend(0.5, 4.0),
    }
    result = inflation_mod.run(snap)
    assert result["composite"] > 70, f"expected high score, got {result['composite']}"


def test_inflation_handles_partial_snapshot():
    """Само едно от 3-те серии дава resilient composite."""
    snap = {"EA_HICP_HEADLINE": trend(0.5, 2.5)}
    result = inflation_mod.run(snap)
    _check_unified_shape(result, "inflation")
    assert len(result["indicators"]) == 1


# ── Growth module ──────────────────────────────────────────────

def test_growth_returns_unified_shape():
    # IP индекс расте от 95 до 105 за 60 месеца — positive YoY% растеж
    snap = {"EA_IP": trend(95.0, 105.0, n=60)}
    result = growth_mod.run(snap)
    _check_unified_shape(result, "growth")


def test_growth_yoy_transform_applied():
    """Growth модулът трансформира level-индекса в YoY%."""
    # 5-годишна постоянно растяща серия → YoY% около константата
    snap = {"EA_IP": trend(100.0, 110.0, n=60)}
    result = growth_mod.run(snap)
    # YoY% не трябва да е същият като level — sparkline values трябва да са percentages
    spark = result["sparklines"]["EA_IP"]
    if spark["values"]:
        # Стойностите след transform трябва да са в "% range" (ниска абсолютна стойност), не индекс
        assert max(abs(v) for v in spark["values"]) < 50, \
            "values look like raw index, not YoY%"


def test_growth_handles_empty():
    result = growth_mod.run({})
    _check_unified_shape(result, "growth")
    assert result["composite"] == 50.0


# ── ECB module ─────────────────────────────────────────────────

def test_ecb_returns_unified_shape():
    snap = {
        "ECB_DFR":            trend(-0.5, 4.0, n=60),
        "ECB_MRO":            trend(0.0, 4.5, n=60),
        "ECB_BALANCE_SHEET":  trend(2_000_000, 7_000_000, n=60),
    }
    result = ecb_mod.run(snap)
    _check_unified_shape(result, "ecb")


def test_ecb_high_dfr_high_stance():
    """Висока DFR → restrictive stance → висок composite."""
    snap = {"ECB_DFR": trend(-0.5, 4.0, n=60)}  # rising rates
    result = ecb_mod.run(snap)
    # Top of historical range → percentile > 80
    assert result["composite"] > 70


def test_ecb_low_dfr_low_stance():
    """Ниска DFR → stimulative → низък composite."""
    snap = {"ECB_DFR": trend(4.0, -0.5, n=60)}  # rates са спаднали
    result = ecb_mod.run(snap)
    assert result["composite"] < 30


def test_ecb_partial_snapshot_works():
    snap = {"ECB_DFR": trend(0.0, 2.0, n=60)}
    result = ecb_mod.run(snap)
    _check_unified_shape(result, "ecb")
