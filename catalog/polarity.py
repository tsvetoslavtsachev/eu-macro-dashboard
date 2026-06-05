"""
catalog/polarity.py
===================
Полярностни решения за lens health scoring — ЕДИНЕН източник на истина (EU).

Виж ../macro-satellite/LENS_SCORING_METHODOLOGY.md §3. Същият метод като US/CN;
различното живее само в данните и знаците тук (решение Цветослав, 2026-06-04).

Типове: +1 · -1 · ("U","self") · ("U","target",X).
"""
from __future__ import annotations

from typing import Any

INFLATION_TARGET = 2.0  # % — ЕЦБ цел; U-център за HICP мерките

POLARITY: dict[str, Any] = {
    # LABOR / employment
    "EA_LFS_EMP": +1, "EA_EMPLOYMENT_PERSONS": +1,
    # LABOR / labor_sentiment
    "EA_EMPLOYMENT_EXP": +1, "EA_EMP_EXP_SERVICES": +1,
    # LABOR / unemployment
    "EA_UNRATE": -1, "EA_UNEMP_YOUTH": -1,
    # LABOR / wages (labor-смисъл: по-високи = по-силен труд)
    "EA_COMP_PER_EMPLOYEE": +1, "EA_WAGES_SALARIES": +1,

    # GROWTH / country_leading
    "NBB_BCI": +1, "SENTIX_EA": +1, "ZEW_EXPECTATIONS_DE": +1, "IFO_CLIMATE_DE": +1,
    # GROWTH / hard_activity
    "EA_IP": +1, "EA_RETAIL_VOL": +1, "EA_BUILDING_PRODUCTION": +1, "EA_GDP_QOQ": +1,
    # GROWTH / leading_indicators
    "EA_PERMIT_DW": +1,
    # GROWTH / sentiment
    "EA_ESI": +1, "EA_INDUSTRY_CONF": +1, "EA_CONSTRUCTION_CONF": +1,
    "EA_RETAIL_CONF": +1, "EA_CONSUMER_CONF": +1, "EA_SERVICES_CONF": +1,
    "EA_CAPACITY_UTIL": +1, "EA_PRODUCTION_EXP": +1,
    "EA_SELLING_PRICE_EXP": +1,   # в growth: ценова мощ = леко growth-позитив

    # INFLATION (U около целта ~2%)
    "EA_HICP_CORE": ("U", "target", INFLATION_TARGET),
    "EA_HICP_SERVICES": ("U", "target", INFLATION_TARGET),
    "EA_HICP_HEADLINE": ("U", "target", INFLATION_TARGET),
    "EA_HICP_ENERGY": ("U", "target", INFLATION_TARGET),
    "EA_HICP_FOOD": ("U", "target", INFLATION_TARGET),
    "EA_PPI_INTERMEDIATE": ("U", "target", INFLATION_TARGET),
    "EA_SPF_HICP_LT": ("U", "target", INFLATION_TARGET),
    "EA_INFL_SWAP_1Y": ("U", "target", INFLATION_TARGET),
    "EA_INFL_SWAP_2Y": ("U", "target", INFLATION_TARGET),
    "EA_INFL_SWAP_5Y": ("U", "target", INFLATION_TARGET),
    "EA_INFL_SWAP_5Y5Y_FWD": ("U", "target", INFLATION_TARGET),

    # CREDIT / bank_lending
    "EA_BANK_LOANS_NFC": +1, "EA_BANK_LOANS_HH": +1,
    # CREDIT / financial_stress
    "EA_CISS": -1,
    # CREDIT / monetary_aggregates (темп; намалено тегло)
    "EA_M3_YOY": +1,
    # CREDIT / sovereign_cds
    "DE_CDS_5Y": -1, "IT_CDS_5Y": -1, "ES_CDS_5Y": -1, "FR_CDS_5Y": -1,
    # CREDIT / sovereign_spreads
    "EA_BTP_BUND_SPREAD": -1, "EA_OAT_BUND_SPREAD": -1, "EA_BONO_BUND_SPREAD": -1,
    "EA_PT_BUND_SPREAD": -1, "EA_GR_BUND_SPREAD": -1,
    # CREDIT / sovereign_yields (в credit-здраве: по-високи = по-стегнато/стрес)
    "EA_BUND_10Y": -1, "EA_BUND_2Y": -1, "IT_10Y": -1, "FR_10Y": -1,
    "DE_10Y": -1, "ES_10Y": -1, "PT_10Y": -1, "GR_10Y": -1,
    # CREDIT / policy_stance (F-teardown 2026-06-05)
    "EA_REAL_DFR": -1,          # по-висока реална лихва = по-стегнато = по-нездраво
    "ECB_BALANCE_SHEET": +1,    # разширяване (QE) = по-облекчено = по-здраво

    # ════════════════════════════════════════════════════════
    # EXTERNAL (нова леща, F-редизайн 2026-06-05) — чиста полярност
    # под момент-скоринг (високо=зелено, без обръщане).
    # ════════════════════════════════════════════════════════
    # input_costs — по-висок темп на вносните разходи = по-нездраво
    "EA_IMPORT_PRICE_TOTAL": -1,
    "EA_IMPORT_PRICE_ENERGY": -1,
    "EA_IMPORT_PRICE_INTERMED": -1,
    # processing — разширяване на маржа/ToT = по-здраво
    "EA_MARGIN": +1,
    "EA_TOT_MONTHLY": +1,
    # external_balance — по-силен баланс/износ = по-здраво; рязка апресиация = по-зле
    "EA_TRADE_BALANCE": +1,
    "EA_EXPORT_VOLUME": +1,
    "EA_REER": -1,
}

# Multi-lens override: ценови очаквания в inflation лещата = U около норма (de-anchoring и в двете посоки)
POLARITY_BY_LENS: dict[tuple[str, str], Any] = {
    ("inflation", "EA_SELLING_PRICE_EXP"): ("U", "self"),
}

PEER_GROUP_WEIGHT: dict[str, float] = {
    "monetary_aggregates": 0.5,   # M3 — слаб сигнал, като US money_supply
}

U_BAND = 1.0


def polarity_for(key: str, lens: str | None = None) -> Any:
    if lens is not None and (lens, key) in POLARITY_BY_LENS:
        return POLARITY_BY_LENS[(lens, key)]
    return POLARITY.get(key, +1)


def peer_group_weight(pg: str) -> float:
    return PEER_GROUP_WEIGHT.get(pg, 1.0)
