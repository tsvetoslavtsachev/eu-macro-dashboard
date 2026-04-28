"""Tests за scripts/_utils.py — journal layer и sandbox scaffolding."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts._utils import (
    JournalEntry,
    VALID_TOPICS,
    VALID_STATUSES,
    _parse_frontmatter,
    _coerce_date,
    _slugify,
    load_journal_entry,
    load_journal_entries,
    save_journal_entry,
    new_sandbox_script,
)


# ── Internal helpers ───────────────────────────────────────────

def test_slugify_handles_cyrillic():
    """Slug-ификация трябва да запази кирилицата."""
    assert _slugify("BTP-Bund стрес") == "btp-bund-стрес"


def test_slugify_handles_special_chars():
    assert _slugify("Hello, World! (2024)") == "hello-world-2024"


def test_slugify_empty_returns_default():
    assert _slugify("") == "untitled"
    assert _slugify("!@#$") == "untitled"


def test_coerce_date_handles_iso_string():
    assert _coerce_date("2026-04-28") == date(2026, 4, 28)


def test_coerce_date_passes_through_date():
    d = date(2026, 4, 28)
    assert _coerce_date(d) == d


def test_coerce_date_returns_none_for_garbage():
    assert _coerce_date("not a date") is None
    assert _coerce_date(None) is None


# ── Frontmatter parser ─────────────────────────────────────────

def test_parse_frontmatter_extracts_yaml():
    text = """---
date: 2026-04-28
topic: credit
title: Test
---

Body content here.
"""
    fm, body = _parse_frontmatter(text)
    assert fm["topic"] == "credit"
    assert fm["title"] == "Test"
    assert body.strip() == "Body content here."


def test_parse_frontmatter_no_frontmatter_returns_empty():
    fm, body = _parse_frontmatter("Just a plain markdown file.")
    assert fm == {}
    assert body == "Just a plain markdown file."


def test_parse_frontmatter_handles_invalid_yaml():
    text = "---\nthis is: [not] valid: yaml :: !\n---\n\nbody"
    fm, body = _parse_frontmatter(text)
    assert isinstance(fm, dict)


# ── Save journal entry ─────────────────────────────────────────

def test_save_journal_entry_creates_file(tmp_path):
    p = save_journal_entry(
        topic="credit",
        title="BTP-Bund стрес тест",
        body="## Анализ\n\nстрес показателя растe...",
        tags=["sovereign_spreads"],
        status="hypothesis",
        entry_date=date(2026, 4, 28),
        journal_dir=tmp_path,
    )
    assert p.exists()
    assert p.parent.name == "credit"
    assert "2026-04-28" in p.name
    text = p.read_text(encoding="utf-8")
    assert "topic: credit" in text
    assert "BTP-Bund стрес тест" in text
    assert "## Анализ" in text


def test_save_journal_entry_unique_filenames(tmp_path):
    """Two entries with same title и date → -2 suffix."""
    p1 = save_journal_entry("credit", "Test", "body 1",
                             entry_date=date(2026, 4, 28), journal_dir=tmp_path)
    p2 = save_journal_entry("credit", "Test", "body 2",
                             entry_date=date(2026, 4, 28), journal_dir=tmp_path)
    assert p1 != p2
    assert "-2" in p2.name


def test_save_journal_entry_rejects_invalid_topic(tmp_path):
    with pytest.raises(ValueError, match="Unknown topic"):
        save_journal_entry("not_a_topic", "T", "B", journal_dir=tmp_path)


def test_save_journal_entry_rejects_invalid_status(tmp_path):
    with pytest.raises(ValueError, match="Unknown status"):
        save_journal_entry("credit", "T", "B", status="invalid", journal_dir=tmp_path)


# ── Load journal entries ───────────────────────────────────────

def test_load_journal_entry_reads_saved(tmp_path):
    p = save_journal_entry(
        "labor", "Test entry", "Body",
        tags=["wages"], status="finding",
        entry_date=date(2026, 3, 15),
        journal_dir=tmp_path,
    )
    entry = load_journal_entry(p)
    assert entry is not None
    assert entry.topic == "labor"
    assert entry.title == "Test entry"
    assert entry.tags == ["wages"]
    assert entry.status == "finding"
    assert entry.date == date(2026, 3, 15)


def test_load_journal_entry_skips_template_files(tmp_path):
    template = tmp_path / "_template.md"
    template.write_text("---\ndate: 2026-01-01\ntopic: credit\n---\nbody", encoding="utf-8")
    assert load_journal_entry(template) is None


def test_load_journal_entry_skips_invalid_topic(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_text("---\ndate: 2026-01-01\ntopic: not_real\n---\nbody", encoding="utf-8")
    assert load_journal_entry(bad) is None


def test_load_journal_entries_returns_sorted_descending(tmp_path):
    save_journal_entry("credit", "Old", "b1", entry_date=date(2026, 1, 1), journal_dir=tmp_path)
    save_journal_entry("credit", "New", "b2", entry_date=date(2026, 4, 28), journal_dir=tmp_path)
    entries = load_journal_entries(journal_dir=tmp_path)
    assert len(entries) == 2
    assert entries[0].title == "New"
    assert entries[1].title == "Old"


def test_load_journal_entries_filters_by_topic(tmp_path):
    save_journal_entry("credit", "C1", "b", journal_dir=tmp_path)
    save_journal_entry("labor", "L1", "b", journal_dir=tmp_path)
    save_journal_entry("inflation", "I1", "b", journal_dir=tmp_path)

    credit_entries = load_journal_entries(topic="credit", journal_dir=tmp_path)
    assert len(credit_entries) == 1
    assert credit_entries[0].topic == "credit"


def test_load_journal_entries_filters_by_status(tmp_path):
    save_journal_entry("credit", "Q1", "b", status="open_question", journal_dir=tmp_path)
    save_journal_entry("credit", "F1", "b", status="finding", journal_dir=tmp_path)

    findings = load_journal_entries(status="finding", journal_dir=tmp_path)
    assert len(findings) == 1
    assert findings[0].status == "finding"


def test_load_journal_entries_filters_by_tags():
    """tags_any filter — поне един от подадените тагове."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        save_journal_entry("credit", "T1", "b", tags=["btp", "stress"], journal_dir=tmp_path)
        save_journal_entry("credit", "T2", "b", tags=["other"], journal_dir=tmp_path)

        btp_entries = load_journal_entries(tags_any=["btp"], journal_dir=tmp_path)
        assert len(btp_entries) == 1


