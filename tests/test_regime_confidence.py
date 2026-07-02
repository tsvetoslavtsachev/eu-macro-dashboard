"""
tests/test_regime_confidence.py
================================
P3-fix-C (D1 + D2, решения на Цветослав 03.07):

D2 — EU-native режимен space: credit_stress през fragmentation_risk
(периферните спредове) + нова growth_labor_lead_lag двойка → expansion и
slowdown стават достижими (REVIEW-03: 3/8 режима бяха недостижими в EU).

D1 — „потвърден" се заслужава: първа поява → „индикиран"; ≥2 поредни
публикувани снимки → „потвърден".
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from analysis.executive import (  # noqa: E402
    CREDIT_STRESS_RULES,
    REGIME_LABELS_BG,
    REGIME_LABELS_BG_INDICATED,
    _classify_regime,
    resolve_regime_label_bg,
)
from catalog.cross_lens_pairs import CROSS_LENS_PAIRS, validate_pairs  # noqa: E402


class TestEuCreditStressViaFragmentation:
    def test_rules_declarative_pin(self):
        assert CREDIT_STRESS_RULES == (
            ("fragmentation_risk", ("both_up", "a_down_b_up")),
        )

    def test_fragmentation_both_up_is_credit_stress(self):
        """Спредове се разширяват ПРИ стягане (TPI candidate, 2011-2012)."""
        regime, driver = _classify_regime({
            "stagflation_test": "transition",
            "fragmentation_risk": "both_up",
        })
        assert regime == "credit_stress"
        assert driver == "fragmentation_risk"

    def test_fragmentation_widening_despite_easing_is_credit_stress(self):
        regime, _ = _classify_regime({
            "stagflation_test": "insufficient_data",
            "fragmentation_risk": "a_down_b_up",
        })
        assert regime == "credit_stress"

    def test_fragmentation_calm_is_not_credit_stress(self):
        regime, _ = _classify_regime({
            "stagflation_test": "transition",
            "fragmentation_risk": "a_up_b_down",  # стягане, спредове спокойни
        })
        assert regime != "credit_stress"

    def test_decisive_stagflation_beats_fragmentation(self):
        """Waterfall редът се пази: stag е primary, frag е fallback."""
        regime, driver = _classify_regime({
            "stagflation_test": "both_up",
            "fragmentation_risk": "both_up",
        })
        assert regime == "stagflation_confirmed"
        assert driver == "stagflation_test"


class TestEuGrowthLaborPair:
    def test_pair_exists_with_expected_anatomy(self):
        pair = next(
            (p for p in CROSS_LENS_PAIRS if p["id"] == "growth_labor_lead_lag"), None
        )
        assert pair is not None, "D2: growth_labor_lead_lag липсва от EU каталога"
        assert pair["slot_a"]["lens"] == "growth"
        assert pair["slot_a"]["peer_groups"] == ["hard_activity"]
        assert pair["slot_b"]["lens"] == "labor"
        assert set(pair["slot_b"]["peer_groups"]) == {"unemployment", "employment"}
        assert pair["slot_b"]["invert"] == {"unemployment": True}

    def test_pairs_config_still_validates(self):
        assert validate_pairs() == []

    def test_expansion_now_reachable(self):
        regime, driver = _classify_regime({
            "stagflation_test": "transition",
            "growth_labor_lead_lag": "both_up",
        })
        assert regime == "expansion"
        assert driver == "growth_labor_lead_lag"

    def test_slowdown_now_reachable(self):
        regime, _ = _classify_regime({
            "stagflation_test": "transition",
            "growth_labor_lead_lag": "both_down",
        })
        assert regime == "slowdown"


class TestConfidenceResolver:
    def test_indicated_and_confirmed_labels(self):
        assert resolve_regime_label_bg("stagflation_confirmed", "indicated") == \
            "Стагфлация (индикирана)"
        assert resolve_regime_label_bg("stagflation_confirmed", "confirmed") == \
            "Стагфлация (потвърдена)"

    def test_transition_has_no_variants(self):
        assert resolve_regime_label_bg("transition", "indicated") == "Преходно / смесено"
        assert resolve_regime_label_bg("transition", "confirmed") == "Преходно / смесено"

    def test_variant_maps_cover_taxonomy(self):
        assert set(REGIME_LABELS_BG_INDICATED) == set(REGIME_LABELS_BG)
