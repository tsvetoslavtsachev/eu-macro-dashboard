"""
tests/test_scorer_mad_guard.py
===============================
O3 Вълна 1 (КОКПИТ) · живо доказателство №5 — КАНОНИЧНИЯТ degenerate guard.

Портнат от china scorer (единен US/EU/CN, O3 правило 4): MAD=0 в 10-г. прозорец
(административно пиннати серии) НЕ бива да дава фалшиво „неутрално 50" при реален
всеисторически екстремум. Fallback към пълната история + клип ±6σ +
`scale_fallback`/`degenerate` флагове. Регресионният гейт е ИДЕНТИЧЕН на
us/china tests/test_scorer_mad_guard.py — един guard, три репа.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from core.scorer import score_series  # noqa: E402


def monthly(values: list[float], end: str = "2026-03-01") -> pd.Series:
    idx = pd.date_range(end=end, periods=len(values), freq="MS")
    return pd.Series(values, index=idx)


def pinned_rate_series() -> pd.Series:
    early = list(np.linspace(5.0, 6.0, 130))
    plateau = [4.3] * 115
    steps = [4.1, 3.9, 3.6, 3.3, 3.0]
    return monthly(early + plateau + steps)


class TestMadGuard:
    def test_pinned_series_at_low_is_not_neutral(self):
        s = pinned_rate_series()
        res = score_series(s, invert=True, name="rate-like", min_obs=36)

        assert res["scale_fallback"] is True, "очаквахме fallback към пълна история"
        assert res["degenerate"] is False
        assert res["score"] != pytest.approx(50.0)
        assert res["score"] > 50.0     # rate под нормата + invert → облекчаване → healthy
        assert res["health_z"] > 0

    def test_constant_series_is_neutral_but_flagged(self):
        s = monthly([4.3] * 200)
        res = score_series(s, invert=True, name="const", min_obs=36)

        assert res["degenerate"] is True
        assert res["score"] == pytest.approx(50.0)
        assert res["health_z"] == pytest.approx(0.0)

    def test_constant_u_polarity_is_neutral_not_73(self):
        s = monthly([2.0] * 200)
        res = score_series(s, polarity=("U", "target", 2.0), name="const-U", min_obs=36)

        assert res["degenerate"] is True
        assert res["score"] == pytest.approx(50.0)

    def test_normal_series_unaffected(self):
        rng = np.random.default_rng(7)
        s = monthly(list(5.0 + np.cumsum(rng.normal(0, 0.1, 180))))
        res = score_series(s, name="normal", min_obs=36)

        assert res["scale_fallback"] is False
        assert res["degenerate"] is False
        assert res["z_score"] is not None
