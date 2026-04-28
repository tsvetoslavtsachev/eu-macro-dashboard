"""
catalog/series.py
=================
Декларативен каталог на Eurozone макро серии.

Това е единственото място, където една серия се описва: източник, ID,
регион, имена (BG/EN), лещи, peer_group за breadth, tags, трансформация,
исторически старт, release schedule, narrative hint.

Всички останали модули (analytics, modules, briefing) четат оттук, без да
дублират metadata.

Phase 1: началник set от потвърдени работещи серии (12). Phase 2 ще добави
повече когато confirm-нем точните Eurostat filter values за всеки dataset.

Поддържани източници:
  - "ecb"       — ECB Statistical Data Warehouse (data-api.ecb.europa.eu)
  - "eurostat"  — Eurostat REST API (ec.europa.eu/eurostat)
  - "oecd"      — OECD Data API (Phase 2 candidate)
  - "pending"   — placeholder (catalog знае за серията но adapter не ги издърпва)

Региони:
  - "EA"   — Euro Area aggregate (default scope за v1)
  - "EU"   — EU-27 (някои Eurostat серии са само EU-27)
  - "DE", "FR", "IT", "ES" — country drill-down (Phase 2)
  - "GLOBAL" — non-region (oil, FX и др.)

Лещи (5):
  - "labor"     — заетост, безработица, заплати
  - "inflation" — HICP, очаквания
  - "growth"    — IP, retail, GDP, sentiment
  - "credit"    — CISS, sovereign spreads, M3, банков lending
  - "ecb"       — ECB rates, balance sheet, TLTRO (нов lens, без US аналог)

Source ID формати:
  ECB:      "<flowref>/<key>"  напр. "CISS/D.U2.Z0Z.4F.EC.SS_CIN.IDX"
  Eurostat: "<dataset>?<filter_string>"  напр.
            "une_rt_m?geo=EA21&unit=PC_ACT&sex=T&age=TOTAL&s_adj=SA"

ВАЖНО: Eurostat geo кодът варира по dataset. EA21 (текущ Euro Area от 2026)
работи за `une_rt_m`, `sts_inpr_m`, но не за `prc_hicp_manr` — там ползваме
`EA` (auto-shifting aggregate). Винаги test-вай преди да добавиш серия.
"""
from __future__ import annotations
from typing import Any


# ============================================================
# WHITELISTS
# ============================================================

ALLOWED_SOURCES = {"ecb", "eurostat", "oecd", "pending"}
ALLOWED_REGIONS = {"EA", "EU", "DE", "FR", "IT", "ES", "GLOBAL"}
ALLOWED_LENSES = {"labor", "inflation", "growth", "credit", "ecb"}
ALLOWED_TRANSFORMS = {"level", "yoy_pct", "mom_pct", "qoq_pct", "z_score", "first_diff"}
ALLOWED_TAGS = {"non_consensus", "structural", "sovereign_stress"}
ALLOWED_SCHEDULES = {"weekly", "monthly", "quarterly", "annually"}


# ============================================================
# CATALOG
# ============================================================

