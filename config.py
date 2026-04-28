"""
eu_macro_dashboard — Configuration
==================================
Единственото място, където пипаш настройки за EU версията.

Различия от US (econ_v2 / Macro_Intelligence):
- Няма API ключове — ECB SDW и Eurostat REST не изискват автентикация
- HISTORY_START е 1999 (EMU стартира — преди това няма унифицирани EA данни)
- ANALOG_HISTORY_START е 1999 (по същата причина)
- MODULE_WEIGHTS прекалибрирани за EA реалност (inflation тежи повече,
  labor по-малко; credit/ECB lens-овете са нови)
- BG labels по подразбиране (briefing-ът е на български)
"""
import os


# ─── ECB / Eurostat не изискват API key ─────────────────────────────────────
# Adapter-ите използват публичните REST endpoint-и:
#   https://data-api.ecb.europa.eu/service/data/{flowref}/{key}
#   https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}
ECB_API_BASE = "https://data-api.ecb.europa.eu/service"
EUROSTAT_API_BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0"

# Optional .env override (за testing срещу staging endpoints, ако се появят)
_DOTENV = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_DOTENV):
    with open(_DOTENV, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            if key.strip() == "ECB_API_BASE":
                ECB_API_BASE = value
            elif key.strip() == "EUROSTAT_API_BASE":
                EUROSTAT_API_BASE = value


# ─── Кеш (адаптивен TTL по release schedule в adapter-а) ─────────────────────
CACHE_TTL_HOURS_DEFAULT = 12
CACHE_TTL_DAYS_BY_SCHEDULE = {
    "weekly":     3,
    "monthly":   10,
    "quarterly": 30,
    "annually":  90,
}


# ─── Исторически прозорци ────────────────────────────────────────────────────
# EMU/euro era старт: януари 1999
HISTORY_START = "1999-01-01"            # percentile/z-score база
ANALOG_HISTORY_START = "1999-01-01"     # historical analog window
# Pre-1999 данни (synthetic GDP-weighted DM legacy currencies) — skip за v1


# ─── Модулни тегла за Composite Macro Score (EA-калибрирани) ─────────────────
# Reasoning:
#   - inflation 0.30 — ЕЦБ има single mandate, инфлацията е dominant signal
#   - labor 0.15    — EA labor markets лагират, по-малко leading
#   - growth 0.20   — стандартна тежест
#   - credit 0.20   — банково-доминирана икономика; CISS + sovereign spreads
#   - ecb 0.15      — нов lens (rates, balance sheet, transmission)
MODULE_WEIGHTS = {
    "inflation": 0.30,
    "labor":     0.15,
    "growth":    0.20,
    "credit":    0.20,
    "ecb":       0.15,
}


# ─── Macro режими (composite score → label, BG) ──────────────────────────────
MACRO_REGIMES = [
    (80, "ЕКСПАНЗИОНЕН",   "#00c853"),
    (65, "ЗДРАВ",          "#69f0ae"),
    (50, "СМЕСЕН",         "#ffd600"),
    (35, "ВЛОШАВАЩ СЕ",    "#ff6d00"),
    (0,  "РЕЦЕСИОНЕН",     "#d50000"),
]


# ─── Изходна папка ───────────────────────────────────────────────────────────
OUTPUT_DIR = "output"
