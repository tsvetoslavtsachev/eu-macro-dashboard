# FRAMEWORK — Eurozone Macro Dashboard

Методология на eu-macro-dashboard. Този документ обяснява **какво** прави всеки lens, **защо** е калибриран както е, и **как** компонентите се комбинират в композитен macro score.

---

## 1. Концептуален модел

5 analytical lens-а покриват EA макроиконoмиката:

| Lens | Какво измерва | Серии |
|---|---|---|
| 👷 **Labor** | Цикличeн натиск на пазара на труда | EA UNRATE (1) |
| 🔥 **Inflation** | HICP натиск спрямо ECB target | HICP headline / core / services (3) |
| 📈 **Growth** | Реална активност и hard data | EA Industrial Production YoY (1) |
| 🏦 **ECB** | Монетарен stance (нов lens, без US аналог) | DFR, MRO, MLF, balance sheet (4) |
| 💳 **Credit** | Системен стрес и transmission | CISS, M3, sovereign yields, BTP-Bund (7) |

**Защо отделен ECB lens?** ЕЦБ има single mandate (ценова стабилност); transmission-ът минава през фрагментиран банков сектор; sovereign spreads (BTP-Bund) са EA-unique stress channel. В US модела Fed е разпиляван през няколко lens-а — за EA това би замазало ключови особености.

---

## 2. Series scoring

Всяка серия получава `score 0–100` чрез следната процедура:

```
percentile = % от историческите стойности (от 1999) под текущата
score = percentile         (ако invert=False)
       или 100 − percentile (ако invert=True)
```

`invert=True` обръща семантиката: за UNRATE висока стойност е лошо → invert така че висок score = здрав labor market.

**За какво се ползва историята от 1999?** EMU стартира 1999. Преди това еквивалентът е synthetic GDP-weighted DM legacy currencies — твърде шумен за meaningful percentile.

**Transforms:**
- `level` — без преобразуване
- `yoy_pct` — 12-period pct_change (за level series като IP индекс)
- `mom_pct` / `qoq_pct` — за по-високочестотен анализ
- `z_score` — pre-computed standardization

---

## 3. Lens composite

За всеки lens се изчислява `composite` като weighted average на series scores:

| Lens | Серии (примерни) | Weights |
|---|---|---|
| Labor | EA_UNRATE | 1.0 (single source v1) |
| Inflation | HICP_HEADLINE, HICP_CORE, HICP_SERVICES | 0.30 / 0.40 / 0.30 |
| Growth | EA_IP YoY | 1.0 |
| ECB | DFR, balance sheet trend, MRO | 0.55 / 0.30 / 0.15 |

**Защо такива тегла за inflation?** Core и services са по-stable indicators of underlying pressure; headline е volatile (energy, food). ECB-овият анализ преферира core като trend signal.

**Защо DFR доминира ECB stance?** След 2014 DFR е binding rate (negative rates era); MRO е largely symbolic; balance sheet trend (yoy_pct) показва QE/QT direction.

---

## 4. Regime mapping (per lens)

Composite score → regime label чрез 5-level threshold mapping:

### Labor (висок score = здрав)
```
≥ 80: ГОРЕЩ          (#00c853)
65-80: ЗДРАВ          (#69f0ae)
45-65: ОХЛАЖДАЩ       (#ffd600)
30-45: СЛАБ           (#ff6d00)
< 30: СТРЕСИРАН       (#d50000)
```

### Inflation (висок score = висока инфлация = проблем)
```
≥ 80: ОСТРА ИНФЛАЦИЯ      (#d50000)
65-80: ЕЛЕВИРАНА          (#ff6d00)
45-65: БЛИЗО ДО ЦЕЛТА     (#69f0ae)
30-45: ПОД ЦЕЛТА          (#ffd600)
< 30: ДЕФЛАЦИОНЕН РИСК    (#0091ea)
```

### Growth (висок score = здрав растеж)
```
≥ 80: ЕКСПАНЗИЯ      (#00c853)
65-80: РАСТЕЖ        (#69f0ae)
45-65: СТАГНАЦИЯ      (#ffd600)
30-45: СВИВАНЕ        (#ff6d00)
< 30: РЕЦЕСИЯ         (#d50000)
```

### ECB (висок score = restrictive stance)
```
≥ 80: ПРОБЛЕМАТИЧНО ТЯСНА    (#d50000)
65-80: РЕСТРИКТИВНА          (#ff6d00)
45-65: НЕУТРАЛНА             (#ffd600)
30-45: СТИМУЛАТИВНА          (#69f0ae)
< 30: СИЛНО СТИМУЛАТИВНА     (#0091ea)
```

---

## 5. Композитен macro score (overall)

```
macro_score = Σ (lens_composite × MODULE_WEIGHTS[lens]) / Σ MODULE_WEIGHTS[lens]
```

**MODULE_WEIGHTS (config.py) — EA калибровка:**
```
inflation: 0.30   ← ECB single mandate; инфлацията е dominant signal
credit:    0.20   ← банково-доминирана икономика; CISS + spreads
growth:    0.20   ← стандартна тежест
labor:     0.15   ← EA labor markets лагират → по-малко leading
ecb:       0.15   ← нов lens (rates, balance, transmission)
```

**Различия от US weights:**
- US: labor 20%, inflation 20%, growth 20%, credit 15%, fed 10%, housing 10%, consumer 5%
- EA: inflation тежи повече (single mandate), labor по-малко (структурно лагира), credit повече (банкова доминация), ECB e нов