SERIES_CATALOG: dict[str, dict[str, Any]] = {
    # ════════════════════════════════════════════════════════
    # LABOR (1)
    # ════════════════════════════════════════════════════════
    "EA_UNRATE": {
        "source": "eurostat",
        "id": "une_rt_m?geo=EA21&unit=PC_ACT&sex=T&age=TOTAL&s_adj=SA",
        "region": "EA",
        "name_bg": "Безработица (EA-21, headline)",
        "name_en": "Unemployment Rate (EA-21)",
        "lens": ["labor"],
        "peer_group": "unemployment",
        "tags": [],
        "transform": "level",
        "historical_start": "2000-01-01",
        "release_schedule": "monthly",
        "typical_release": "first_week",
        "revision_prone": False,
        "narrative_hint": "Headline unemployment rate за EA-21. Lagging indicator. "
                          "По-плосък в EA отколкото US (структурно).",
    },

    # ════════════════════════════════════════════════════════
    # INFLATION (3)
    # ════════════════════════════════════════════════════════
    "EA_HICP_HEADLINE": {
        "source": "eurostat",
        "id": "prc_hicp_manr?geo=EA&unit=RCH_A&coicop=CP00",
        "region": "EA",
        "name_bg": "HICP — всички продукти, YoY",
        "name_en": "HICP All Items, YoY",
        "lens": ["inflation"],
        "peer_group": "headline_measures",
        "tags": [],
        "transform": "level",  # вече е YoY % (RCH_A = "rate of change, annual")
        "historical_start": "1997-01-01",
        "release_schedule": "monthly",
        "typical_release": "mid_month",
        "revision_prone": True,  # flash → final ревизии
        "narrative_hint": "ЕЦБ-овият главен ценови индикатор. Single mandate target = 2% medium-term.",
    },
    "EA_HICP_CORE": {
        "source": "eurostat",
        "id": "prc_hicp_manr?geo=EA&unit=RCH_A&coicop=TOT_X_NRG_FOOD",
        "region": "EA",
        "name_bg": "HICP базова инфлация (excl. енергия и храни), YoY",
        "name_en": "HICP Core (excl. energy and food), YoY",
        "lens": ["inflation"],
        "peer_group": "core_measures",
        "tags": [],
        "transform": "level",
        "historical_start": "2001-12-01",
        "release_schedule": "monthly",
        "typical_release": "mid_month",
        "revision_prone": True,
        "narrative_hint": "Underlying inflation pressure без волатилните компоненти. "
                          "ЕЦБ преферира за анализ на trend.",
    },
    "EA_HICP_SERVICES": {
        "source": "eurostat",
        "id": "prc_hicp_manr?geo=EA&unit=RCH_A&coicop=SERV",
        "region": "EA",
        "name_bg": "HICP услуги, YoY",
        "name_en": "HICP Services, YoY",
        "lens": ["inflation"],
        "peer_group": "core_measures",
        "tags": [],
        "transform": "level",
        "historical_start": "2001-12-01",
        "release_schedule": "monthly",
        "typical_release": "mid_month",
        "revision_prone": True,
        "narrative_hint": "Sticky компонент на core inflation. Wage-sensitive — "
                          "leading indicator за core persistence.",
    },

    # ════════════════════════════════════════════════════════
    # GROWTH (1)
    # ════════════════════════════════════════════════════════
    "EA_IP": {
        "source": "eurostat",
        "id": "sts_inpr_m?geo=EA21&unit=I21&nace_r2=B-D&s_adj=CA",
        "region": "EA",
        "name_bg": "Промишлено производство (B-D), индекс 2021=100",
        "name_en": "Industrial Production (B-D), index 2021=100",
        "lens": ["growth"],
        "peer_group": "hard_activity",
        "tags": [],
        "transform": "yoy_pct",
        "historical_start": "1991-01-01",
        "release_schedule": "monthly",
        "typical_release": "mid_month",
        "revision_prone": True,
        "narrative_hint": "Hard activity indicator. Energy-intensive sectors водят "
                          "EA индекса (DE/IT композиция).",
    },

    # ════════════════════════════════════════════════════════
    # CREDIT (5) — CISS + sovereign yields + M3
    # ════════════════════════════════════════════════════════
    "EA_CISS": {
        "source": "ecb",
        "id": "CISS/D.U2.Z0Z.4F.EC.SS_CIN.IDX",
        "region": "EA",
        "name_bg": "CISS — Composite Indicator of Systemic Stress",
        "name_en": "Composite Indicator of Systemic Stress",
        "lens": ["credit"],
        "peer_group": "financial_stress",
        "tags": [],
        "transform": "level",
        "historical_start": "1980-01-03",
        "release_schedule": "weekly",
        "typical_release": "weekly_friday",
        "revision_prone": False,
        "narrative_hint": "ECB-овият композитен financial stress индикатор. "
                          "Заместител на STLFSI/NFCI от US версията. "
                          "Стойности > 0.2 → значителен системен стрес.",
    },
    "EA_M3_YOY": {
        "source": "ecb",
        "id": "BSI/M.U2.Y.V.M30.X.I.U2.2300.Z01.A",
        "region": "EA",
        "name_bg": "M3 паричен агрегат, годишен ръст",
        "name_en": "M3 Monetary Aggregate, YoY growth",
        "lens": ["credit"],
        "peer_group": "monetary_aggregates",
        "tags": [],
        "transform": "level",  # вече е YoY %
        "historical_start": "1981-01-01",
        "release_schedule": "monthly",
        "typical_release": "end_month",
        "revision_prone": False,
        "narrative_hint": "ЕЦБ-овият референтен monetary aggregate. "
                          "Историческа вторична mandate (1999-2003), сега secondary indicator.",
    },
    "EA_BUND_10Y": {
        "source": "ecb",
        "id": "FM/M.U2.EUR.4F.BB.U2_10Y.YLD",
        "region": "EA",
        "name_bg": "Bund 10Y benchmark yield",
        "name_en": "EA 10Y Government Bond Yield (Bund proxy)",
        "lens": ["credit"],
        "peer_group": "sovereign_yields",
        "tags": [],
        "transform": "level",
        "historical_start": "1970-01-01",
        "release_schedule": "monthly",
        "typical_release": "monthly",
        "revision_prone": False,
        "narrative_hint": "EA-aggregate 10Y yield (ECB compiled). Risk-free benchmark "
                          "за европейските пазари.",
    },
    "EA_BUND_2Y": {
        "source": "ecb",
        "id": "FM/M.U2.EUR.4F.BB.U2_2Y.YLD",
        "region": "EA",
        "name_bg": "Bund 2Y benchmark yield",
        "name_en": "EA 2Y Government Bond Yield",
        "lens": ["credit"],
        "peer_group": "sovereign_yields",
        "tags": [],
        "transform": "level",
        "historical_start": "1970-01-01",
        "release_schedule": "monthly",
        "typical_release": "monthly",
        "revision_prone": False,
        "narrative_hint": "EA-aggregate 2Y yield. Curve slope (10Y-2Y) проксира "
                          "policy expectations и recession risk.",
    },
    "IT_10Y": {
        "source": "ecb",
        "id": "IRS/M.IT.L.L40.CI.0000.EUR.N.Z",
        "region": "IT",
        "name_bg": "Italy 10Y government bond yield",
        "name_en": "Italy 10Y Government Bond Yield",
        "lens": ["credit"],
        "peer_group": "sovereign_yields",
        "tags": ["sovereign_stress"],
        "transform": "level",
        "historical_start": "1993-01-01",
        "release_schedule": "monthly",
        "typical_release": "monthly",
        "revision_prone": False,
        "narrative_hint": "Italy sovereign yield — компонент на BTP-Bund spread. "
                          "Главен periphery stress proxy.",
    },
    "FR_10Y": {
        "source": "ecb",
        "id": "IRS/M.FR.L.L40.CI.0000.EUR.N.Z",
        "region": "FR",
        "name_bg": "France 10Y government bond yield",
        "name_en": "France 10Y Government Bond Yield",
        "lens": ["credit"],
        "peer_group": "sovereign_yields",
        "tags": [],
        "transform": "level",
        "historical_start": "1993-01-01",
        "release_schedule": "monthly",
        "typical_release": "monthly",
        "revision_prone": False,
        "narrative_hint": "France sovereign yield — компонент на OAT-Bund spread. "
                          "Core-but-not-DE EA stress indicator.",
    },
    "DE_10Y": {
        "source": "ecb",
        "id": "IRS/M.DE.L.L40.CI.0000.EUR.N.Z",
        "region": "DE",
        "name_bg": "Germany 10Y Bund yield (Maastricht measure)",
        "name_en": "Germany 10Y Bund Yield (Maastricht)",
        "lens": ["credit"],
        "peer_group": "sovereign_yields",
        "tags": [],
        "transform": "level",
        "historical_start": "1993-01-01",
        "release_schedule": "monthly",
        "typical_release": "monthly",
        "revision_prone": False,
        "narrative_hint": "Germany 10Y, Maastricht-criterion measure. Reference за "
                          "BTP-Bund / OAT-Bund spread изчисления.",
    },

    # ════════════════════════════════════════════════════════
    # ECB POLICY (4) — Rates + balance sheet
    # ════════════════════════════════════════════════════════
    "ECB_DFR": {
        "source": "ecb",
        "id": "FM/D.U2.EUR.4F.KR.DFR.LEV",
        "region": "EA",
        "name_bg": "ЕЦБ — Лихва по депозитната улеснение (DFR)",
        "name_en": "ECB Deposit Facility Rate",
        "lens": ["ecb"],
        "peer_group": "policy_rates",
        "tags": [],
        "transform": "level",
        "historical_start": "1999-01-01",
        "release_schedule": "weekly",  # промяна на decision dates, иначе static
        "typical_release": "ad_hoc",
        "revision_prone": False,
        "narrative_hint": "Главната policy rate след 2014 (когато DFR стана binding). "
                          "Replaces FEDFUNDS от US версията.",
    },
    "ECB_MRO": {
        "source": "ecb",
        "id": "FM/D.U2.EUR.4F.KR.MRR_FR.LEV",
        "region": "EA",
        "name_bg": "ЕЦБ — Лихва по MRO операции",
        "name_en": "ECB Main Refinancing Operations Rate",
        "lens": ["ecb"],
        "peer_group": "policy_rates",
        "tags": [],
        "transform": "level",
        "historical_start": "1999-01-01",
        "release_schedule": "weekly",
        "typical_release": "ad_hoc",
        "revision_prone": False,
        "narrative_hint": "Refi rate. Binding до 2014, после secondary signal.",
    },
    "ECB_MLF": {
        "source": "ecb",
        "id": "FM/D.U2.EUR.4F.KR.MLFR.LEV",
        "region": "EA",
        "name_bg": "ЕЦБ — Лихва по marginal lending facility",
        "name_en": "ECB Marginal Lending Facility Rate",
        "lens": ["ecb"],
        "peer_group": "policy_rates",
        "tags": [],
        "transform": "level",
        "historical_start": "1999-01-01",
        "release_schedule": "weekly",
        "typical_release": "ad_hoc",
        "revision_prone": False,
        "narrative_hint": "Upper bound на коридорa. Сигнал за liquidity stress ако се ползва.",
    },
    "ECB_BALANCE_SHEET": {
        "source": "ecb",
        "id": "BSI/M.U2.N.A.A20.A.1.U2.0000.Z01.E",
        "region": "EA",
        "name_bg": "ЕЦБ — общи активи (баланс)",
        "name_en": "ECB Total Assets (Balance Sheet)",
        "lens": ["ecb"],
        "peer_group": "balance_sheet",
        "tags": [],
        "transform": "yoy_pct",  # анализираме trend, не level
        "historical_start": "1997-09-01",
        "release_schedule": "monthly",
        "typical_release": "mid_month",
        "revision_prone": False,
        "narrative_hint": "Sum total assets — отразява APP/PEPP покупки и TLTRO. "
                          "Trend (растеж/свиване) e key QE/QT signal.",
    },
}


