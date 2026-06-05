"""
tests/test_momentum_scoring.py
==============================
Verify gate за момент-скоринга (external леща, F-редизайн 2026-06-05).

Твърдения:
  1. Рязък скок дава силен сигнал НЕЗАВИСИМО от нивото (две серии с еднакъв
     шок-профил, отместени само с константа → еднакъв health_z).
  2. Полярността обръща знака на шока (разходи ↑ = нездраво).
  3. Плоска серия → неутрално (≈50), без near-zero-MAD експлозия (нито inf/nan).
  4. Момент-режимът НЕ пинва номинално растящ индекс (заобикаля magnitude
     артефакта) — много по-близо до 50 от ниво-режима.

NB: реалистични noisy baselines — реалните external серии (import yoy, trade
balance, ToT, REER) флуктуират непрекъснато, така че MAD(момент) е здрав. Точно
плоска/линейна синтетика е дегенерат (MAD→0) и попада в scale==0 guard-а → 50.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.scorer import score_series
from core.primitives import momentum_signal
from analysis.health import series_health_z


def _monthly(values, end="2026-04-01"):
    idx = pd.date_range(end=end, periods=len(values), freq="MS")
    return pd.Series(values, index=idx)


def _noisy_baseline(n, scale=1.0, seed=0):
    """Реалистична флуктуираща baseline (random walk + noise) — не точно плоска."""
    rng = np.random.RandomState(seed)
    return np.cumsum(rng.randn(n) * scale) + rng.randn(n) * scale


def test_momentum_detects_shock_regardless_of_level():
    """Еднакъв шок-профил + различно ниво → почти идентичен health_z."""
    base = _noisy_baseline(160, scale=0.4, seed=1)
    shock = np.concatenate([np.zeros(150), np.linspace(0, 18, 10)])  # рязко ускорение накрая
    s_low = _monthly(100.0 + base + shock)
    s_high = _monthly(5000.0 + base + shock)  # 50× по-високо ниво, същата промяна

    sd_low = score_series(s_low, transform="level", polarity=+1, scoring_mode="momentum")
    sd_high = score_series(s_high, transform="level", polarity=+1, scoring_mode="momentum")

    hz_low, hz_high = sd_low["health_z"], sd_high["health_z"]
    # Нивото е 50× различно, но момент-сигналът е идентичен → health_z съвпада
    assert abs(hz_low - hz_high) < 1e-6, f"{hz_low} != {hz_high} (нивото не бива да влияе)"
    # И сигналът е силен (рязко ускорение нагоре с полярност +1)
    assert hz_high > 1.5, f"шокът трябва да дава силен сигнал, got {hz_high}"
    assert sd_high["score"] > 70, f"score трябва да е висок, got {sd_high['score']}"
    assert sd_high["scoring_mode"] == "momentum"


def test_momentum_shock_polarity_sign():
    """Полярност −1 (разходи) обръща знака: ускорение нагоре = нездраво (огледално)."""
    base = _noisy_baseline(160, scale=0.4, seed=2)
    shock = np.concatenate([np.zeros(150), np.linspace(0, 18, 10)])
    s = _monthly(100.0 + base + shock)
    sd_pos = score_series(s, transform="level", polarity=+1, scoring_mode="momentum")
    sd_neg = score_series(s, transform="level", polarity=-1, scoring_mode="momentum")
    assert sd_pos["health_z"] > 0 and sd_neg["health_z"] < 0
    assert abs(sd_pos["health_z"] + sd_neg["health_z"]) < 1e-9  # огледални


def test_momentum_flat_series_is_neutral_no_explosion():
    """Точно плоска серия → момент=0, MAD=0 → health_z=0, score≈50; никакъв inf/nan."""
    s = _monthly(np.full(140, 100.0))
    sd = score_series(s, transform="level", polarity=+1, scoring_mode="momentum")
    assert np.isfinite(sd["score"]) and np.isfinite(sd["health_z"])
    assert abs(sd["health_z"]) < 1e-9, f"flat → 0, got {sd['health_z']}"
    assert abs(sd["score"] - 50.0) < 1e-6, f"flat → 50, got {sd['score']}"


def test_momentum_avoids_magnitude_artifact_on_growing_index():
    """Стабилно растящ индекс: ниво-режим е дръпнат нагоре (latest≈max); момент-режим
    стои близо до 50 (стабилният растеж = норма, не екстремум)."""
    t = np.arange(160)
    rng = np.random.RandomState(3)
    growing = 100.0 + 2.0 * t + rng.randn(160) * 0.5  # линеен растеж + iid noise (без drift)
    s = _monthly(growing)

    sd_level = score_series(s, transform="level", polarity=+1, scoring_mode="level")
    sd_mom = score_series(s, transform="level", polarity=+1, scoring_mode="momentum")

    # Ниво-режимът е дръпнат нагоре (последната точка ≈ историческият максимум)
    assert sd_level["score"] > 70, f"level режим трябва да е дръпнат нагоре, got {sd_level['score']}"
    # Момент-режимът е значимо по-близо до 50 (заобикаля magnitude артефакта)
    assert abs(sd_mom["score"] - 50.0) < abs(sd_level["score"] - 50.0)
    assert sd_mom["score"] < sd_level["score"], "момент < ниво при растящ индекс"
    assert np.isfinite(sd_mom["health_z"])


def test_momentum_signal_primitive_shape():
    """momentum_signal: изгладен k-периоден Δ; без NaN; разумна дължина."""
    s = _monthly(np.cumsum(np.random.RandomState(0).randn(100)) + 100)
    mom = momentum_signal(s, smooth=3, k=3)
    assert isinstance(mom, pd.Series)
    assert mom.notna().all()
    assert len(mom) > 80


def test_series_health_z_momentum_matches_scorer():
    """series_health_z(momentum) и score_series(momentum) дават същия health_z."""
    base = _noisy_baseline(160, scale=0.4, seed=5)
    shock = np.concatenate([np.zeros(150), np.linspace(0, 12, 10)])
    s = _monthly(200.0 + base + shock)
    hz_health = series_health_z(s, transform="level", polarity=+1, scoring_mode="momentum")
    sd = score_series(s, transform="level", polarity=+1, scoring_mode="momentum")
    assert hz_health is not None
    # score_series закръгля health_z до 2dp; series_health_z връща суров float
    assert abs(round(hz_health, 2) - sd["health_z"]) < 1e-9
