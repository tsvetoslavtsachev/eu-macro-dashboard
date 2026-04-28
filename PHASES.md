# PHASES.md — Build log на eu-macro-dashboard

Хронологичен запис на 6-те фази на v0.1.0 MVP.

---

## Phase 0: Setup (28 April 2026, commit `0cab670`)

**Цел:** Skeleton + portable analytics layer copy.

**Какво се направи:**
- Sibling папка `eu_macro_dashboard/` (paralleln с `Macro_Intelligence/`)
- Git init, remote add, initial structure
- Копирани 1:1 от US: `core/primitives.py`, `analysis/{breadth,divergence,non_consensus,anomaly,executive,delta,guardrails,macro_vector,analog_matcher,analog_comparison,forward_path,analog_pipeline}.py`
- Stubs за нови файлове: `sources/{ecb,eurostat}_adapter.py`, `catalog/{series,cross_lens_pairs}.py`, `modules/{labor,inflation,growth,ecb}.py`, `export/{weekly_briefing,data_status}.py`, `run.py`
- `config.py` с EA-калибрирани weights (inflation 30%, ECB 15%) и BG regime labels
- `requirements.txt` (без fredapi; добавен requests)
- `.env.example` (без API keys — ECB/Eurostat не изискват)
- BG `journal/HOWTO.md`, `_template.md`, 7 topic поддиректории
- `LICENSE` (MIT), updated `README.md`, `run.bat` (Windows menu)
- 24 модула importable чисто, `python run.py --status` минава с empty catalog

**Cleanup commit `4970a18`:**
- Audit на US остатъци; generalize "FRED" в source-agnostic модули
- TODO банери на 7 файла с реално US съдържание (macro_vector, analog_matcher, executive narratives, guardrails signals)
- Запазени cross-references в headers за orientation

---

## Phase 1: Data Layer (commit `39d37a5`)

**Цел:** Real ECB + Eurostat adapter-и + catalog с EA серии.

**Какво се направи:**
- `sources/_base.py` — BaseAdapter с shared cache I/O (JSON), retry на transient errors (5xx/timeout, backoff [2,5,15]), fail-fast на permanent (4xx), tolerant JSON parser за корумпиран cache
- `sources/ecb_adapter.py` — ECB Data Portal SDMX REST + SDMX-JSON 1.0 parser; period parsing (monthly, quarterly, weekly, daily, annual)
- `sources/eurostat_adapter.py` — Eurostat REST + JSON-stat 2.0 parser
- 8 паралелни regex паттерна за Eurostat period strings (M01 vs -01 формати)
- `catalog/series.py` — 15 EA серии с пълна metadata
- `export/data_status.py` — console status report multi-source
- `run.py --status --refresh` end-to-end функционален
- 66 теста (mocked HTTP responses, parser correctness, cache behavior)

**Confirmed working ECB serии:**
- CISS, DFR, MRO, MLF, M3_YOY, EA_BUND_10Y, ECB_BALANCE_SHEET, IT_10Y, FR_10Y, DE_10Y

**Confirmed working Eurostat серии:**
- EA_UNRATE, EA_HICP_HEADLINE, EA_HICP_CORE, EA_HICP_SERVICES, EA_IP

**Bug fixes намерени в hot-fix loop:**
- Eurostat parser първоначално не разпознаваше "1983-01" формат — fix с 8 паралелни regex паттерна
- ECB parser връщаше `pd.NaT` за празни strings — fix към `None`

**Lessons learned:**
- Eurostat geo код варира по dataset: `EA21` за `une_rt_m`/`sts_inpr_m`, `EA` за `prc_hicp_manr`
- Eurostat 413 Payload Too Large при липсващи filters — нужни `unit=`, `coicop=`
- Лесно се mocка през requests.Session.get patch

---

## Phase 2: Lens Modules (commit `b5d7be6`)

**Цел:** 4 lens модула с modern snapshot interface.