# ============================================================
# QUERY HELPERS
# ============================================================

def get_series(key: str) -> dict[str, Any]:
    """Връща конкретна серия по ключ. Хвърля KeyError ако липсва."""
    if key not in SERIES_CATALOG:
        raise KeyError(f"Серия '{key}' не съществува в catalog.")
    return SERIES_CATALOG[key]


def series_by_lens(lens: str) -> list[dict[str, Any]]:
    """Всички серии, принадлежащи към дадена леща (вкл. multi-lens)."""
    return [
        {**meta, "_key": k}
        for k, meta in SERIES_CATALOG.items()
        if lens in meta.get("lens", [])
    ]


def series_by_peer_group(group: str) -> list[dict[str, Any]]:
    """Всички серии в конкретна peer group."""
    return [
        {**meta, "_key": k}
        for k, meta in SERIES_CATALOG.items()
        if meta.get("peer_group") == group
    ]


def series_by_tag(tag: str) -> list[dict[str, Any]]:
    """Всички серии със специфичен tag (напр. 'non_consensus')."""
    return [
        {**meta, "_key": k}
        for k, meta in SERIES_CATALOG.items()
        if tag in meta.get("tags", [])
    ]


def all_series_ids() -> list[str]:
    """Всички каталожни ключове."""
    return list(SERIES_CATALOG.keys())


