"""
tests/test_executive.py
========================
Gate за REVIEW-03 точка 0.7 — EU клиентски наративи в analysis/executive.py
НЕ трябва да реферират "Fed" (US-specific наратив, изтекъл в EU репо).

ECB нейма dual mandate като Fed — затова "Fed е заклещен между двата мандата"
НЕ се превежда буквално, а като "ЕЦБ е заклещена между инфлацията и растежа".
"""
from __future__ import annotations

import re
from pathlib import Path

EXECUTIVE_PY = Path(__file__).resolve().parent.parent / "analysis" / "executive.py"


def _narrative_string_literals() -> list[str]:
    """Извлича само string литералите от _REGIME_OPENINGS и _find_counter_signal
    return statements — т.е. user-facing narrative текст, не docstring/коментари.
    """
    source = EXECUTIVE_PY.read_text(encoding="utf-8")
    # Първо премахваме module docstring-а (тройни кавички в началото на файла) и
    # ред-коментарите (#...) — те носят нарочно оставения TODO документиращ бъга
    # (redове 6-15), не user-facing narrative текст.
    source_no_docstring = re.sub(r'"""[\s\S]*?"""', "", source, count=1)
    source_no_comments = re.sub(r"#.*", "", source_no_docstring)
    # Извличаме само single/double-quoted literal стрингове с дължина >=20 —
    # това са изреченията в _REGIME_OPENINGS / _find_counter_signal.
    literals = re.findall(r'"([^"]{20,})"', source_no_comments)
    return literals


def test_no_fed_references_in_narrative_strings():
    """0 срещания на 'Fed' в narrative string литералите (REVIEW-03 т.0.7 gate).

    Коментари/docstring не се проверяват тук — само стойностите, които реално
    се пращат в quick briefing / macro_state narrative към клиента.
    """
    literals = _narrative_string_literals()
    offending = [s for s in literals if "Fed" in s]
    assert offending == [], (
        f"Намерени {len(offending)} narrative низа все още реферират 'Fed': {offending}"
    )


def test_ecb_soft_landing_opening_present():
    from analysis.executive import _REGIME_OPENINGS
    assert "ЕЦБ" in _REGIME_OPENINGS["soft_landing"]
    assert "Fed" not in _REGIME_OPENINGS["soft_landing"]


def test_ecb_policy_dilemma_opening_does_not_use_dual_mandate_literal():
    """ECB няма dual mandate — не превеждаме буквално 'двата мандата'."""
    from analysis.executive import _REGIME_OPENINGS
    opening = _REGIME_OPENINGS["policy_dilemma"]
    assert "ЕЦБ" in opening
    assert "Fed" not in opening
    assert "двата мандата" not in opening


def test_ecb_credit_stress_opening_present():
    from analysis.executive import _REGIME_OPENINGS
    assert "ЕЦБ" in _REGIME_OPENINGS["credit_stress"]
    assert "Fed" not in _REGIME_OPENINGS["credit_stress"]


def test_ecb_counter_signal_anchoring_present():
    """_find_counter_signal връща ECB narrative вместо Fed narrative за
    inflation_anchoring a_up_b_down случая."""
    from analysis.executive import _find_counter_signal

    class _FakePair:
        def __init__(self, pair_id, state):
            self.pair_id = pair_id
            self.state = state

    class _FakeCrossReport:
        pairs = [_FakePair("inflation_anchoring", "a_up_b_down")]

    result = _find_counter_signal("stagflation_confirmed", _FakeCrossReport())
    assert result is not None
    assert "ЕЦБ" in result
    assert "Fed" not in result