def test_load_journal_entries_empty_dir_returns_empty():
    """Несъществуваща папка → празен списък без грешки."""
    entries = load_journal_entries(journal_dir=Path("/nonexistent/path/that/should/not/exist"))
    assert entries == []


# ── Sandbox scaffolding ────────────────────────────────────────

def test_new_sandbox_script_creates_file(tmp_path):
    p = new_sandbox_script("CISS vs sovereign spreads", sandbox_dir=tmp_path)
    assert p.exists()
    assert p.suffix == ".py"
    text = p.read_text(encoding="utf-8")
    assert "CISS vs sovereign spreads" in text
    assert "from scripts._utils import" in text
    assert "load_briefing_snapshot" in text


def test_new_sandbox_script_unique_names(tmp_path):
    p1 = new_sandbox_script("Test", sandbox_dir=tmp_path)
    p2 = new_sandbox_script("Test", sandbox_dir=tmp_path)
    assert p1 != p2


# ── Whitelists ─────────────────────────────────────────────────

def test_valid_topics_match_journal_dirs():
    """VALID_TOPICS трябва да съвпадат с journal/ subdirs."""
    assert "labor" in VALID_TOPICS
    assert "inflation" in VALID_TOPICS
    assert "credit" in VALID_TOPICS
    assert "growth" in VALID_TOPICS


def test_valid_statuses_4_levels():
    assert len(VALID_STATUSES) == 4
    assert "open_question" in VALID_STATUSES
    assert "finding" in VALID_STATUSES