def series_by_source(source: str) -> list[dict[str, Any]]:
    """Всички серии от конкретен източник ('ecb', 'eurostat', 'oecd', 'pending')."""
    return [
        {**meta, "_key": k}
        for k, meta in SERIES_CATALOG.items()
        if meta.get("source") == source
    ]


# ============================================================
# VALIDATION
# ============================================================

def validate_catalog() -> list[str]:
    """Проверява, че всички записи имат задължителните полета с валидни стойности."""
    required_fields = {
        "source", "id", "region", "name_bg", "name_en",
        "lens", "peer_group", "tags", "transform",
        "historical_start", "release_schedule", "typical_release",
        "revision_prone", "narrative_hint",
    }

    errors: list[str] = []

    for key, meta in SERIES_CATALOG.items():
        missing = required_fields - set(meta.keys())
        if missing:
            errors.append(f"{key}: липсват полета {missing}")
            continue

        if meta["source"] not in ALLOWED_SOURCES:
            errors.append(f"{key}: невалиден source '{meta['source']}'")
        if meta["region"] not in ALLOWED_REGIONS:
            errors.append(f"{key}: невалиден region '{meta['region']}'")
        if meta["transform"] not in ALLOWED_TRANSFORMS:
            errors.append(f"{key}: невалиден transform '{meta['transform']}'")
        if meta["release_schedule"] not in ALLOWED_SCHEDULES:
            errors.append(f"{key}: невалиден release_schedule '{meta['release_schedule']}'")
        for lens in meta["lens"]:
            if lens not in ALLOWED_LENSES:
                errors.append(f"{key}: невалидна lens '{lens}'")
        for tag in meta["tags"]:
            if tag not in ALLOWED_TAGS:
                errors.append(f"{key}: невалиден tag '{tag}'")
        if not isinstance(meta["revision_prone"], bool):
            errors.append(f"{key}: revision_prone трябва да е bool")

    return errors


# ============================================================
# MODULE LOAD-TIME VALIDATION
# ============================================================

_validation_errors = validate_catalog()
if _validation_errors:
    import warnings
    warnings.warn(
        "Catalog validation failed:\n  " + "\n  ".join(_validation_errors),
        UserWarning,
        stacklevel=2,
    )
