# eu-macro-dashboard

**Седмичен макроикономически briefing за Еврозоната.**

Сестрински проект на [us-macro-dashboard](https://github.com/tsvetoslavtsachev/us-macro-dashboard) — същата архитектура, различни данни (ECB SDW + Eurostat вместо FRED), различен регулаторен контекст и briefing на български.

---

## Статус

🚧 **В активна разработка.** Phase 0 (skeleton) завършена. Phase 1 (data layer) предстои.

| Phase | Статус | Описание |
|---|---|---|
| 0. Setup | ✅ | Skeleton, portable analytics layer copy, stubs |
| 1. Data Layer | ⏳ | ECB + Eurostat adapter-и с cache; catalog с ~25–30 EA серии |
| 2. Lens Modules | ⏳ | labor, inflation, growth, ecb |
| 3. Briefing | ⏳ | HTML template на български |
| 4. Analog Engine | ⏳ | Adapted 8-D macro vector за EA + analog matcher |
| 5. Research Desk | ⏳ | Journal layer + sandbox |
| 6. Package | ⏳ | Final docs, run.bat, push |

---

## Какво прави

Чете 25–30 макроикономически серии от ECB Statistical Data Warehouse и Eurostat REST API, групирани в 5 analytical lens-а (Labor, Inflation, Growth, Credit, ECB), и генерира седмичен HTML briefing с:

- **Executive summary** — composite macro score (0–100) и режим (БГ: ЗДРАВ / СМЕСЕН / ВЛОШАВАЩ СЕ / РЕЦЕСИОНЕН)
- **Седмична делта** (week-over-week материални движения)
- **Cross-lens divergence** — двойки lens-и в разминаване (стагфлация тест, ECB transmission, и др.)
- **Non-consensus readings** — серии в опашката на историческото разпределение
- **Anomaly detection** — статистически outliers (|z|>2)
- **Historical analogs** — top-3 най-близки исторически EA епизода + forward outcomes (опционално)

HTML файлът е self-contained (без CDN, без JS), изпраща се по имейл или се отваря локално.

---

## Защо отделно репо от US

Eurozone има **различни данни, различни регулатори, различен tempo** от US. Смесването в един dashboard ще даде leaky abstractions. По-чисто е — същата архитектура, нови adapter-и и каталог.

---

## Quick start

```bash
git clone https://github.com/tsvetoslavtsachev/eu-macro-dashboard.git
cd eu-macro-dashboard
pip install -r requirements.txt

# Phase 1+ когато е готово:
python run.py --status      # data status screen
python run.py --briefing    # седмичен briefing
```

⚠ Phase 0 не може още да генерира briefing — adapter-ите и catalog-ът са в работа.

**API ключове:** ECB SDW и Eurostat REST не изискват автентикация. `.env` файлът е опционален, само за override на endpoint-и.

---

## Архитектура

```
eu_macro_dashboard/
├── run.py                # CLI entry point
├── config.py             # ECB/Eurostat endpoints, EA weights, BG labels
├── catalog/              # series.py, cross_lens_pairs.py
├── sources/              # ecb_adapter.py, eurostat_adapter.py
├── core/primitives.py    # math primitives (1:1 от US)
├── modules/              # labor, inflation, growth, ecb
├── analysis/             # breadth, divergence, non_consensus, anomaly,
│                         # executive, delta, guardrails, macro_vector,
│                         # analog_matcher, forward_path
├── export/               # weekly_briefing, data_status
├── scripts/              # journal layer + sandbox
├── journal/              # private research notes (в .gitignore)
└── tests/                # pytest
```

---

## Differences vs US version

| Aspect | US | EU |
|---|---|---|
| Source | FRED | ECB SDW + Eurostat |
| API key | required | none |
| History start | 1970 | 1999 (EMU era) |
| Lens count | 4 (Labor, Inflation, Growth, Liquidity) | 5 (+ ECB) |
| Inflation weight | 0.20 | 0.30 (ECB single mandate) |
| Credit proxy | HY OAS, IG OAS | CISS + sovereign spreads (BTP-Bund) |
| PMI | ISM | ESI (DG ECFIN, безплатно) |
| Briefing language | English | български |

---

## License

MIT — виж [LICENSE](LICENSE).

---

## Maintainer

Tsvetoslav Tsachev — [@tsvetoslavtsachev](https://github.com/tsvetoslavtsachev)
