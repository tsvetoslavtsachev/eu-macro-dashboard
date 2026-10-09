"""Tests за export/cache_age.py — сензорът за застинал локален кеш."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from export.cache_age import API_CACHES, cache_ages, format_warning, stale_caches

NOW = datetime(2026, 10, 9, 12, 0)


def _write(tmp_path: Path, src: str, *stamps: datetime) -> None:
    data = {f"S{i}": {"last_fetched": s.isoformat(), "data": {}} for i, s in enumerate(stamps)}
    (tmp_path / f"{src}_cache.json").write_text(json.dumps(data), encoding="utf-8")


def test_fresh_caches_are_silent(tmp_path):
    for src in API_CACHES:
        _write(tmp_path, src, NOW - timedelta(days=2))
    assert stale_caches(tmp_path, now=NOW) == {}
    assert format_warning({}) == ""


def test_june_cache_is_flagged(tmp_path):
    """Точно случаят от 2026: кеш от 18.06, гледан на 09.10."""
    for src in API_CACHES:
        _write(tmp_path, src, NOW - timedelta(days=1))
    _write(tmp_path, "eurostat", datetime(2026, 6, 18, 10, 0))
    stale = stale_caches(tmp_path, now=NOW)
    assert list(stale) == ["eurostat"]
    assert 112 < stale["eurostat"] < 114
    msg = format_warning(stale)
    assert "eurostat" in msg and "--refresh-only" in msg


def test_newest_stamp_counts(tmp_path):
    """Една стара серия в иначе опреснен файл не е застинал кеш (това е работа на --status)."""
    _write(tmp_path, "ecb", NOW - timedelta(days=60), NOW - timedelta(days=1))
    assert cache_ages(tmp_path, now=NOW)["ecb"] < 2


def test_missing_and_broken_files_are_flagged(tmp_path):
    (tmp_path / "oecd_cache.json").write_text("{not json", encoding="utf-8")
    stale = stale_caches(tmp_path, now=NOW)
    assert stale["oecd"] is None and stale["nbb"] is None
    assert "липсва" in format_warning(stale)
