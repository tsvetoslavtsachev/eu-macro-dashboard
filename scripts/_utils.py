"""
scripts/_utils.py
=================
Convenience layer за research desk ad hoc анализи.

Boilerplate за:
  - Зареждане на ECB / Eurostat snapshot (multi-source)
  - Работа с journal entries (load/save, filter по topic/status/date)
  - Създаване на нови sandbox скриптове с template

НЕ е публичен API. Сигнатурите могат да се променят без notice.

Типичен pattern за sandbox script:

    from pathlib import Path
    import sys
    BASE = Path(__file__).resolve().parent.parent.parent  # eu_macro_dashboard/
    sys.path.insert(0, str(BASE))
    from scripts._utils import load_briefing_snapshot, save_journal_entry

    snap = load_briefing_snapshot()
    ciss = snap["EA_CISS"]
    btp_bund = snap["IT_10Y"] - snap["DE_10Y"]
    # … твоя анализ …
    save_journal_entry(
        topic="credit",
        title="BTP-Bund стрес без CISS confirmation",
        body="...",
        tags=["sovereign_spreads"],
        status="finding",
    )
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
JOURNAL_DIR = BASE_DIR / "journal"
SCRIPTS_DIR = BASE_DIR / "scripts"
SANDBOX_DIR = SCRIPTS_DIR / "sandbox"
OUTPUT_DIR = BASE_DIR / "output"

VALID_TOPICS = ["labor", "inflation", "credit", "growth", "analogs", "regime", "methodology"]
VALID_STATUSES = ["open_question", "hypothesis", "finding", "decision"]


# ============================================================
# JOURNAL ENTRY
# ============================================================

@dataclass
class JournalEntry:
    """Структуриран вид на journal запис."""
    path: Path
    date: date
    topic: str
    title: str
    tags: list[str] = field(default_factory=list)
    related_briefing: Optional[str] = None
    related_scripts: list[str] = field(default_factory=list)
    status: str = "open_question"
    body: str = ""

    @property
    def relative_path(self) -> str:
        """Път спрямо eu_macro_dashboard/."""
        try:
            return str(self.path.relative_to(BASE_DIR))
        except ValueError:
            return str(self.path)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Парсва YAML frontmatter от markdown файл.

    Формат: '---\\n<yaml>\\n---\\n<body>'. Връща ({}, text) ако няма frontmatter.
    """
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    body = m.group(2)
    return fm, body


def _coerce_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def load_journal_entry(path: Path) -> Optional[JournalEntry]:
    """Чете един .md файл и връща JournalEntry, или None ако не е валиден."""
    if path.name.startswith("_") or path.name == "README.md":
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    fm, body = _parse_frontmatter(text)
    if not fm:
        return None

    entry_date = _coerce_date(fm.get("date"))
    topic = fm.get("topic")
    if entry_date is None or topic not in VALID_TOPICS:
        return None

    return JournalEntry(
        path=path,
        date=entry_date,
        topic=topic,
        title=str(fm.get("title", path.stem)),
        tags=list(fm.get("tags") or []),
        related_briefing=fm.get("related_briefing"),
        related_scripts=list(fm.get("related_scripts") or []),
        status=fm.get("status", "open_question") if fm.get("status") in VALID_STATUSES else "open_question",
        body=body.strip(),
    )


def load_journal_entries(
    topic: Optional[str] = None,
    status: Optional[str] = None,
    tags_any: Optional[list[str]] = None,
    since: Optional[date] = None,
    journal_dir: Optional[Path] = None,
) -> list[JournalEntry]:
    """Зарежда всички journal entries с optional филтри.

    Args:
        topic: Точно един topic или None.
        status: Точно един статус или None.
        tags_any: Връща entries с поне един от тези тагове.
        since: Включва само entries с date >= since.
        journal_dir: Override за tests.

    Returns:
        Списък сортиран по date descending.
    """
    jdir = journal_dir or JOURNAL_DIR
    if not jdir.exists():
        return []

    entries: list[JournalEntry] = []
    for md in jdir.rglob("*.md"):
        entry = load_journal_entry(md)
        if entry is None:
            continue
        if topic is not None and entry.topic != topic:
            continue
        if status is not None and entry.status != status:
            continue
        if tags_any is not None and not (set(tags_any) & set(entry.tags)):
            continue
        if since is not None and entry.date < since:
            continue
        entries.append(entry)

    entries.sort(key=lambda e: e.date, reverse=True)
    return entries


