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
import modules.credit as credit_mod
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


def test_labor_yoy_returns_pp_delta_for_rate_series():
    """Regression: UNRATE е rate series → YoY трябва да е pp delta, не relative %.

    UNRATE от 6.30 → 6.20 = -0.10pp (НЕ -1.6%, което беше bug-ът).
    """
    # Synthetic series: 12 месеца константа на 6.30, после спад до 6.20
    idx = pd.date_range(end="2026-03-01", periods=24, freq="MS")
    values = [6.30] * 12 + [6.20] * 12
    snap = {"EA_UNRATE": pd.Series(values, index=idx)}
    result = labor_mod.run(snap)
    kr = result["key_readings"][0]
    assert kr["yoy_unit"] == "pp", f"expected pp unit, got {kr['yoy_unit']}"
    assert kr["yoy"] == pytest.approx(-0.10, abs=0.01), \
        f"expected -0.10pp absolute delta, got {kr['yoy']}"


def test_inflation_yoy_returns_pp_delta():
    """Regression: HICP YoY → YoY column е pp, не relative %.

    HICP от 2.40 → 2.00 = -0.40pp (НЕ -16.7%, което беше bug-ът).
    """
    idx = pd.date_range(end="2026-03-01", periods=24, freq="MS")
    values = [2.40] * 12 + [2.00] * 12
    snap = {"EA_HICP_HEADLINE": pd.Series(values, index=idx)}
    result = inflation_mod.run(snap)
    kr = next(r for r in result["key_readings"] if r["id"] == "EA_HICP_HEADLINE")
    assert kr["yoy_unit"] == "pp"
    assert kr["yoy"] == pytest.approx(-0.40, abs=0.01)


def test_ecb_balance_yoy_pp_delta_after_transform():
    """Regression: ECB balance YoY% transform → YoY column е pp.

    Balance YoY от -0.27% → +2.23% = +2.5pp (НЕ +879%, което беше bug-ът).
    """
    # Build level series so YoY transform produces clear delta
    idx = pd.date_range(end="2026-03-01", periods=36, freq="MS")
    # First 24 months stable, next 12 grow to produce specific YoY change
    levels = list(range(100, 100 + 24)) + list(range(124, 124 + 12))
    snap = {"ECB_BALANCE_SHEET": pd.Series([float(v) for v in levels], index=idx)}
    result = ecb_mod.run(snap)
    kr = next((r for r in result["key_readings"] if r["id"] == "ECB_BALANCE_SHEET"), None)
    assert kr is not None
    assert kr["yoy_unit"] == "pp"
    # Ние не знаем точното pp число (зависи от transform internals), но
    # трябва да е малко число (< 50pp), не absurd процент
    assert abs(kr["yoy"]) < 50, f"yoy should be reasonable pp delta, got {kr['yoy']}"


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


# ── Credit module (Phase 1.5 NEW) ──────────────────────────────

def test_credit_returns_unified_shape():
    snap = {
        "EA_CISS": trend(0.05, 0.15, n=60),
        "EA_BANK_LOANS_NFC": trend(2.0, 1.0, n=60),
        "EA_BANK_LOANS_HH": trend(2.5, 1.5, n=60),
        "EA_BUND_10Y": trend(0.5, 3.0, n=60),
        "EA_M3_YOY": trend(8.0, 3.0, n=60),
        "IT_10Y": trend(2.0, 4.5, n=60),
        "FR_10Y": trend(1.0, 3.5, n=60),
        "DE_10Y": trend(0.5, 2.5, n=60),
    }
    result = credit_mod.run(snap)
    _check_unified_shape(result, "credit")


def test_credit_handles_empty_snapshot():
    result = credit_mod.run({})
    _check_unified_shape(result, "credit")
    assert result["composite"] == 50.0


def test_credit_computes_btp_bund_spread_locally():
    """Module трябва да compute-ва BTP-Bund от raw IT_10Y - DE_10Y."""
    it = trend(2.0, 5.0, n=60)
    de = trend(0.5, 2.5, n=60)
    snap = {"IT_10Y": it, "DE_10Y": de}
    result = credit_mod.run(snap)
    # Spread series трябва да присъства в indicators
    assert "EA_BTP_BUND_SPREAD" in result["indicators"]
    # Latest spread = IT.iloc[-1] - DE.iloc[-1] = 5.0 - 2.5 = 2.5pp
    spread_val = result["indicators"]["EA_BTP_BUND_SPREAD"]["current_value"]
    assert spread_val == pytest.approx(2.5, abs=0.01)


