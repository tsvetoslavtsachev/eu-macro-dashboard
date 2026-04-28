# eu-macro-dashboard

**Седмичен макроикономически briefing за Еврозоната.**

Сестрински проект на [us-macro-dashboard](https://github.com/tsvetoslavtsachev/us-macro-dashboard) — същата архитектура, различни данни (ECB SDW + Eurostat вместо FRED), различен регулаторен контекст и briefing на български.

---

## Статус

✅ **v0.1.0 MVP — функционален.** Всичките 6 фази завършени.

| Phase | Статус | Описание |
|---|---|---|
| 0. Setup | ✅ | Skeleton, portable analytics layer, BG journal template |
| 1. Data Layer | ✅ | ECB + Eurostat adapter-и с cache; 16 EA серии в catalog |
| 2. Lens Modules | ✅ | labor, inflation, growth, ecb (4 модула) |
| 3. Briefing | ✅ | HTML template на български със executive + per-module + anomalies |
| 4. Analog Engine | ✅ | EA 7-dim macro vector + cosine analog matcher + forward outcomes |
| 5. Research Desk | ✅ | Journal layer (CRUD + filter) + sandbox scaffolding |
| 6. Package | ✅ | FRAMEWORK.md, AGENT.md, PHASES.md, run.bat, tag v0.1.0 |

134 теста минават · 16 серии fetch-ват чисто end-to-end.

---

## Какво прави

Чете 16 макроикономически серии от ECB Statistical Data Warehouse и Eurostat REST API, групирани в 5 analytical lens-а (Labor, Inflation, Growth, Credit, ECB), и генерира седмичен HTML briefing с:

- **Executive summary** — composite macro score (0–100) и режим (БГ: ЗДРАВ / СМЕСЕН / ВЛОШАВАЩ СЕ / РЕЦЕСИОНЕН)
- **Per-module блокове** — индикатори, percentile rank, YoY промени за всеки lens
- **Исторически аналози** (опционално с `--with-analogs`) — top-3 най-близки EA епизода (1999+ EMU era) + forward outcomes след 3/6/12m
- **Аномалии** — серии в опашката на историческото разпределение (|z|>2)
- **Свързани журнал бележки** (опционално с `--with-journal`) — релевантни записи от research journal

HTML файлът е self-contained (без CDN, без JS), изпраща се по имейл или се отваря локално.

---

## Quick start

```bash
git clone https://github.com/tsvetoslavtsachev/eu-macro-dashboard.git
cd eu-macro-dashboard
pip install -r requirements.txt

# Първо стартиране — fetch всички 16 серии
python run.py --status --refresh

# Седмичен briefing (бърз, само от cache)
python run.py --briefing

# Пълен briefing с analog engine + journal
python run.py --briefing --with-analogs --with-journal

# По-подробни режими
python run.py --modules        # console summary на 4-те lens модула
python run.py --status         # cache status report
```

**API ключове:** ECB SDW и Eurostat REST не изискват автентикация. `.env` файлът е опционален, само за override на endpoint-и.

**Windows:** Има `run.bat` launcher с double-click меню — Status / Briefing / Refresh / Tests.

---

## Архитектура

```
eu_macro_dashboard/
├── run.py                # CLI entry point (--status / --modules / --briefing)
├── run.bat               # Windows launcher menu
├── config.py             # ECB/Eurostat endpoints, EA weights, BG labels
├── catalog/
│   ├── series.py         # 16 EA серии с metadata (ECB + Eurostat IDs)
│   └── cross_lens_pairs.py
├── sources/
│   ├── _base.py          # BaseAdapter (cache, retry, freshness)
│   ├── ecb_adapter.py    # ECB SDMX REST (jsondata format)
│   └── eurostat_adapter.py # Eurostat REST (JSON-stat 2.0)
├── core/
│   ├── primitives.py     # breadth, momentum, z_score, percentile, etc.
│   └── scorer.py         # score_series, composite_score, regimes
├── modules/              # labor, inflation, growth, ecb (4 lens модула)
├── analysis/             # breadth, divergence, non_consensus, anomaly,
│                         # executive, delta, macro_vector (7-dim EA),
│                         # analog_matcher (EA episodes), forward_path
├── export/
│   ├── weekly_briefing.py # HTML renderer (BG, self-contained)
│   └── data_status.py    # console status report
├── scripts/
│   ├── _utils.py         # journal CRUD + sandbox scaffolding
│   ├── build_journal_index.py
│   └── sandbox/          # ad hoc анализи (gitignored)
├── journal/              # research notes (gitignored, само framework публичен)
│   ├── _template.md
│   ├── HOWTO.md
│   └── {labor,inflation,credit,growth,analogs,regime,methodology}/
├── tests/                # 134 pytest теста
├── FRAMEWORK.md          # методология
├── AGENT.md              # orientation за AI assistents в бъдещи сесии
├── PHASES.md             # build log на 6-те phase-а
├── LICENSE               # MIT
└── requirements.txt
```

---

## Differences vs US version

| Aspect | US (us-macro-dashboard) | EU (този проект) |
|---|---|---|
| Source | FRED (Federal Reserve) | ECB SDW + Eurostat |
| API key | required (FRED key) | none (публични endpoints) |
| History start | 1970 | 1999 (EMU era) |
| Macro vector | 8-dim (T10YIE breakeven) | 8-dim (ECB SPF long-term expectations) |
| Lens count | 4 (Labor, Inflation, Growth, Liquidity) | 5 (+ ECB monetary stance) |
| Inflation weight | 0.20 | 0.30 (ECB single mandate) |
| Credit proxy | HY OAS, IG OAS | CISS + sovereign spreads (BTP-Bund) |
| PMI | ISM | ESI (DG ECFIN — безплатно) |
| Recession trigger | Sahm rule (UNRATE) | Sahm rule (EA-21 UNRATE) |
| Briefing language | English | български |

---

## Methodology

Виж [FRAMEWORK.md](FRAMEWORK.md) за пълна методология.

Кратко:
1. **Lens scoring:** percentile rank спрямо EA history (1999+); invert flag за серии където high=bad (UNRATE)
2. **Composite score:** weighted average по `MODULE_WEIGHTS` (inflation 30%, credit 20%, growth 20%, labor 15%, ECB 15%)
3. **Regime mapping:** 5 levels от composite score (РЕЦЕСИОНЕН → ВЛОШАВАЩ СЕ → СМЕСЕН → ЗДРАВ → ЕКСПАНЗИОНЕН)
4. **Analog engine:** 7-D z-scored vector → cosine similarity срещу 1999+ history → top-3 най-подобни месеци + forward outcomes медиана

---

## Развитие след v0.1.0

Планирани разширения:
- ✅ ~~Inflation expectations dim → 8-dim vector~~ (v0.2.0: ECB SPF long-term)
- WoW delta секция (след първата session с persisted state)
- Cross-lens divergence pairs за `analysis/divergence.py`
- Country drill-down (DE/FR/IT/ES) — текущо само EA-aggregate
- ESI sentiment лens разширение
- TLTRO outstanding в ECB module

---

## License

MIT — виж [LICENSE](LICENSE).

---

## Maintainer

Tsvetoslav Tsachev — [@tsvetoslavtsachev](https://github.com/tsvetoslavtsachev)
