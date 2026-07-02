"""
tests/test_export_components_no_score.py
=========================================
P3-fix-C (Q3, решение на Цветослав 03.07): lens=[] "_components" серии
(строителни блокове за derived числа) НЕ получават score/health полета в
series_data.json — те нямат изрична полярност и score с default +1 внушаваше
посока („DFR по-високо = по-добре"). Остават като chart данни.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from export_api import ALL_CHART_SERIES, build_series_data  # noqa: E402
from catalog.series import SERIES_CATALOG  # noqa: E402


def monthly(values, end="2026-06-01"):
    idx = pd.date_range(end=end, periods=len(values), freq="MS")
    return pd.Series(values, index=idx)


def _long_series():
    return monthly(list(2.0 + 0.01 * np.arange(130)))


def _component_chart_key():
    return next(
        (k for k in sorted(ALL_CHART_SERIES)
         if not SERIES_CATALOG.get(k, {}).get("lens")),
        None,
    )


def _lens_chart_key():
    return next(
        (k for k in sorted(ALL_CHART_SERIES)
         if SERIES_CATALOG.get(k, {}).get("lens")),
        None,
    )


class TestComponentsNoScore:
    def test_component_series_has_no_score_fields(self):
        key = _component_chart_key()
        assert key is not None, "няма lens=[] серия в CHART_SERIES — тестът е остарял"

        out = build_series_data({key: _long_series()}, today=date(2026, 7, 3))
        series = out["series"]
        assert key in series, f"{key} липсва от series_data изхода"
        latest = series[key]["latest"]
        assert latest["score"] is None, f"{key}: component серия пак получава score"
        assert latest["health_z"] is None
        # Данните за chart-а остават
        assert latest["value"] is not None
        assert series[key]["chart"]["dates"]

    def test_lens_series_still_scored(self):
        key = _lens_chart_key()
        assert key is not None

        out = build_series_data({key: _long_series()}, today=date(2026, 7, 3))
        series = out["series"]
        assert key in series
        assert series[key]["latest"]["score"] is not None, (
            f"{key}: лещова серия загуби score-а си — guard-ът е прекалено широк"
        )