def save_journal_entry(
    topic: str,
    title: str,
    body: str,
    tags: Optional[list[str]] = None,
    status: str = "open_question",
    related_briefing: Optional[str] = None,
    related_scripts: Optional[list[str]] = None,
    entry_date: Optional[date] = None,
    journal_dir: Optional[Path] = None,
) -> Path:
    """Записва нов journal entry. Връща пътя до записания файл."""
    if topic not in VALID_TOPICS:
        raise ValueError(f"Unknown topic: {topic!r}. Valid: {VALID_TOPICS}")
    if status not in VALID_STATUSES:
        raise ValueError(f"Unknown status: {status!r}. Valid: {VALID_STATUSES}")

    jdir = (journal_dir or JOURNAL_DIR) / topic
    jdir.mkdir(parents=True, exist_ok=True)

    entry_date = entry_date or date.today()
    slug = _slugify(title)
    base_name = f"{entry_date.isoformat()}_{slug}"
    path = jdir / f"{base_name}.md"
    n = 2
    while path.exists():
        path = jdir / f"{base_name}-{n}.md"
        n += 1

    frontmatter = {
        "date": entry_date.isoformat(),
        "topic": topic,
        "title": title,
        "tags": tags or [],
        "related_briefing": related_briefing,
        "related_scripts": related_scripts or [],
        "status": status,
    }
    fm_yaml = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
    path.write_text(f"---\n{fm_yaml}\n---\n\n{body.strip()}\n", encoding="utf-8")
    return path


_SLUG_CLEAN = re.compile(r"[^\w\s-]", re.UNICODE)
_SLUG_SPACES = re.compile(r"[-\s]+")


def _slugify(text: str, max_len: int = 60) -> str:
    """Unicode-safe slugification (работи с кирилица)."""
    text = _SLUG_CLEAN.sub("", text.strip().lower())
    text = _SLUG_SPACES.sub("-", text)
    return text[:max_len].strip("-") or "untitled"


# ============================================================
# DATA LOADERS
# ============================================================

def load_briefing_snapshot(base_dir: Optional[Path] = None) -> dict[str, pd.Series]:
    """Зарежда multi-source snapshot от cache (ECB + Eurostat).

    Lazy import — за да няма overhead при чисти journal операции.
    """
    from sources.ecb_adapter import EcbAdapter
    from sources.eurostat_adapter import EurostatAdapter
    from catalog.series import SERIES_CATALOG, series_by_source

    bdir = base_dir or BASE_DIR
    snapshot: dict[str, pd.Series] = {}

    for adapter, source_name in [(EcbAdapter(base_dir=bdir), "ecb"),
                                  (EurostatAdapter(base_dir=bdir), "eurostat")]:
        keys = [s["_key"] for s in series_by_source(source_name)]
        snapshot.update(adapter.get_snapshot(keys))

    return snapshot


def latest_briefing_path(output_dir: Optional[Path] = None) -> Optional[Path]:
    """Пътя до най-скорошния briefing_YYYY-MM-DD.html в output/."""
    odir = output_dir or OUTPUT_DIR
    if not odir.exists():
        return None
    candidates = sorted(odir.glob("briefing_*.html"))
    return candidates[-1] if candidates else None


def load_current_briefing_html(output_dir: Optional[Path] = None) -> Optional[str]:
    """Текста на последния briefing (ако има)."""
    p = latest_briefing_path(output_dir)
    if p is None:
        return None
    return p.read_text(encoding="utf-8")


# ============================================================
# SANDBOX SCRIPT SCAFFOLDING
# ============================================================

_SANDBOX_TEMPLATE = '''"""
sandbox/{filename}
==================
Ad hoc анализ — {title}

Създаден: {date}
Свързан journal запис: (попълни ръчно след save_journal_entry)
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent  # eu_macro_dashboard/
sys.path.insert(0, str(BASE))

import pandas as pd
import numpy as np

from scripts._utils import (
    load_briefing_snapshot,
    save_journal_entry,
)


# ============================================================
# 1. ВЪПРОС
# ============================================================
QUESTION = """
{title}

TODO: опиши въпроса в 2-4 изречения.
"""


# ============================================================
# 2. ДАННИ
# ============================================================
def load_data() -> dict:
    snap = load_briefing_snapshot()
    # TODO: извади конкретните серии
    # ciss = snap["EA_CISS"]
    # btp_bund = snap["IT_10Y"] - snap["DE_10Y"]
    return {{"snapshot": snap}}


# ============================================================
# 3. АНАЛИЗ
# ============================================================
def analyze(data: dict) -> dict:
    # TODO: твоят анализ
    return {{}}


# ============================================================
# 4. ИЗВОД
# ============================================================
def format_finding(result: dict) -> str:
    return f\"\"\"
## Въпрос

{{QUESTION.strip()}}

## Данни

TODO

## Анализ

TODO

## Извод

TODO
\"\"\".strip()


def main() -> None:
    data = load_data()
    result = analyze(data)
    finding = format_finding(result)
    print(finding)

    # Ако анализът е стойностен — разкомeнтирай и запиши:
    #
    # save_journal_entry(
    #     topic="credit",
    #     title="{title}",
    #     body=finding,
    #     tags=[],
    #     status="open_question",
    #     related_scripts=[Path(__file__).name],
    # )


if __name__ == "__main__":
    main()
'''


def new_sandbox_script(title: str, sandbox_dir: Optional[Path] = None) -> Path:
    """Създава нов sandbox script. Връща пътя."""
    sdir = sandbox_dir or SANDBOX_DIR
    sdir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    slug = _slugify(title)
    base = f"{today}_{slug}"
    path = sdir / f"{base}.py"
    n = 2
    while path.exists():
        path = sdir / f"{base}-{n}.py"
        n += 1

    path.write_text(
        _SANDBOX_TEMPLATE.format(filename=path.name, title=title, date=today),
        encoding="utf-8",
    )
    return path
