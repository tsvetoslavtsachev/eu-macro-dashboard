"""
catalog/cross_lens_pairs.py
===========================
Декларативен config на cross-lens divergence pairs за Eurozone версията.

Всяка pair представлява икономическа теза, която се проверява чрез съпоставка
на breadth между два "slot"-а — всеки slot е колекция от peer_groups,
евентуално с invert ако ↓ на peer_group трябва да се интерпретира като ↑
на темата (напр. unemployment ↓ → labor tightness ↑).

Структура на pair:
  id: уникален идентификатор
  name_bg, question_bg: човешки етикети (BG)
  slot_a, slot_b: dict с {lens, peer_groups, invert, label}
    invert: {peer_group_name: True/False}
  interpretations: dict с 5 стейта — both_up, both_down, a_up_b_down,
    a_down_b_up, transition

Phase 0 (текущ): празен списък. Phase 1/2 ще добави EA-specific pair-и
(напр. ECB transmission test, sovereign stress vs core spreads, etc.).

EA отличия от US (планирани pair-и):
  1. stagflation_test — тук "labor tightness" е по-плосък (EA labour markets
     по-малко flex), затова signal threshold ще е по-сензитивен
  2. ecb_transmission — НОВ — DFR vs sovereign spreads (ако ECB hike-ва, но
     spread-ове се разширяват, transmission е счупен)
  3. inflation_anchoring — HICP реализирана vs ECB SPF expectations
  4. credit_policy_transmission — bank lending volume vs CISS
  5. sentiment_vs_hard_data — ESI vs IP/Retail
  6. core_periphery_split — Bund vs BTP/OAT spreads (нов EA-specific concept)
"""
from __future__ import annotations


CROSS_LENS_PAIRS: list[dict] = [
    # TODO Phase 1/2: добави EA-specific pair-и (виж docstring за списъка)
]


# ============================================================
# VALIDATION
# ============================================================

REQUIRED_PAIR_FIELDS = frozenset({
    "id", "name_bg", "question_bg", "narrative",
    "slot_a", "slot_b", "interpretations",
})

REQUIRED_SLOT_FIELDS = frozenset({"lens", "peer_groups", "invert", "label"})

REQUIRED_INTERPRETATION_STATES = frozenset({
    "both_up", "both_down", "a_up_b_down", "a_down_b_up", "transition",
})


def validate_pairs(pairs: list[dict] = None) -> list[str]:
    """Валидира config-а. Връща списък с грешки (празен ако всичко OK)."""
    if pairs is None:
        pairs = CROSS_LENS_PAIRS

    errors: list[str] = []
    seen_ids: set[str] = set()

    for i, pair in enumerate(pairs):
        prefix = f"pair[{i}]"
        missing = REQUIRED_PAIR_FIELDS - set(pair.keys())
        if missing:
            errors.append(f"{prefix}: missing fields {missing}")
            continue

        pid = pair["id"]
        if pid in seen_ids:
            errors.append(f"{prefix}: duplicate id '{pid}'")
        seen_ids.add(pid)

        for slot_name in ("slot_a", "slot_b"):
            slot = pair[slot_name]
            missing_slot = REQUIRED_SLOT_FIELDS - set(slot.keys())
            if missing_slot:
                errors.append(f"{prefix}.{slot_name}: missing fields {missing_slot}")

        interp_states = set(pair["interpretations"].keys())
        missing_interp = REQUIRED_INTERPRETATION_STATES - interp_states
        if missing_interp:
            errors.append(f"{prefix}.interpretations: missing states {missing_interp}")

    return errors


# Module load-time validation
_validation_errors = validate_pairs()
if _validation_errors:
    import warnings
    warnings.warn(
        "cross_lens_pairs validation failed:\n  " + "\n  ".join(_validation_errors),
        UserWarning,
        stacklevel=2,
    )
