"""
catalog/series.py
=================
Декларативен каталог на Eurozone макро серии.

Това е единственото място, където една серия се описва: източник, ID,
регион, имена (BG/EN), лещи, peer_group за breadth, tags, трансформация,
исторически старт, release schedule, narrative hint, is_rate.

Всички останали модули (analytics, modules, briefing) четат оттук, без да
дублират metadata.

Phase 1.5: 36 confirmed серии (30 baseline + 6 нови от indicator review).

Поддържани източници:
  - "ecb"       — ECB Statistical Data Warehouse (data-api.ecb.europa.eu)
  - "eurostat"  — Eurostat REST API (ec.europa.eu/eurostat)
  - "derived"   — computed от други серии (BTP-Bund spread = IT_10Y - DE_10Y)
  - "oecd"      — OECD Data API (Phase 2 candidate)
  - "pending"   — placeholder (catalog знае за серията но adapter не ги издърпва)

Региони:
  - "EA"   — Euro Area aggregate (default scope за v1)
  - "EU"   — EU-27 (някои Eurostat серии са само EU-27)
  - "DE", "FR", "IT", "ES" — country drill-down (Phase 2)
  - "GLOBAL" — non-region (oil, FX и др.)

Лещи (5):
  - "labor"     — заетост, безработица, заплати
  - "inflation" — HICP, очаквания, PPI pipeline
  - "growth"    — IP, retail, GDP, sentiment
  - "credit"    — CISS, sovereign spreads, M3, банков lending
  - "ecb"       — ECB rates, balance sheet, TLTRO (нов lens, без US аналог)

Source ID формати:
  ECB:      "<flowref>/<key>"  напр. "CISS/D.U2.Z0Z.4F.EC.SS_CIN.IDX"
  Eurostat: "<dataset>?<filter_string>"  напр.
            "une_rt_m?geo=EA21&unit=PC_ACT&sex=T&age=TOTAL&s_adj=SA"
  Derived:  "<expression>"  напр. "IT_10Y - DE_10Y"

ВАЖНО: Eurostat geo кодът варира по dataset. EA21 (текущ Euro Area от 2026)
работи за `une_rt_m`, `sts_inpr_m`, но не за `prc_hicp_manr` — там ползваме
`EA` (auto-shifting aggregate). Винаги test-вай преди да добавиш серия.

is_rate field semantics:
  - True: values (post-transform) са rate / percentage. YoY display ползва pp delta.
  - False: values са index / balance / level. YoY display ползва relative %.
"""
from __future__ import annotations
from typing import Any


# ============================================================
# WHITELISTS
# ============================================================

ALLOWED_SOURCES = {"ecb", "eurostat", "oecd", "derived", "pending", "bloomberg_bridge"}
ALLOWED_REGIONS = {"EA", "EU", "DE", "FR", "IT", "ES", "PT", "GR", "BE", "GLOBAL"}
ALLOWED_LENSES = {"labor", "inflation", "growth", "credit", "ecb"}
ALLOWED_TRANSFORMS = {"level", "yoy_pct", "mom_pct", "qoq_pct", "z_score", "first_diff"}
ALLOWED_TAGS = {"non_consensus", "structural", "sovereign_stress"}
ALLOWED_SCHEDULES = {"daily", "weekly", "monthly", "quarterly", "annually"}


# ============================================================
# CATALOG
# ============================================================