**Какво се направи:**
- `core/scorer.py` — функции за нормализиране (percentile_rank, z_score, score_series, composite_score, get_regime, build_sparkline, build_historical_context)
- `modules/labor.py` — UNRATE с invert; режими ГОРЕЩ/ЗДРАВ/ОХЛАЖДАЩ/СЛАБ/СТРЕСИРАН
- `modules/inflation.py` — HICP composite; режими ОСТРА ИНФЛАЦИЯ → ДЕФЛАЦИОНЕН РИСК
- `modules/growth.py` — IP YoY transform; режими ЕКСПАНЗИЯ → РЕЦЕСИЯ
- `modules/ecb.py` — НОВ lens (без US аналог); DFR + balance + MRO; режими ПРОБЛЕМАТИЧНО ТЯСНА → СИЛНО СТИМУЛАТИВНА
- `run.py --modules` — console summary + композитен macro score
- 80 теста total (+14 нови)

**Дизайн решение:** modern snapshot interface вместо legacy client. Modules вземат `dict[str, pd.Series]` директно — отделени от data sources, лесно за тестване.

**Live результат (2026-04-28):**
- Labor 99.7 ГОРЕЩ · Inflation 71.8 ЕЛЕВИРАНА · Growth 28.5 РЕЦЕСИЯ · ECB 68.0 РЕСТРИКТИВНА
- Композитен Macro Score: 65.5 → ЗДРАВ

---

## Phase 3: Briefing (commit `7522157`)

**Цел:** HTML weekly briefing на български.

**Какво се направи:**
- `export/weekly_briefing.py` — self-contained HTML (inline CSS, без JS, без CDN)
- 5 секции: header (composite score + regime), executive (4-модулна table), per-module блокове, top anomalies (от `analysis/anomaly.py`), footer (методология)
- Print-friendly CSS (@media print)
- `run.py --briefing` — fetch snapshot + run modules + render HTML + open в браузър (`--no-browser` за CI)
- 91 теста total (+11 нови)

**Sections отложени за по-късни phases:**
- Cross-lens divergence (CROSS_LENS_PAIRS празен)
- Non-consensus highlights (никоя серия не е tagged)
- WoW delta (изисква sequential briefings с persisted state)

---

## Phase 4: Historical Analog Engine (commit `ca1b02b`)

**Цел:** EA 7-dim macro vector + analog matcher + forward outcomes.

**Какво се направи:**
- `analysis/macro_vector.py` пренаписан за EA — 7 dimensions (US имаше 8; expectations отложен)
- 7 EA dimensions: unrate, core_hicp_yoy, real_dfr, yc_10y2y, sovereign_stress (BTP-Bund), ip_yoy, sahm
- Без proxy splicing — чиста EMU история от 1999
- `analysis/analog_matcher.py` HISTORICAL_EPISODES пренаписан с EA episodes (Dotcom, ECB hike cycle, GFC, EU sovereign debt crisis EA-unique, Draghi, QE, Brexit, COVID+PEPP, Energy shock, Disinflation)
- `analysis/forward_path.py` DEFAULT_OUTCOME_DIMS обновен към EA dim names
- `catalog/series.py` добавен EA_BUND_2Y → catalog 16 серии
- `export/weekly_briefing.py` нова `_render_analogs()` секция: текущ state, top-3 analog table, forward outcomes по horizon
- `run.py --with-analogs` flag wired
- 109 теста total (+18 за macro_vector)

**Live анализ (2025-12 EA макро):**
- Top analog: 2008-03 (similarity 0.76, GFC pre-recession)
- Други: 2023-12 (Disinflation, 0.71), 2007-02 (ECB rate hike cycle, 0.65)

---

## Phase 5: Research Desk (commit `c0cc88e`)

**Цел:** Journal layer + sandbox scaffolding.

**Какво се направи:**
- `scripts/_utils.py` — JournalEntry dataclass, save/load CRUD, filter (topic/status/tags/since), sandbox scaffolding с template
- `_slugify` Unicode-safe (кирилица в filenames)
- YAML frontmatter parser (date, topic, title, tags, status, related_briefing, related_scripts)
- `scripts/build_journal_index.py` — генерира `journal/README.md` с BG topic labels (Трудов пазар, Кредит, ...) и status badges (❓🧪✓◆)
- `export/weekly_briefing.py` `_render_journal()` секция в HTML
- `run.py --with-journal` flag wired
- 134 теста total (+25 за journal)

