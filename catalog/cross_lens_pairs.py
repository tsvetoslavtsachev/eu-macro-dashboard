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
    # ─────────────────────────────────────────────────────────────
    # 1. stagflation_test
    #    Wage pressure (labor) × Services/Core inflation
    # ─────────────────────────────────────────────────────────────
    {
        "id": "stagflation_test",
        "name_bg": "Стагфлационен тест",
        "question_bg": "Заплатите ли движат услугите нагоре?",
        "narrative": (
            "Класически stagflation проба за EA. Wage pressure (compensation per "
            "employee) срещу sticky services inflation. EA labor pass-through по-бавен "
            "от US — threshold по-сензитивен. both_up = wage-price spiral risk."
        ),
        "slot_a": {
            "lens": "labor",
            "peer_groups": ["wages"],
            "invert": {},
            "label": "Натиск от заплати",
        },
        "slot_b": {
            "lens": "inflation",
            "peer_groups": ["core_measures"],
            "invert": {},
            "label": "Базова/услуги инфлация",
        },
        "interpretations": {
            "both_up": (
                "Стагфлационен риск: заплатите и базовата/услуги инфлация се "
                "движат заедно нагоре. Wage-price spiral начало."
            ),
            "both_down": (
                "Дезинфлация broad-based: и заплати, и базова отстъпват. "
                "ЕЦБ има пространство за политика."
            ),
            "a_up_b_down": (
                "Wage-led моментум без transfer към услугите още. "
                "Early warning — гледай дали ще пробие."
            ),
            "a_down_b_up": (
                "Sticky services без wage support — не sustainable. "
                "Очаквай корекция надолу в core."
            ),
            "transition": "Смесена картина — изчакай confirm на trend.",
        },
    },

    # ─────────────────────────────────────────────────────────────
    # 2. ecb_transmission
    #    Policy rates × Bank lending growth (inverted)
    # ─────────────────────────────────────────────────────────────
    {
        "id": "ecb_transmission",
        "name_bg": "Трансмисия на ЕЦБ политиката",
        "question_bg": "ЕЦБ hike-овете стигат ли до банковото кредитиране?",
        "narrative": (
            "Тества дали policy rate hikes се преобразуват в свиване на bank "
            "lending. Inversion на bank_lending: свиване (нисък YoY %) = "
            "restrictive transmission = high score. Convergent both_up = transmission works."
        ),
        "slot_a": {
            "lens": "ecb",
            "peer_groups": ["policy_rates"],
            "invert": {},
            "label": "Policy rates (DFR/MRO)",
        },
        "slot_b": {
            "lens": "credit",
            "peer_groups": ["bank_lending"],
            "invert": {"bank_lending": True},
            "label": "Банково кредитиране (свиване)",
        },
        "interpretations": {
            "both_up": (
                "Transmission работи: ECB hike-овете се преобразуват в свиване "
                "на банковото кредитиране. Restrictive stance ефективен."
            ),
            "both_down": (
                "Loose policy + експандиращо лендиране — стимулираща среда "
                "(2015-2019 NIRP epoch)."
            ),
            "a_up_b_down": (
                "ECB hike-ва, но lending не се свива — transmission lag или счупен. "
                "Risk: real economy не отчита restrictive stance."
            ),
            "a_down_b_up": (
                "ECB cuts, но lending не реагира. Тип balance sheet repair или "
                "demand-side слабост."
            ),
            "transition": "Смесена картина — типично около policy turning points.",
        },
    },

    # ─────────────────────────────────────────────────────────────
    # 3. fragmentation_risk
    #    Policy rates × Sovereign spreads (BTP/OAT-Bund)
    # ─────────────────────────────────────────────────────────────
    {
        "id": "fragmentation_risk",
        "name_bg": "Фрагментационен риск",
        "question_bg": "ЕЦБ hike-овете разширяват ли периферните spreads?",
        "narrative": (
            "Уникален EA cross-lens: tests дали ECB tightening активира "
            "fragmentation в periphery (BTP-Bund широк). both_up = TPI candidate. "
            "Hist precedent: 2011-2012 sovereign crisis."
        ),
        "slot_a": {
            "lens": "ecb",
            "peer_groups": ["policy_rates"],
            "invert": {},
            "label": "Policy rates",
        },
        "slot_b": {
            "lens": "credit",
            "peer_groups": ["sovereign_spreads"],
            "invert": {},
            "label": "Sovereign spreads (BTP/OAT-Bund)",
        },
        "interpretations": {
            "both_up": (
                "Fragmentation risk: hike-овете разширяват periphery spreads. "
                "Ако упорства — TPI activation candidate. 2011-2012 patron."
            ),
            "both_down": (
                "Cuts + сжимане на spreads — convergence trade. Stable EA core."
            ),
            "a_up_b_down": (
                "Hike-ове + сжимащи се spreads — smooth transmission, "
                "credible policy."
            ),
            "a_down_b_up": (
                "Cuts + разширяващи се spreads — necessary easing, но fragmentation "
                "продължава. Idiosyncratic country risk (Italy budget?)."
            ),
            "transition": "Mixed signals — гледай individual country drivers.",
        },
    },

    # ─────────────────────────────────────────────────────────────
    # 4. inflation_anchoring
    #    Headline inflation × ECB SPF expectations
    # ─────────────────────────────────────────────────────────────
    {
        "id": "inflation_anchoring",
        "name_bg": "Закотвеност на инфлационните очаквания",
        "question_bg": "Headline отскача — очакванията остават ли закотвени?",
        "narrative": (
            "Тест за credibility на ЕЦБ: headline инфлацията движение срещу "
            "long-term SPF expectations. both_up = de-anchoring risk; expectations "
            "drift проблем. Hist anchor band: SPF LT = 2.0% ± 0.2pp (post-2003)."
        ),
        "slot_a": {
            "lens": "inflation",
            "peer_groups": ["headline_measures"],
            "invert": {},
            "label": "Реализирана headline инфлация",
        },
        "slot_b": {
            "lens": "inflation",
            "peer_groups": ["expectations"],
            "invert": {},
            "label": "SPF дългосрочни очаквания",
        },
        "interpretations": {
            "both_up": (
                "De-anchoring risk: и реализирана и очаквания инфлация ↑. "
                "ЕЦБ credibility под въпрос — aggressive response justified."
            ),
            "both_down": (
                "Дезинфлация + expectations отстъпват — disinflation traction "
                "(BUT ниски expectations = deflation risk, ако < 1.5%)."
            ),
            "a_up_b_down": (
                "Headline ↑ но expectations стабилни/ниски — temporary shock "
                "interpretation; anchoring intact."
            ),
            "a_down_b_up": (
                "Headline ↓ но expectations ↑ — необичайно; може signal-ва "
                "data noise или rapidly shifting outlook."
            ),
            "transition": "Очакванията инерчни — обикновено след realisation.",
        },
    },

    # ─────────────────────────────────────────────────────────────
    # 5. pipeline_inflation
    #    PPI intermediate × HICP core
    # ─────────────────────────────────────────────────────────────
    {
        "id": "pipeline_inflation",
        "name_bg": "Pipeline инфлация",
        "question_bg": "PPI води ли core inflation?",
        "narrative": (
            "PPI (intermediate goods) исторически води consumer prices с 3-6mo lag. "
            "both_up = pipeline confirmed; PPI ↑ + core flat = lead-lag wait; "
            "PPI ↓ + core ↑ = services-driven sticky core."
        ),
        "slot_a": {
            "lens": "inflation",
            "peer_groups": ["producer_prices"],
            "invert": {},
            "label": "PPI междинни стоки",
        },
        "slot_b": {
            "lens": "inflation",
            "peer_groups": ["core_measures"],
            "invert": {},
            "label": "Core инфлация (HICP)",
        },
        "interpretations": {
            "both_up": (
                "Pipeline потвърден: производствени и потребителски цени ↑ заедно. "
                "Trend ще продължи 3-6mo lag-а."
            ),
            "both_down": (
                "Pipeline relief: PPI и core отстъпват — broad-based disinflation."
            ),
            "a_up_b_down": (
                "PPI водещ — core ще последва 3-6mo. Watch list."
            ),
            "a_down_b_up": (
                "Core sticky въпреки PPI облекчение — services-driven inflation; "
                "wage-price spiral индикатор."
            ),
            "transition": "Lead-lag relationship typically takes 3-6mo to resolve.",
        },
    },

    # ─────────────────────────────────────────────────────────────
    # 6. sentiment_vs_hard_data
    #    Growth sentiment × Hard activity
    # ─────────────────────────────────────────────────────────────
    {
        "id": "sentiment_vs_hard_data",
        "name_bg": "Очаквания срещу твърди данни",
        "question_bg": "Sentiment отразява ли реалната икономика?",
        "narrative": (
            "Sentiment (ESI, confidence indices) срещу hard data (IP, retail, GDP). "
            "Divergence е diagnostic: sentiment leading turning points 3-6mo. "
            "Soft data overshoot vs hard data lag."
        ),
        "slot_a": {
            "lens": "growth",
            "peer_groups": ["sentiment"],
            "invert": {},
            "label": "Sentiment (ESI, confidence)",
        },
        "slot_b": {
            "lens": "growth",
            "peer_groups": ["hard_activity"],
            "invert": {},
            "label": "Hard activity (IP, retail, GDP)",
        },
        "interpretations": {
            "both_up": (
                "Healthy expansion: sentiment + hard data confirm-ват растеж."
            ),
            "both_down": (
                "Broad-based weakness: sentiment + activity и двете слизат. "
                "Recession watch."
            ),
            "a_up_b_down": (
                "Soft data overshoot: optimism без real follow-through (yet). "
                "Early recovery signal или narrative bubble."
            ),
            "a_down_b_up": (
                "Narrative pessimism, но fundamentals OK. Sentiment trailing "
                "real activity — temporary."
            ),
            "transition": "Sentiment turn обикновено leads hard data 3-6mo.",
        },
    },
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