SERIES_CATALOG: dict[str, dict[str, Any]] = {
    # ════════════════════════════════════════════════════════
    # LABOR (8) — unemployment, employment, wages, labor_sentiment
    # Всяка peer-група има ≥2 серии (de-singleton, за да скорира лещата).
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
        "is_rate": True,
        "historical_start": "2000-01-01",
        "release_schedule": "monthly",
        "typical_release": "first_week",
        "revision_prone": False,
        "narrative_hint": "Headline unemployment rate за EA-21. Lagging indicator. "
                          "По-плосък в EA отколкото US (структурно).",
    },
    "EA_LFS_EMP": {
        "source": "eurostat",
        "id": "lfsi_emp_q?geo=EA21&indic_em=EMP_LFS&s_adj=SA&sex=T&age=Y20-64&unit=PC_POP",
        "region": "EA",
        "name_bg": "Заетост (LFS, 20-64г, % от популация)",
        "name_en": "Employment Rate (LFS, age 20-64, % of population)",
        "lens": ["labor"],
        "peer_group": "employment",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2009-01-01",
        "release_schedule": "quarterly",
        "typical_release": "mid_quarter",
        "revision_prone": False,
        "narrative_hint": "Employment rate from EU Labour Force Survey. По-структурен "
                          "indicator от unemployment — отчита и неактивните.",
    },
    "EA_EMPLOYMENT_EXP": {
        "source": "eurostat",
        "id": "teibs030?geo=EA21&indic=BS-EEI-I&s_adj=SA",
        "region": "EA",
        "name_bg": "Очаквания за заетост (3m напред)",
        "name_en": "Employment Expectations Indicator (next 3 months)",
        "lens": ["labor"],
        "peer_group": "labor_sentiment",
        "tags": [],
        "transform": "level",
        "is_rate": False,
        "historical_start": "2025-05-01",
        "release_schedule": "monthly",
        "typical_release": "end_month",
        "revision_prone": False,
        "narrative_hint": "DG ECFIN survey: forward-looking labor signal. "
                          "Limited history (only 12 months in teibs030 dataset).",
    },
    "EA_COMP_PER_EMPLOYEE": {
        "source": "eurostat",
        "id": "namq_10_a10?geo=EA20&unit=CP_MEUR&nace_r2=TOTAL&na_item=D1&s_adj=SCA",
        "region": "EA",
        "name_bg": "Компенсация на наетите (D1, EA-20, M€)",
        "name_en": "Compensation of Employees (D1, EA-20, EUR mln)",
        "lens": ["labor"],
        "peer_group": "wages",
        "tags": [],
        "transform": "yoy_pct",
        "is_rate": True,
        "historical_start": "1995-01-01",
        "release_schedule": "quarterly",
        "typical_release": "mid_quarter",
        "revision_prone": True,
        "narrative_hint": "Quarterly compensation of employees aggregate (EA-20). "
                          "YoY growth е headline wage signal — lagged 1Q. "
                          "Активира stagflation cross-lens срещу HICP services.",
    },

    # ─── Втори членове на labor peer-групите (Phase EU.labor, 2026-06-03) ───
    # Добавени за да скорира labor lens-ът: всяка singleton група получава 2-ри
    # серия със същата полярност (sign-consistent breadth). Всички verified
    # през EurostatAdapter — теглят свежи данни. Виж HANDOFF-eu-labor-dbnomics.md.
    "EA_UNEMP_YOUTH": {
        "source": "eurostat",
        "id": "une_rt_m?geo=EA21&unit=PC_ACT&sex=T&age=Y_LT25&s_adj=SA",
        "region": "EA",
        "name_bg": "Младежка безработица (под 25г, EA-21)",
        "name_en": "Youth Unemployment Rate (under 25, EA-21)",
        "lens": ["labor"],
        "peer_group": "unemployment",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2000-01-01",
        "release_schedule": "monthly",
        "typical_release": "first_week",
        "revision_prone": False,
        "narrative_hint": "Под-25 безработица — по-cyclical и leading спрямо headline "
                          "(EA_UNRATE). Същата полярност (higher=worse). "
                          "De-singleton-ва unemployment peer-групата.",
    },
    "EA_EMPLOYMENT_PERSONS": {
        "source": "eurostat",
        "id": "namq_10_a10_e?geo=EA20&na_item=EMP_DC&unit=THS_PER&nace_r2=TOTAL&s_adj=SCA",
        "region": "EA",
        "name_bg": "Заетост — брой наети (нац. сметки, EA-20, хил. лица)",
        "name_en": "Employment — Persons (national accounts, EA-20, thousands)",
        "lens": ["labor"],
        "peer_group": "employment",
        "tags": [],
        "transform": "yoy_pct",
        "is_rate": True,
        "historical_start": "1995-01-01",
        "release_schedule": "quarterly",
        "typical_release": "mid_quarter",
        "revision_prone": True,
        "narrative_hint": "Домашна концепция за заетост (брой наети) от тримесечните "
                          "нац. сметки. Допълва employment RATE (EA_LFS_EMP) с обемен "
                          "сигнал — същата полярност. De-singleton-ва employment.",
    },
    "EA_WAGES_SALARIES": {
        "source": "eurostat",
        "id": "namq_10_a10?geo=EA20&unit=CP_MEUR&nace_r2=TOTAL&na_item=D11&s_adj=SCA",
        "region": "EA",
        "name_bg": "Работни заплати (D11, EA-20, M€)",
        "name_en": "Wages and Salaries (D11, EA-20, EUR mln)",
        "lens": ["labor"],
        "peer_group": "wages",
        "tags": [],
        "transform": "yoy_pct",
        "is_rate": True,
        "historical_start": "1995-01-01",
        "release_schedule": "quarterly",
        "typical_release": "mid_quarter",
        "revision_prone": True,
        "narrative_hint": "Работни заплати (D11 = компенсация без работодателските "
                          "социални вноски D12). Допълва общата компенсация D1 "
                          "(EA_COMP_PER_EMPLOYEE) — същата полярност. De-singleton-ва wages.",
    },
    "EA_EMP_EXP_SERVICES": {
        "source": "eurostat",
        "id": "ei_bsse_m_r2?geo=EA21&indic=BS-SEEM&s_adj=SA&unit=BAL",
        "region": "EA",
        "name_bg": "Очаквания за заетост — услуги (3m напред)",
        "name_en": "Employment Expectations — Services (next 3 months)",
        "lens": ["labor"],
        "peer_group": "labor_sentiment",
        "tags": [],
        "transform": "level",
        "is_rate": False,
        "historical_start": "1996-04-01",
        "release_schedule": "monthly",
        "typical_release": "end_month",
        "revision_prone": False,
        "narrative_hint": "DG ECFIN survey: forward-looking labor сигнал от услугите "
                          "(~70% от GDP). Дълга история (от 1996) — за разлика от "
                          "teibs030 (EA_EMPLOYMENT_EXP, 12m). Същата полярност "
                          "(higher=better). De-singleton-ва labor_sentiment.",
    },

    # ════════════════════════════════════════════════════════
    # INFLATION (6) — HICP family + SPF + PPI pipeline
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
        "transform": "level",
        "is_rate": True,
        "historical_start": "1997-01-01",
        "release_schedule": "monthly",
        "typical_release": "mid_month",
        "revision_prone": True,
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
        "is_rate": True,
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
        "is_rate": True,
        "historical_start": "2001-12-01",
        "release_schedule": "monthly",
        "typical_release": "mid_month",
        "revision_prone": True,
        "narrative_hint": "Sticky компонент на core inflation. Wage-sensitive — "
                          "leading indicator за core persistence.",
    },
    "EA_HICP_ENERGY": {
        "source": "eurostat",
        "id": "prc_hicp_manr?geo=EA&unit=RCH_A&coicop=NRG",
        "region": "EA",
        "name_bg": "HICP енергия, YoY",
        "name_en": "HICP Energy, YoY",
        "lens": ["inflation"],
        "peer_group": "headline_measures",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "1997-01-01",
        "release_schedule": "monthly",
        "typical_release": "mid_month",
        "revision_prone": True,
        "narrative_hint": "Volatile component на headline. Oil shock dependent. "
                          "Headline-core gap explainer; de-singleton-ва headline_measures.",
    },
    "EA_HICP_FOOD": {
        "source": "eurostat",
        "id": "prc_hicp_manr?geo=EA&unit=RCH_A&coicop=FOOD",
        "region": "EA",
        "name_bg": "HICP храни, YoY",
        "name_en": "HICP Food, YoY",
        "lens": ["inflation"],
        "peer_group": "headline_measures",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "1997-01-01",
        "release_schedule": "monthly",
        "typical_release": "mid_month",
        "revision_prone": True,
        "narrative_hint": "Food prices — supply-side shock proxy (drought, war). "
                          "По-малко volatile от energy, но social impact силен.",
    },
    "EA_SPF_HICP_LT": {
        "source": "ecb",
        "id": "SPF/Q.U2.HICP.POINT.LT.Q.001",
        "region": "EA",
        "name_bg": "ECB SPF — HICP long-term очаквания",
        "name_en": "ECB SPF Long-term HICP Inflation Expectations",
        "lens": ["inflation"],
        "peer_group": "expectations",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "1999-01-01",
        "release_schedule": "quarterly",
        "typical_release": "end_quarter",
        "revision_prone": False,
        "narrative_hint": "Survey of Professional Forecasters point estimate за "
                          "long-term inflation. Anchored индикатор: ~2% target. "
                          "Дeviation > 0.3pp от target е значителен.",
    },
    "EA_PPI_INTERMEDIATE": {
        "source": "eurostat",
        "id": "sts_inpp_m?geo=EA20&unit=I21&nace_r2=MIG_ING&s_adj=NSA&indic_bt=PRC_PRR",
        "region": "EA",
        "name_bg": "PPI междинни стоки (MIG ING, индекс 2021=100)",
        "name_en": "PPI Intermediate Goods (MIG ING, index 2021=100)",
        "lens": ["inflation"],
        "peer_group": "producer_prices",
        "tags": [],
        "transform": "yoy_pct",
        "is_rate": True,
        "historical_start": "2000-01-01",
        "release_schedule": "monthly",
        "typical_release": "first_week",
        "revision_prone": True,
        "narrative_hint": "Producer prices, intermediate goods (proxy за nonenergy PPI). "
                          "Leading indicator на consumer goods inflation 3-6mo lag. "
                          "Активира pipeline_inflation cross-lens срещу HICP core.",
    },

    # ════════════════════════════════════════════════════════
    # GROWTH (10) — hard activity, leading indicators, sentiment
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
        "is_rate": True,
        "historical_start": "1991-01-01",
        "release_schedule": "monthly",
        "typical_release": "mid_month",
        "revision_prone": True,
        "narrative_hint": "Hard activity indicator. Energy-intensive sectors водят "
                          "EA индекса (DE/IT композиция).",
    },
    "EA_RETAIL_VOL": {
        "source": "eurostat",
        "id": "sts_trtu_m?geo=EA21&s_adj=SCA&unit=I21&nace_r2=G47&indic_bt=VOL_SLS",
        "region": "EA",
        "name_bg": "Търговия на дребно — обем на продажбите (G47, индекс 2021=100)",
        "name_en": "Retail Trade Volume of Sales (G47, index 2021=100)",
        "lens": ["growth"],
        "peer_group": "hard_activity",
        "tags": [],
        "transform": "yoy_pct",
        "is_rate": True,
        "historical_start": "2000-01-01",
        "release_schedule": "monthly",
        "typical_release": "first_week",
        "revision_prone": True,
        "narrative_hint": "Consumer spending proxy. По-стабилна от IP — services-driven EA.",
    },
    "EA_BUILDING_PRODUCTION": {
        "source": "eurostat",
        "id": "ei_isbu_m?geo=EA21&s_adj=SCA&unit=I2021&indic=IS-IP&nace_r2=F",
        "region": "EA",
        "name_bg": "Строително производство (F, индекс 2021=100)",
        "name_en": "Construction Production Index (F, index 2021=100)",
        "lens": ["growth"],
        "peer_group": "hard_activity",
        "tags": [],
        "transform": "yoy_pct",
        "is_rate": True,
        "historical_start": "1995-01-01",
        "release_schedule": "monthly",
        "typical_release": "mid_month",
        "revision_prone": True,
        "narrative_hint": "Construction sector activity. Cyclical — лагира interest rates "
                          "и building permits.",
    },
    "EA_PERMIT_DW": {
        "source": "eurostat",
        "id": "sts_cobp_m?geo=EA21&s_adj=SCA&unit=I21&indic_bt=BPRM_DW",
        "region": "EA",
        "name_bg": "Разрешения за строеж (жилищни сгради, индекс 2021=100)",
        "name_en": "Building Permits — Dwellings (index 2021=100)",
        "lens": ["growth"],
        "peer_group": "leading_indicators",
        "tags": [],
        "transform": "yoy_pct",
        "is_rate": True,
        "historical_start": "2005-01-01",
        "release_schedule": "monthly",
        "typical_release": "mid_month",
        "revision_prone": True,
        "narrative_hint": "Leading indicator за construction activity. Първи sign на "
                          "real estate cycle turning.",
    },
    "EA_GDP_QOQ": {
        "source": "eurostat",
        "id": "namq_10_gdp?geo=EA21&unit=CLV15_MEUR&s_adj=SCA&na_item=B1GQ",
        "region": "EA",
        "name_bg": "Реален БВП (chained volumes, M€)",
        "name_en": "Real GDP (chained volumes, EUR millions)",
        "lens": ["growth"],
        "peer_group": "hard_activity",
        "tags": [],
        "transform": "qoq_pct",
        "is_rate": True,
        "historical_start": "1995-01-01",
        "release_schedule": "quarterly",
        "typical_release": "mid_quarter",
        "revision_prone": True,
        "narrative_hint": "Headline real GDP. QoQ % е стандартното quarterly EA reporting.",
    },
    "EA_ESI": {
        "source": "eurostat",
        "id": "teibs010?geo=EA21&indic=BS-ESI-I&s_adj=SA",
        "region": "EA",
        "name_bg": "Икономически Sentiment Indicator (DG ECFIN ESI)",
        "name_en": "Economic Sentiment Indicator (DG ECFIN)",
        "lens": ["growth"],
        "peer_group": "sentiment",
        "tags": [],
        "transform": "level",
        "is_rate": False,
        "historical_start": "2025-05-01",
        "release_schedule": "monthly",
        "typical_release": "end_month",
        "revision_prone": False,
        "narrative_hint": "Composite sentiment indicator (ESI ≈ ISM PMI EA equivalent). "
                          "Заместител на US PMI. Limited history в teibs010 (12 months).",
    },
    "EA_INDUSTRY_CONF": {
        "source": "eurostat",
        "id": "teibs020?geo=EA21&indic=BS-ICI-BAL&s_adj=SA",
        "region": "EA",
        "name_bg": "Доверие в промишлеността (DG ECFIN)",
        "name_en": "Industry Confidence Indicator (DG ECFIN)",
        "lens": ["growth"],
        "peer_group": "sentiment",
        "tags": [],
        "transform": "level",
        "is_rate": False,
        "historical_start": "2025-05-01",
        "release_schedule": "monthly",
        "typical_release": "end_month",
        "revision_prone": False,
        "narrative_hint": "Sectoral confidence — industry. Limited history в teibs020.",
    },
    "EA_CONSTRUCTION_CONF": {
        "source": "eurostat",
        "id": "teibs020?geo=EA21&indic=BS-CCI-BAL&s_adj=SA",
        "region": "EA",
        "name_bg": "Доверие в строителството (DG ECFIN)",
        "name_en": "Construction Confidence Indicator (DG ECFIN)",
        "lens": ["growth"],
        "peer_group": "sentiment",
        "tags": [],
        "transform": "level",
        "is_rate": False,
        "historical_start": "2025-05-01",
        "release_schedule": "monthly",
        "typical_release": "end_month",
        "revision_prone": False,
        "narrative_hint": "Sectoral confidence — construction. Limited history в teibs020.",
    },
    "EA_RETAIL_CONF": {
        "source": "eurostat",
        "id": "teibs020?geo=EA21&indic=BS-RCI-BAL&s_adj=SA",
        "region": "EA",
        "name_bg": "Доверие в търговията на дребно (DG ECFIN)",
        "name_en": "Retail Confidence Indicator (DG ECFIN)",
        "lens": ["growth"],
        "peer_group": "sentiment",
        "tags": [],
        "transform": "level",
        "is_rate": False,
        "historical_start": "2025-05-01",
        "release_schedule": "monthly",
        "typical_release": "end_month",
        "revision_prone": False,
        "narrative_hint": "Sectoral confidence — retail. Limited history в teibs020.",
    },
    "EA_CONSUMER_CONF": {
        "source": "eurostat",
        "id": "ei_bsco_m?geo=EA21&indic=BS-CSMCI&s_adj=SA&unit=BAL",
        "region": "EA",
        "name_bg": "Потребителско доверие (DG ECFIN, full history от 1985)",
        "name_en": "Consumer Confidence Indicator (DG ECFIN)",
        "lens": ["growth"],
        "peer_group": "sentiment",
        "tags": [],
        "transform": "level",
        "is_rate": False,
        "historical_start": "1985-01-01",
        "release_schedule": "monthly",
        "typical_release": "end_month",
        "revision_prone": False,
        "narrative_hint": "Pre-EMU история (1985+). Negative balance е норма; отклонения "
                          "от mean показват consumer sentiment shifts.",
    },
    "EA_SERVICES_CONF": {
        "source": "eurostat",
        "id": "ei_bsse_m_r2?geo=EA21&indic=BS-SCI&s_adj=SA&unit=BAL",
        "region": "EA",
        "name_bg": "Доверие в услугите (DG ECFIN)",
        "name_en": "Services Confidence Indicator (DG ECFIN)",
        "lens": ["growth"],
        "peer_group": "sentiment",
        "tags": [],
        "transform": "level",
        "is_rate": False,
        "historical_start": "1996-01-01",
        "release_schedule": "monthly",
        "typical_release": "end_month",
        "revision_prone": False,
        "narrative_hint": "Услугите са ~70% от GDP — services confidence е равностоен "
                          "на industry confidence по тежест. Full Eurostat history от 1996.",
    },
    "EA_CAPACITY_UTIL": {
        "source": "eurostat",
        "id": "ei_bsin_q_r2?geo=EA21&indic=BS-ICU-PC&s_adj=SA",
        "region": "EA",
        "name_bg": "Capacity utilisation в производството (%)",
        "name_en": "Manufacturing Capacity Utilisation (%)",
        "lens": ["growth"],
        "peer_group": "sentiment",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "1985-01-01",
        "release_schedule": "quarterly",
        "typical_release": "mid_quarter",
        "revision_prone": False,
        "narrative_hint": "Реален измерител на slack — % от инсталирания капацитет. "
                          "Над 82% историческа норма; <75% сигнализира рецесия. Quarterly.",
    },
    "EA_SELLING_PRICE_EXP": {
        "source": "eurostat",
        "id": "ei_bsin_m_r2?geo=EA21&indic=BS-ISPE&s_adj=SA&unit=BAL",
        "region": "EA",
        "name_bg": "Очаквания за продажни цени (промишленост, 3m напред)",
        "name_en": "Selling-price Expectations (Industry, next 3 months)",
        "lens": ["inflation", "growth"],
        "peer_group": "sentiment",
        "tags": [],
        "transform": "level",
        "is_rate": False,
        "historical_start": "1985-01-01",
        "release_schedule": "monthly",
        "typical_release": "end_month",
        "revision_prone": False,
        "narrative_hint": "Forward-looking inflation сигнал от business side — мениджърите "
                          "казват дали ще вдигат цени. Изпреварва HICP с 3-6 месеца.",
    },
    "EA_PRODUCTION_EXP": {
        "source": "eurostat",
        "id": "ei_bsin_m_r2?geo=EA21&indic=BS-IPE&s_adj=SA&unit=BAL",
        "region": "EA",
        "name_bg": "Очаквания за производство (промишленост, 3m напред)",
        "name_en": "Production Expectations (Industry, next 3 months)",
        "lens": ["growth"],
        "peer_group": "sentiment",
        "tags": [],
        "transform": "level",
        "is_rate": False,
        "historical_start": "1985-01-01",
        "release_schedule": "monthly",
        "typical_release": "end_month",
        "revision_prone": False,
        "narrative_hint": "Forward-looking real-economy сигнал — production plans от "
                          "industry. Изпреварва industrial production index с 1-3 месеца.",
    },

    # ════════════════════════════════════════════════════════
    # CREDIT (11) — CISS + sovereign yields/spreads + M3 + bank loans
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
        "is_rate": False,
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
        "transform": "level",
        "is_rate": True,
        "historical_start": "1981-01-01",
        "release_schedule": "monthly",
        "typical_release": "end_month",
        "revision_prone": False,
        "narrative_hint": "ЕЦБ-овият референтен monetary aggregate. "
                          "Историческа вторична mandate (1999-2003), сега secondary indicator.",
    },
    "EA_BANK_LOANS_NFC": {
        "source": "ecb",
        "id": "BSI/M.U2.Y.U.A20T.A.I.U2.2240.Z01.A",
        "region": "EA",
        "name_bg": "MFI кредити към нефинансови корпорации (YoY %)",
        "name_en": "MFI Loans to Non-Financial Corporations, YoY",
        "lens": ["credit"],
        "peer_group": "bank_lending",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2004-01-01",
        "release_schedule": "monthly",
        "typical_release": "end_month",
        "revision_prone": False,
        "narrative_hint": "Банков credit към реалния сектор. ECB transmission "
                          "channel. Свиване < 0% historically signals stress.",
    },
    "EA_BANK_LOANS_HH": {
        "source": "ecb",
        "id": "BSI/M.U2.Y.U.A20T.A.I.U2.2250.Z01.A",
        "region": "EA",
        "name_bg": "MFI кредити към домакинства (YoY %)",
        "name_en": "MFI Loans to Households, YoY",
        "lens": ["credit"],
        "peer_group": "bank_lending",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2004-01-01",
        "release_schedule": "monthly",
        "typical_release": "end_month",
        "revision_prone": False,
        "narrative_hint": "Household credit. Housing-driven; силна корелация с ECB rates.",
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
        "is_rate": True,
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
        "is_rate": True,
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
        "is_rate": True,
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
        "is_rate": True,
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
        "is_rate": True,
        "historical_start": "1993-01-01",
        "release_schedule": "monthly",
        "typical_release": "monthly",
        "revision_prone": False,
        "narrative_hint": "Germany 10Y, Maastricht-criterion measure. Reference за "
                          "BTP-Bund / OAT-Bund spread изчисления.",
    },
    "EA_BTP_BUND_SPREAD": {
        "source": "derived",
        "id": "IT_10Y - DE_10Y",
        "region": "EA",
        "name_bg": "BTP-Bund spread (IT-DE 10Y, pp)",
        "name_en": "BTP-Bund Spread (IT-DE 10Y, pp)",
        "lens": ["credit"],
        "peer_group": "sovereign_spreads",
        "tags": ["sovereign_stress"],
        "transform": "level",
        "is_rate": True,
        "historical_start": "1993-01-01",
        "release_schedule": "monthly",
        "typical_release": "monthly",
        "revision_prone": False,
        "narrative_hint": "Премиер EA periphery stress proxy. Активира "
                          "fragmentation_risk cross-lens срещу ECB policy_rates.",
    },
    "EA_OAT_BUND_SPREAD": {
        "source": "derived",
        "id": "FR_10Y - DE_10Y",
        "region": "EA",
        "name_bg": "OAT-Bund spread (FR-DE 10Y, pp)",
        "name_en": "OAT-Bund Spread (FR-DE 10Y, pp)",
        "lens": ["credit"],
        "peer_group": "sovereign_spreads",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "1993-01-01",
        "release_schedule": "monthly",
        "typical_release": "monthly",
        "revision_prone": False,
        "narrative_hint": "Core-but-not-DE EA stress proxy. Captures France-specific "
                          "stress (e.g., 2024 budget crisis).",
    },

    # ─── Peripheral sovereign yields (ES, PT, GR) — ECB SDW IRS dataset ───
    # Добавени Phase EU.1.5 (2026-05-31) — peripheral fragmentation breadth.
    "ES_10Y": {
        "source": "ecb",
        "id": "IRS/M.ES.L.L40.CI.0000.EUR.N.Z",
        "region": "ES",
        "name_bg": "Испания 10Y държавна доходност",
        "name_en": "Spain 10Y Government Bond Yield (Maastricht measure)",
        "lens": ["credit"],
        "peer_group": "sovereign_yields",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "1993-01-01",
        "release_schedule": "monthly",
        "typical_release": "monthly",
        "revision_prone": False,
        "narrative_hint": "Iberian periphery — стабилен >2015, но fragmentation watch.",
    },
    "PT_10Y": {
        "source": "ecb",
        "id": "IRS/M.PT.L.L40.CI.0000.EUR.N.Z",
        "region": "PT",
        "name_bg": "Португалия 10Y държавна доходност",
        "name_en": "Portugal 10Y Government Bond Yield (Maastricht measure)",
        "lens": ["credit"],
        "peer_group": "sovereign_yields",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "1993-01-01",
        "release_schedule": "monthly",
        "typical_release": "monthly",
        "revision_prone": False,
        "narrative_hint": "Bail-out alumnus (2011-2014). Сега sub-investment volatility low.",
    },
    "GR_10Y": {
        "source": "ecb",
        "id": "IRS/M.GR.L.L40.CI.0000.EUR.N.Z",
        "region": "GR",
        "name_bg": "Гърция 10Y държавна доходност",
        "name_en": "Greece 10Y Government Bond Yield (Maastricht measure)",
        "lens": ["credit"],
        "peer_group": "sovereign_yields",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "1993-01-01",
        "release_schedule": "monthly",
        "typical_release": "monthly",
        "revision_prone": False,
        "narrative_hint": "Главен tail-risk signal — 2010-2012 crisis epicenter. Сега IG rated.",
    },
    "EA_BONO_BUND_SPREAD": {
        "source": "derived",
        "id": "ES_10Y - DE_10Y",
        "region": "EA",
        "name_bg": "Bono-Bund spread (ES-DE 10Y, pp)",
        "name_en": "Bono-Bund Spread (ES-DE 10Y, pp)",
        "lens": ["credit"],
        "peer_group": "sovereign_spreads",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "1993-01-01",
        "release_schedule": "monthly",
        "typical_release": "monthly",
        "revision_prone": False,
        "narrative_hint": "Spain periphery stress. Drifts с BTP-Bund в crisis moments.",
    },
    "EA_PT_BUND_SPREAD": {
        "source": "derived",
        "id": "PT_10Y - DE_10Y",
        "region": "EA",
        "name_bg": "PT-Bund spread (PT-DE 10Y, pp)",
        "name_en": "PT-Bund Spread (PT-DE 10Y, pp)",
        "lens": ["credit"],
        "peer_group": "sovereign_spreads",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "1993-01-01",
        "release_schedule": "monthly",
        "typical_release": "monthly",
        "revision_prone": False,
        "narrative_hint": "Portugal periphery stress proxy.",
    },
    "EA_GR_BUND_SPREAD": {
        "source": "derived",
        "id": "GR_10Y - DE_10Y",
        "region": "EA",
        "name_bg": "GGB-Bund spread (GR-DE 10Y, pp)",
        "name_en": "GGB-Bund Spread (GR-DE 10Y, pp)",
        "lens": ["credit"],
        "peer_group": "sovereign_spreads",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "1993-01-01",
        "release_schedule": "monthly",
        "typical_release": "monthly",
        "revision_prone": False,
        "narrative_hint": "Greek crisis tail risk. Активира при periphery stress wave.",
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
        "is_rate": True,
        "historical_start": "1999-01-01",
        "release_schedule": "weekly",
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
        "is_rate": True,
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
        "is_rate": True,
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
        "transform": "yoy_pct",
        "is_rate": True,
        "historical_start": "1997-09-01",
        "release_schedule": "monthly",
        "typical_release": "mid_month",
        "revision_prone": False,
        "narrative_hint": "Sum total assets — отразява APP/PEPP покупки и TLTRO. "
                          "Trend (растеж/свиване) e key QE/QT signal.",
    },

    # ─── ECB additional rates: €STR (overnight benchmark) ───
    "ECB_ESTR": {
        "source": "ecb",
        "id": "EST/B.EU000A2X2A25.WT",
        "region": "EA",
        "name_bg": "€STR — Euro Short-Term Rate (overnight benchmark)",
        "name_en": "€STR (Euro Short-Term Rate, daily)",
        "lens": ["ecb"],
        "peer_group": "policy_rates",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2019-10-02",
        "release_schedule": "daily",
        "typical_release": "next_target2_day_8am",
        "revision_prone": False,
        "narrative_hint": "Replaces EONIA от Oct 2019. Tracking close до DFR; spread "
                          "над DFR показва funding stress в репо пазара.",
    },

    # ════════════════════════════════════════════════════════
    # GROWTH (leading) — Country sentiment indicators
    # ════════════════════════════════════════════════════════
    # Тези серии са leading EA-wide индикатори чрез country signals.
    # NBB и Sentix се publish-ват преди ESI (DG ECFIN) на месеца — leads ~2-3w.
    # ZEW и IFO са German-specific но DE е 30% от EA GDP → drive-ват EA picture.
    # Status: source="pending" — adapters следват в Phase EU.2 implementation.
    # Sources:
    #   NBB BCI:  https://www.nbb.be/en/statistics/indicator-business-confidence
    #   Sentix:   https://www.sentix.de/index.php/en/economic-index.html (Bloomberg за history)
    #   ZEW:      https://www.zew.de/en/research/zew-financial-market-survey (Bundesbank API за history)
    #   IFO:      https://www.ifo.de/en/survey/ifo-business-climate-index (Bundesbank API за history)

    "NBB_BCI": {
        "source": "pending",
        "id": "NBB_BCI",
        "region": "BE",
        "name_bg": "NBB Business Climate Indicator (Белгия — EA leading proxy)",
        "name_en": "NBB Business Climate Indicator (Belgium)",
        "lens": ["growth"],
        "peer_group": "country_leading",
        "tags": [],
        "transform": "level",
        "is_rate": False,
        "historical_start": "1980-01-01",
        "release_schedule": "monthly",
        "typical_release": "around_25th",
        "revision_prone": False,
        "narrative_hint": "Белгийските SME са поддоставчици на DE/FR auto + chemicals — order book "
                          "лее 2-3m преди EA PMI/ESI. Класически leading индикатор за EA industrial cycle.",
    },
    "SENTIX_EA": {
        "source": "pending",
        "id": "SENTIX_EA",
        "region": "EA",
        "name_bg": "Sentix Economic Index (EA investor sentiment)",
        "name_en": "Sentix Economic Index (EA, current + 6m expectations)",
        "lens": ["growth"],
        "peer_group": "country_leading",
        "tags": [],
        "transform": "level",
        "is_rate": False,
        "historical_start": "2002-02-01",
        "release_schedule": "monthly",
        "typical_release": "first_monday",
        "revision_prone": False,
        "narrative_hint": "Investor sentiment via 5000+ респонденти. Published 1-ви понеделник, "
                          "leads ESI с ~3-4 седмици.",
    },
    "ZEW_EXPECTATIONS_DE": {
        "source": "pending",
        "id": "ZEW_EXPECTATIONS_DE",
        "region": "DE",
        "name_bg": "ZEW Economic Sentiment (Германия, expectations 6m)",
        "name_en": "ZEW Economic Sentiment Indicator (Germany, 6-month expectations)",
        "lens": ["growth"],
        "peer_group": "country_leading",
        "tags": [],
        "transform": "level",
        "is_rate": False,
        "historical_start": "1991-12-01",
        "release_schedule": "monthly",
        "typical_release": "second_tuesday",
        "revision_prone": False,
        "narrative_hint": "350+ financial analysts. DE-specific но drives EA picture (DE = 30% EA GDP). "
                          "Published 2-ри вторник, leads ESI.",
    },
    "IFO_CLIMATE_DE": {
        "source": "pending",
        "id": "IFO_CLIMATE_DE",
        "region": "DE",
        "name_bg": "IFO Geschäftsklima (Германия business climate)",
        "name_en": "IFO Business Climate Index (Germany)",
        "lens": ["growth"],
        "peer_group": "country_leading",
        "tags": [],
        "transform": "level",
        "is_rate": False,
        "historical_start": "1991-01-01",
        "release_schedule": "monthly",
        "typical_release": "around_25th",
        "revision_prone": False,
        "narrative_hint": "9000+ DE фирми. Главен German business cycle benchmark. "
                          "Sub-components: current_assessment + expectations.",
    },

    # ════════════════════════════════════════════════════════
    # INFLATION (expectations) — Bloomberg-bridge inflation swaps
    # ════════════════════════════════════════════════════════
    # Status: source="bloomberg_bridge" — данните идват от vrm-data-archive
    # parquet след първи ingestion. Catalog entries готови за момента когато
    # parquet файловете съществуват — pipeline-ът ще ги вкара автоматично.

    "EA_INFL_SWAP_1Y": {
        "source": "bloomberg_bridge",
        "id": "EA_INFL_SWAP_1Y",
        "parquet_path": "../../vrm-data-archive/parquet/EA_INFL_SWAP_1Y.parquet",
        "license_class": "derived_only",
        "region": "EA",
        "name_bg": "EA inflation swap 1Y (HICP-linked)",
        "name_en": "EUR Inflation Swap 1Y (HICP-linked, EUSWI1)",
        "lens": ["inflation"],
        "peer_group": "expectations",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2004-01-01",
        "release_schedule": "daily",
        "typical_release": "daily_close",
        "revision_prone": False,
        "narrative_hint": "Market-implied 1y inflation (HICP-linked). Short-horizon — energy passthrough sensitive.",
    },
    "EA_INFL_SWAP_2Y": {
        "source": "bloomberg_bridge",
        "id": "EA_INFL_SWAP_2Y",
        "parquet_path": "../../vrm-data-archive/parquet/EA_INFL_SWAP_2Y.parquet",
        "license_class": "derived_only",
        "region": "EA",
        "name_bg": "EA inflation swap 2Y (HICP-linked)",
        "name_en": "EUR Inflation Swap 2Y (HICP-linked, EUSWI2)",
        "lens": ["inflation"],
        "peer_group": "expectations",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2004-01-01",
        "release_schedule": "daily",
        "typical_release": "daily_close",
        "revision_prone": False,
        "narrative_hint": "Medium-horizon inflation expectations.",
    },
    "EA_INFL_SWAP_5Y": {
        "source": "bloomberg_bridge",
        "id": "EA_INFL_SWAP_5Y",
        "parquet_path": "../../vrm-data-archive/parquet/EA_INFL_SWAP_5Y.parquet",
        "license_class": "derived_only",
        "region": "EA",
        "name_bg": "EA inflation swap 5Y (HICP-linked)",
        "name_en": "EUR Inflation Swap 5Y (HICP-linked, EUSWI5)",
        "lens": ["inflation"],
        "peer_group": "expectations",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2004-01-01",
        "release_schedule": "daily",
        "typical_release": "daily_close",
        "revision_prone": False,
        "narrative_hint": "5y horizon — anchored regime check. Watch deviation от 2% mandate.",
    },
    "EA_INFL_SWAP_5Y5Y_FWD": {
        "source": "bloomberg_bridge",
        "id": "EA_INFL_SWAP_5Y5Y_FWD",
        "parquet_path": "../../vrm-data-archive/parquet/EA_INFL_SWAP_5Y5Y_FWD.parquet",
        "license_class": "derived_only",
        "region": "EA",
        "name_bg": "EA inflation swap 5y5y forward (ECB's preferred LT measure)",
        "name_en": "EUR Inflation Swap 5y5y Forward (EUSWI5Y5Y)",
        "lens": ["inflation"],
        "peer_group": "expectations",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2004-01-01",
        "release_schedule": "daily",
        "typical_release": "daily_close",
        "revision_prone": False,
        "narrative_hint": "ECB's preferred long-horizon измерване на de-anchoring риск. "
                          "Quoted в всеки ECB Monetary Policy Statement.",
    },

    # ════════════════════════════════════════════════════════
    # CREDIT (sovereign CDS) — Bloomberg-bridge
    # ════════════════════════════════════════════════════════
    # Sovereign CDS дава market credit risk view, complementing cash bond yields.
    # 5y senior CDS е benchmark tenor.

    "DE_CDS_5Y": {
        "source": "bloomberg_bridge",
        "id": "DE_CDS_5Y",
        "parquet_path": "../../vrm-data-archive/parquet/DE_CDS_5Y.parquet",
        "license_class": "derived_only",
        "region": "DE",
        "name_bg": "Germany 5Y sovereign CDS (senior)",
        "name_en": "Germany 5Y Sovereign CDS (Senior)",
        "lens": ["credit"],
        "peer_group": "sovereign_cds",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2008-01-01",
        "release_schedule": "daily",
        "typical_release": "daily_close",
        "revision_prone": False,
        "narrative_hint": "Risk-free benchmark в EA CDS пространство. Минимална стойност.",
    },
    "IT_CDS_5Y": {
        "source": "bloomberg_bridge",
        "id": "IT_CDS_5Y",
        "parquet_path": "../../vrm-data-archive/parquet/IT_CDS_5Y.parquet",
        "license_class": "derived_only",
        "region": "IT",
        "name_bg": "Italy 5Y sovereign CDS (senior)",
        "name_en": "Italy 5Y Sovereign CDS (Senior)",
        "lens": ["credit"],
        "peer_group": "sovereign_cds",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2008-01-01",
        "release_schedule": "daily",
        "typical_release": "daily_close",
        "revision_prone": False,
        "narrative_hint": "Largest EA periphery debt market. Spike-ва в 2011-2012 + 2018 + 2022.",
    },
    "ES_CDS_5Y": {
        "source": "bloomberg_bridge",
        "id": "ES_CDS_5Y",
        "parquet_path": "../../vrm-data-archive/parquet/ES_CDS_5Y.parquet",
        "license_class": "derived_only",
        "region": "ES",
        "name_bg": "Spain 5Y sovereign CDS (senior)",
        "name_en": "Spain 5Y Sovereign CDS (Senior)",
        "lens": ["credit"],
        "peer_group": "sovereign_cds",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2008-01-01",
        "release_schedule": "daily",
        "typical_release": "daily_close",
        "revision_prone": False,
        "narrative_hint": "Iberian periphery — moves with IT_CDS_5Y в crisis moments.",
    },
    "FR_CDS_5Y": {
        "source": "bloomberg_bridge",
        "id": "FR_CDS_5Y",
        "parquet_path": "../../vrm-data-archive/parquet/FR_CDS_5Y.parquet",
        "license_class": "derived_only",
        "region": "FR",
        "name_bg": "France 5Y sovereign CDS (senior)",
        "name_en": "France 5Y Sovereign CDS (Senior)",
        "lens": ["credit"],
        "peer_group": "sovereign_cds",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2008-01-01",
        "release_schedule": "daily",
        "typical_release": "daily_close",
        "revision_prone": False,
        "narrative_hint": "Core-but-not-DE. Captures France-specific stress (2024 budget crisis).",
    },

    # ════════════════════════════════════════════════════════
    # ECB OIS curve (forwards) — Bloomberg-bridge
    # ════════════════════════════════════════════════════════
    # OIS forwards дават implied DFR path — какво пазара очаква ECB да направи.
    # Spot rates (€STR) идват от ECB SDW; forwards са Bloomberg-only practically.

    "EA_OIS_3M": {
        "source": "bloomberg_bridge",
        "id": "EA_OIS_3M",
        "parquet_path": "../../vrm-data-archive/parquet/EA_OIS_3M.parquet",
        "license_class": "source_public",
        "region": "EA",
        "name_bg": "EA 3M OIS forward (implied €STR 3m)",
        "name_en": "EUR 3M OIS Forward (€STR-linked, EUSWE3 BGN)",
        "lens": ["ecb"],
        "peer_group": "ois_curve",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2019-10-02",
        "release_schedule": "daily",
        "typical_release": "daily_close",
        "revision_prone": False,
        "narrative_hint": "Short-horizon implied ECB DFR. Reaction function в action.",
    },
    "EA_OIS_1Y": {
        "source": "bloomberg_bridge",
        "id": "EA_OIS_1Y",
        "parquet_path": "../../vrm-data-archive/parquet/EA_OIS_1Y.parquet",
        "license_class": "source_public",
        "region": "EA",
        "name_bg": "EA 1Y OIS forward (implied 1y average DFR)",
        "name_en": "EUR 1Y OIS Forward (EUSWE1 BGN)",
        "lens": ["ecb"],
        "peer_group": "ois_curve",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2019-10-02",
        "release_schedule": "daily",
        "typical_release": "daily_close",
        "revision_prone": False,
        "narrative_hint": "1y implied policy path.",
    },
    "EA_OIS_2Y": {
        "source": "bloomberg_bridge",
        "id": "EA_OIS_2Y",
        "parquet_path": "../../vrm-data-archive/parquet/EA_OIS_2Y.parquet",
        "license_class": "source_public",
        "region": "EA",
        "name_bg": "EA 2Y OIS forward",
        "name_en": "EUR 2Y OIS Forward (EUSWE2 BGN)",
        "lens": ["ecb"],
        "peer_group": "ois_curve",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2019-10-02",
        "release_schedule": "daily",
        "typical_release": "daily_close",
        "revision_prone": False,
        "narrative_hint": "Medium-horizon policy expectations.",
    },
    "EA_OIS_5Y": {
        "source": "bloomberg_bridge",
        "id": "EA_OIS_5Y",
        "parquet_path": "../../vrm-data-archive/parquet/EA_OIS_5Y.parquet",
        "license_class": "source_public",
        "region": "EA",
        "name_bg": "EA 5Y OIS forward",
        "name_en": "EUR 5Y OIS Forward (EUSWE5 BGN)",
        "lens": ["ecb"],
        "peer_group": "ois_curve",
        "tags": [],
        "transform": "level",
        "is_rate": True,
        "historical_start": "2019-10-02",
        "release_schedule": "daily",
        "typical_release": "daily_close",
        "revision_prone": False,
        "narrative_hint": "Long-horizon equilibrium rate proxy.",
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
    """Всички серии от конкретен източник ('ecb', 'eurostat', 'derived', 'oecd', 'pending')."""
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
        "lens", "peer_group", "tags", "transform", "is_rate",
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
        if not isinstance(meta["is_rate"], bool):
            errors.append(f"{key}: is_rate трябва да е bool")

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