---

## 6. Macro regime (overall)

`MACRO_REGIMES` (config.py) → 5 нива:
```
≥ 80: ЕКСПАНЗИОНЕН   (#00c853)
65-80: ЗДРАВ         (#69f0ae)
50-65: СМЕСЕН        (#ffd600)
35-50: ВЛОШАВАЩ СЕ   (#ff6d00)
< 35: РЕЦЕСИОНЕН     (#d50000)
```

---

## 7. Historical Analog Engine (Phase 4 / 4.5)

8-dimensional macro state vector:

| Dim | Source | Бележка |
|---|---|---|
| 1. unrate | Eurostat une_rt_m | EA-21 |
| 2. core_hicp_yoy | Eurostat prc_hicp_manr | TOT_X_NRG_FOOD |
| 3. real_dfr | DERIVED: DFR − HICP_CORE | Реален policy rate |
| 4. yc_10y2y | DERIVED: BUND_10Y − BUND_2Y | Curve slope |
| 5. sovereign_stress | DERIVED: IT_10Y − DE_10Y | BTP-Bund proxy за HY OAS |
| 6. ip_yoy | EA_IP YoY computed | Hard activity |
| 7. sahm | Sahm rule на UNRATE | 3mma − 12m trailing min |
| 8. inflation_expectations | ECB SPF/Q.U2.HICP.POINT.LT.Q.001 | Long-term anchored (quarterly forward-fill) |

**Phase 4.5 added dim 8** — ECB Survey of Professional Forecasters long-term HICP point forecast. Quarterly survey, end-of-quarter release; forward-filled до monthly за alignment. История от 1999 (EMU era), първа observation 1.80%, текуща 2.00% (точно anchored at ECB target). Dim 8 интерпретация: близо до 2% = anchored; > 0.5pp deviation = de-anchoring risk.

**Algorithm:**
1. `build_history_matrix(snapshot)` → DataFrame (327+ месеца × 7 dims)
2. `z_score_matrix(df)` → standardize each dim спрямо собствена history
3. `build_current_vector` → MacroState за последната complete-case дата
4. `find_analogs(history_z, current_z, k=3)`:
   - Cosine similarity срещу всеки исторически месец
   - `exclude_last_months=24` (отрязваме скорошното за фалшиво съпадение)
   - `min_gap_months=12` (избягваме 3 близки месеца като top-3)
5. `forward_outcomes` за всеки analog: какво се е случило 3/6/12 месеца след него

**Episode labels** (analog_matcher.py): EA-specific исторически епизоди от 1999 — Dotcom bust, ECB rate hike cycle 2005-08, GFC, EU sovereign debt crisis, Draghi "whatever it takes", QE/negative rates, Brexit, COVID + PEPP, Energy shock + ECB hiking, Disinflation.

---

## 8. Caveats

1. **EA история е по-кратка от US** — 26 години vs 50+. По-малко candidates за analog, по-малко цикъла. Top analog може да е статистически слаб (similarity < 0.7).

2. **Ден-1 lag в release schedules:**
   - Eurostat: HICP flash → final cycle (45+ ден lag за финалните стойности)
   - ECB: rates сами-day; balance sheet седмично; M3 monthly с 3 sedmici lag
   - Adapter cache TTL се адаптира по `release_schedule` за всяка серия

3. **Sovereign spread proxy за HY OAS** — BTP-Bund е sovereign credit, не corporate. За v1 е приемлив proxy; в `analog_matcher.py` интерпретацията на 5-та dim като "stress" е coherent, но не идентична на US HY OAS semantics.

4. **Country drill-down пропуснат за v1.** Catalog поддържа DE/FR/IT/ES в `ALLOWED_REGIONS`, но активните серии са EA-aggregate. Phase 2.0 candidate.

5. **Cross-lens divergence pairs не са populating-нати.** `catalog/cross_lens_pairs.py` е празен в v1; `analysis/divergence.py` е готов но без data input. Phase 1.5/2.5 candidate когато 25+ серии се натрупат.

6. **Analytics из copy-нати от US** — `analysis/breadth.py`, `non_consensus.py`, `anomaly.py`, `executive.py` са data-source agnostic, работят на каталожни ключове. `executive.py` narrative templates все още имат "Fed" referencи (TODO Phase 3.5 за ECB прерайт).

---

## 9. Validation

134 pytest теста покриват:
- **Adapter behavior** (mocked HTTP): SDMX-JSON parser, JSON-stat parser, period parsing, cache I/O, retry на transient errors, fail-fast на permanent errors
- **Catalog integrity**: validate_catalog() за всички 16 серии, lens whitelist, source whitelist
- **Module logic**: unified return shape, invert semantics, transform application, partial snapshot resilience
- **Macro vector**: derived dim correctness (real_dfr, sovereign_stress, yc_10y2y), Sahm rule, z-score properties, today cutoff
- **Briefing rendering**: composite computation, section renderers, edge cases (empty modules, zero series)
- **Journal layer**: slugify (Unicode-safe), frontmatter parsing, save/load CRUD, filter by topic/status/tags

---

## 10. Допълнителни ресурси

- [README.md](README.md) — high-level overview, quick start
- [AGENT.md](AGENT.md) — orientation за AI assistents в бъдещи сесии
- [PHASES.md](PHASES.md) — build log на 6-те phase-а
- [journal/HOWTO.md](journal/HOWTO.md) — research workflow conventions

---

**Last updated:** 2026-04-28 (v0.1.0 MVP release)