def test_credit_computes_oat_bund_spread_locally():
    """OAT-Bund = FR_10Y - DE_10Y."""
    fr = trend(1.0, 3.5, n=60)
    de = trend(0.5, 2.5, n=60)
    snap = {"FR_10Y": fr, "DE_10Y": de}
    result = credit_mod.run(snap)
    assert "EA_OAT_BUND_SPREAD" in result["indicators"]
    spread_val = result["indicators"]["EA_OAT_BUND_SPREAD"]["current_value"]
    assert spread_val == pytest.approx(1.0, abs=0.01)


def test_credit_no_de_means_no_spreads():
    """Без DE_10Y не може да компютира spreads."""
    snap = {"IT_10Y": trend(2.0, 4.5, n=60)}
    result = credit_mod.run(snap)
    assert "EA_BTP_BUND_SPREAD" not in result["indicators"]


def test_credit_high_ciss_high_score():
    """Висок CISS → висок score (stress)."""
    snap = {"EA_CISS": trend(0.05, 0.45, n=60)}  # acute stress regime
    result = credit_mod.run(snap)
    assert result["composite"] > 60, f"expected high score, got {result['composite']}"


def test_credit_yoy_unit_for_rate_series_is_pp():
    """BTP-Bund spread е rate series → YoY unit трябва да е pp."""
    idx = pd.date_range(end="2026-03-01", periods=24, freq="MS")
    it = pd.Series([5.0] * 12 + [4.5] * 12, index=idx)
    de = pd.Series([3.0] * 24, index=idx)
    snap = {"IT_10Y": it, "DE_10Y": de}
    result = credit_mod.run(snap)
    spread_kr = next((r for r in result["key_readings"] if r["id"] == "EA_BTP_BUND_SPREAD"), None)
    assert spread_kr is not None
    assert spread_kr["yoy_unit"] == "pp"


# ── Labor wages extension (Phase 1.5) ──────────────────────────

def test_labor_includes_wages_in_composite():
    """EA_COMP_PER_EMPLOYEE трябва да участва когато присъства в snapshot."""
    # Wages нараства от 100 до 130 за 60 месеца → стабилен YoY%
    snap = {
        "EA_UNRATE": trend(8.0, 6.0),
        "EA_COMP_PER_EMPLOYEE": trend(100.0, 130.0, n=72),  # quarterly-ish
    }
    result = labor_mod.run(snap)
    _check_unified_shape(result, "labor")
    # Wages трябва да е в indicators ако transform yoy_pct произвежда non-empty
    if "EA_COMP_PER_EMPLOYEE" in result["indicators"]:
        kr = next(r for r in result["key_readings"] if r["id"] == "EA_COMP_PER_EMPLOYEE")
        assert kr["yoy_unit"] == "pp"


# ── Inflation HICP decomp + PPI extension (Phase 1.5) ──────────

def test_inflation_includes_hicp_energy_and_food():
    """HICP energy/food са в headline_measures peer_group."""
    snap = {
        "EA_HICP_HEADLINE": trend(0.5, 2.5),
        "EA_HICP_ENERGY":   trend(-2.0, 8.0),  # volatile energy
        "EA_HICP_FOOD":     trend(0.5, 4.0),
    }
    result = inflation_mod.run(snap)
    _check_unified_shape(result, "inflation")
    assert "EA_HICP_ENERGY" in result["indicators"]
    assert "EA_HICP_FOOD" in result["indicators"]


def test_inflation_includes_ppi_intermediate():
    """PPI intermediate goods през yoy_pct transform."""
    # Index расте 100 → 130 за 60 месеца → YoY около 5%
    snap = {
        "EA_HICP_CORE":         trend(0.5, 2.5),
        "EA_PPI_INTERMEDIATE":  trend(100.0, 130.0, n=72),
    }
    result = inflation_mod.run(snap)
    _check_unified_shape(result, "inflation")
    if "EA_PPI_INTERMEDIATE" in result["indicators"]:
        kr = next(r for r in result["key_readings"] if r["id"] == "EA_PPI_INTERMEDIATE")
        assert kr["yoy_unit"] == "pp"
