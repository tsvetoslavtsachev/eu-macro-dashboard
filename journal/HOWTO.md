# Research Journal — Eurozone

Структурирани markdown бележки за наблюдения, хипотези и заключения от EA анализа.

## Защо тази папка е почти празна в публичното репо?

По дизайн. Публичното репо съдържа **рамката** — directory structure per topic, шаблон, index generator. Самите записи са лични бележки и не се commit-ват в git (виж `.gitignore`).

Ако някой fork-не проекта, неговите `journal/credit/*.md`, `journal/labor/*.md` и т.н. остават локално на машината му.

## Структура

Една поддиректория на тема:

- `labor/` — заетост, заплати, EA labour market dynamics
- `inflation/` — HICP, очаквания, sticky vs flexible
- `credit/` — CISS, sovereign spreads (BTP-Bund), bank lending
- `growth/` — IP, retail, GDP, ESI sentiment
- `analogs/` — historical analog engine наблюдения
- `regime/` — режимни преходи в EA макро
- `methodology/` — framework бележки, calibration решения

## Създаване на записи

Копирай `_template.md` или използвай helper-а (Phase 5):

```python
from scripts._utils import save_journal_entry

save_journal_entry(
    topic="credit",
    title="BTP-Bund stress без CISS confirmation",
    body="## Въпрос\n...\n## Извод\n...",
    tags=["sovereign_spreads", "divergence"],
    status="open_question",  # or hypothesis / finding / decision
)
```

## Index

Локален index (не се commit-ва):

```
python -m scripts.build_journal_index
```

Записва `journal/README.md` — таблица със всички записи групирани по тема. Файлът е `.gitignore`-нат, защото заглавията често съдържат контекст, който не е за публично.