**Privacy design:** journal/<topic>/*.md в .gitignore (само framework публичен — _template.md, HOWTO.md). Личните бележки остават локално.

---

## Phase 6: Final Package (this commit)

**Цел:** Production-ready docs + tag v0.1.0.

**Какво се направи:**
- Updated `README.md` за v0.1.0 (всички 6 phase-а ✅; quick start с реални команди; 16 серии)
- `FRAMEWORK.md` — пълна методология (lens scoring, regime mapping, composite, analog engine, caveats, validation)
- `AGENT.md` — orientation за бъдещи AI sessions (architecture, conventions, troubleshooting, what NOT to do)
- `PHASES.md` — този файл (chronological build log)
- Тагване v0.1.0

---

## Final state v0.1.0 MVP

```
Lines of code (excluding tests): ~3500
Tests passing: 134
Series в catalog: 16 (10 ECB + 5 Eurostat + 1 derived)
Lens модули: 4 (labor, inflation, growth, ecb)
Macro vector dimensions: 7
Briefing sections: 6 (header, executive, per-module, analogs, anomalies, journal)
Live data through: 2026-04-28 (CISS, ECB rates), 2025-12 (HICP), 2026-02 (IP, UNRATE)
```

End-to-end команда от scratch до пълен briefing:
```bash
git clone https://github.com/tsvetoslavtsachev/eu-macro-dashboard.git
cd eu-macro-dashboard
pip install -r requirements.txt
python run.py --status --refresh
python run.py --briefing --with-analogs --with-journal
```

---

## Phase 4.5: 8-dim macro vector — inflation expectations (post-v0.1.0)

**Цел:** Активиране на 8-та dimension в macro vector чрез ECB SPF long-term HICP forecast.

**Какво се направи:**
- Research: probed ECB Data Portal SDMX REST API; намерен ECB_FCT1 datastructure с 7 dimensions (FREQ, REF_AREA, FCT_TOPIC, FCT_BREAKDOWN, FCT_HORIZON, SURVEY_FREQ, FCT_SOURCE)
- Discovered key: `SPF/Q.U2.HICP.POINT.LT.Q.001` — long-term point forecast (1999+, quarterly)
- catalog/series.py: добавен `EA_SPF_HICP_LT` (peer_group=expectations, в inflation lens)
- analysis/macro_vector.py:
  - STATE_VECTOR_DIMS extended to 8: `["unrate", "core_hicp_yoy", "real_dfr", "yc_10y2y", "sovereign_stress", "ip_yoy", "sahm", "inflation_expectations"]`
  - DIM_LABELS_BG / DIM_UNITS обновени
  - build_history_matrix: SPF quarterly → forward-filled monthly за alignment
- Tests: 134 → 136 (+2 нови за SPF behavior — quarterly→monthly fill, missing series resilience)
- Catalog: 16 → 17 серии

**Effects върху analog matching (cosine similarity refinement):**

7-dim vs 8-dim top-3:
```
7-dim (Phase 4 baseline):  Phase 4.5 (8-dim):
  2008-03  0.756              2008-03  0.781
  2023-12  0.707              2023-12  0.727
  2007-02  0.646              2007-02  0.682
```
8-та dim добавя refining signal — текущите EA inflation expectations (2.00%) са anchored at target (similar to 2008-03 pre-GFC anchoring), което подсилва analog match-а.

**Текущ state на dim 8 (2025-12):** **2.00%** — perfectly anchored at ECB target.

---

## Roadmap отвъд v0.2.0

| Priority | Item | Estimated effort |
|---|---|---|
| High | Populate `catalog/cross_lens_pairs.py` (стагфлация тест, ECB transmission) | 1 session |
| High | Add 10+ серии (PMI ESI subindices, retail trade, building permits, employment LFS) | 1-2 sessions |
| Medium | WoW delta активиране в run.py + briefing | 0.5 session |
| Medium | `analysis/executive.py` Fed→ECB narrative rewrite | 0.5 session |
| Medium | `analysis/guardrails.py` US→EA signal rewrite | 0.5 session |
| Low | Country drill-down (DE/FR/IT/ES) — отделна Phase 2 версия | 3+ sessions |
| Low | OECD adapter (Phase 1 wishlist) | 1 session |

---

**Last updated:** 2026-04-28 (v0.1.0 MVP release).
