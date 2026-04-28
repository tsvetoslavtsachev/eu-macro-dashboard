# AGENT.md — Orientation за AI assistents

Този файл дава контекст на Claude (или друг AI) при стартиране на нова сесия. Прочети го като влизаш в проекта.

---

## TL;DR

- **Проект:** Eurozone макроикономически седмичен briefing.
- **Сестрински проект:** [us-macro-dashboard](https://github.com/tsvetoslavtsachev/us-macro-dashboard) — същата архитектура, US данни.
- **Status:** v0.1.0 MVP released. 134 теста минават. End-to-end функционален.
- **Език за разговор:** български. **Code/commits/comments:** английски (понякога BG inline в docstrings). **Briefing output:** български.
- **Потребител:** economist & financial analyst, не програмист. Винаги показвай план преди да пипаш код.

---

## Какво е build-нато

| Phase | Compileted | Files |
|---|---|---|
| 0. Setup | ✅ | Skeleton, portable analytics 1:1 от US |
| 1. Data Layer | ✅ | `sources/_base.py` + `ecb_adapter.py` + `eurostat_adapter.py` + 16 серии в catalog |
| 2. Lens Modules | ✅ | `modules/labor.py`, `inflation.py`, `growth.py`, `ecb.py` |
| 3. Briefing | ✅ | `export/weekly_briefing.py` — HTML на български |
| 4. Analog Engine | ✅ | EA 7-dim macro vector + analog matcher + forward outcomes |
| 5. Research Desk | ✅ | `scripts/_utils.py` — journal CRUD, sandbox scaffolding |
| 6. Package | ✅ | FRAMEWORK.md, AGENT.md, PHASES.md, run.bat, tag v0.1.0 |

---

## Архитектура — къде да гледаш

```
eu_macro_dashboard/
├── run.py                ← CLI entry. --status / --modules / --briefing
├── config.py             ← Endpoints, weights, BG regime labels
├── catalog/series.py     ← 16 серии metadata (single source of truth)
├── catalog/cross_lens_pairs.py ← празен в v1; popular в Phase 1.5+
├── sources/
│   ├── _base.py          ← BaseAdapter (cache, retry, freshness)
│   ├── ecb_adapter.py    ← ECB SDMX-JSON parser
│   └── eurostat_adapter.py ← Eurostat JSON-stat 2.0 parser
├── core/
│   ├── primitives.py     ← math (z_score, breadth, momentum)
│   └── scorer.py         ← score_series, composite_score, get_regime
├── modules/              ← 4 lens модула (labor, inflation, growth, ecb)
├── analysis/             ← agnostic analytics (breadth, divergence, anomaly,
│                           executive, macro_vector, analog_matcher, forward_path)
├── export/
│   ├── weekly_briefing.py ← HTML rendering
│   └── data_status.py    ← console status report
├── scripts/_utils.py     ← journal CRUD + sandbox templates
├── scripts/build_journal_index.py
├── tests/                ← 134 pytest теста
└── data/                 ← cache files (.json, gitignored)
```

---

## Как се пуска (typical commands)

```bash
# Install
pip install -r requirements.txt

# Първо стартиране — fetch данни
python run.py --status --refresh

# Бърз briefing (cache-only)
python run.py --briefing

# Пълен briefing
python run.py --briefing --with-analogs --with-journal

# Console summary на модулите
python run.py --modules

# Tests
pytest tests/ -q

# Journal
python scripts/build_journal_index.py    # rebuilds journal/README.md
```

Windows: `run.bat` → double-click меню.

---

## Conventions

### Naming
- **Catalog keys:** `EA_*` (EA-aggregate), `IT_*`, `DE_*`, `FR_*` (country)
- **Test files:** `tests/test_<module>.py`, един test = един assertion идея
- **Journal entries:** `journal/<topic>/YYYY-MM-DD_slug.md` (auto-generated с `save_journal_entry`)
- **Sandbox scripts:** `scripts/sandbox/YYYY-MM-DD_slug.py` (gitignored)

### Series catalog metadata (catalog/series.py)
Всяка серия трябва да има всичките 14 полета:
```python
"EA_KEY": {
    "source": "ecb" | "eurostat" | "oecd" | "pending",
    "id": "<flowref>/<key>"  # за ECB; "<dataset>?<filter>" за Eurostat
    "region": "EA" | "EU" | "DE" | "FR" | "IT" | "ES" | "GLOBAL",
    "name_bg": "...",
    "name_en": "...",
    "lens": ["labor"],  # list, може multi-lens
    "peer_group": "...",
    "tags": [],
    "transform": "level" | "yoy_pct" | "mom_pct" | "qoq_pct" | "z_score" | "first_diff",
    "historical_start": "YYYY-MM-DD",
    "release_schedule": "weekly" | "monthly" | "quarterly" | "annually",
    "typical_release": "first_week" | "mid_month" | etc.,
    "revision_prone": True | False,
    "narrative_hint": "BG description...",
}
```

### ECB source IDs
Format: `flowref/key` напр. `CISS/D.U2.Z0Z.4F.EC.SS_CIN.IDX`. Adapter splits на първото `/`.

### Eurostat source IDs
Format: `dataset?filter_string` напр. `une_rt_m?geo=EA21&unit=PC_ACT&sex=T&age=TOTAL&s_adj=SA`.

**ВАЖНО:** Eurostat geo код варира по dataset:
- `une_rt_m`, `sts_inpr_m` → използват `EA21` (текущ Euro Area composition от 2026)
- `prc_hicp_manr` → използва `EA` (auto-shifting aggregate; EA20 / EA21 не работи)
- `EU27_2020` за full EU-27

Винаги test fetch-вай преди да добавиш нова серия.

### Module pattern (snapshot interface)
```python
def run(snapshot: dict[str, pd.Series]) -> dict:
    """Returns unified shape: {module, label, icon, scores, composite,
    regime, regime_color, indicators, sparklines, key_readings}"""
```

Модулите НЕ знаят за adapter-и — само за snapshot. Run.py orchestrates fetch.

---

## Какво да НЕ правиш

- ❌ Не добавяй FRED references — този проект НЕ е US.
- ❌ Не commit-вай `journal/<topic>/*.md` (private notes); само `_template.md` и `HOWTO.md` са public.
- ❌ Не commit-вай `data/*.json` (cache; gitignored).
- ❌ Не презапиши `core/primitives.py` или other 1:1 от US модули без сериозна причина — те са вече тествани и работят.
- ❌ Не променяй MacroState dataclass shape без update на analog_matcher/comparison/pipeline.

---

## Какво ТРЯБВА да направиш

- ✅ Винаги показвай план преди да пипаш код.
- ✅ Тествай нови adapter codes срещу live API преди commit (за да се избегнат "hardcoded but not working" entries).
- ✅ Run `pytest tests/ -q` преди commit.
- ✅ Commit messages на английски; BG в docstrings/UI/journal.
- ✅ Когато добавяш серия в catalog: проверявай че fetch работи, validation минава, добавена в правилния lens.
- ✅ Mark Phase 4+ TODOs ясно когато съдържанието е US-specific.

---

## Известни ограничения / Phase 4.5+ candidates

- **Inflation expectations dim** — текущо 7-dim macro vector; 8-дим version изисква HICP swap или ECB SPF (research нужен за правилни ECB codes).
- **Cross-lens divergence pairs празни** — `catalog/cross_lens_pairs.py` е stub; populating-нете с EA-specific pairs (стагфлация тест, ECB transmission, sovereign spread vs CISS) изисква 25+ серии за meaningful breadth.
- **WoW delta** — implementation готов в `analysis/delta.py`, но не активиран в run.py (изисква state persist между runs).
- **`analysis/executive.py` Fed→ECB narrative rewrite** — все още има US-style "Fed credibility" текстове.
- **`analysis/guardrails.py`** — US Sahm/ICSA/T10Y2Y signals; EA equivalents (CISS / ESI / Bund-spread) не са пренаписани.

---

## Quick troubleshooting

| Проблем | Причина | Fix |
|---|---|---|
| `python run.py --status` says catalog empty | Catalog не е populated | Проверка `catalog/series.py` |
| `--refresh` фейлва | Network / firewall | Re-test индивидуално с `EcbAdapter().fetch(...)` |
| Eurostat 413 Payload Too Large | Filters недостатъчни | Добави `unit=`, `coicop=` и т.н. |
| Eurostat `value: {}` | geo код невалиден за този dataset | Опитай `EA` вместо `EA21` или обратното |
| ECB 404 | Wrong flowref/key format | Виж https://data.ecb.europa.eu за валидни |
| UnicodeEncodeError на Windows | cp1252 stdout | Add `sys.stdout.reconfigure(encoding="utf-8")` |
| pytest fails след catalog change | Catalog validation broken | Run `python -c "from catalog.series import validate_catalog; print(validate_catalog())"` |

---

## Credits

Built by Tsvetoslav Tsachev със съдействие на Claude (Anthropic) през 6 итеративни phase-а. Архитектурата е mirror на us-macro-dashboard, със системна EA адаптация на data sources, regimes, weights и език.

**Last updated:** 2026-04-28 (v0.1.0 MVP)
