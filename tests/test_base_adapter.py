"""Tests за sources/_base.py — споделена cache + retry логика."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sources._base import (
    BaseAdapter,
    classify_fetch_error,
    tolerant_parse_cache,
)


# ── Error classification ───────────────────────────────────────

def test_classify_5xx_as_transient():
    err = RuntimeError("HTTP 502 Bad Gateway")
    assert classify_fetch_error(err) == "transient"


def test_classify_4xx_as_permanent():
    err = RuntimeError("HTTP 404 Not Found")
    assert classify_fetch_error(err) == "permanent"


def test_classify_status_code_attribute():
    err = RuntimeError("boom")
    err.status_code = 500
    assert classify_fetch_error(err) == "transient"
    err.status_code = 404
    assert classify_fetch_error(err) == "permanent"


def test_classify_timeout_as_transient():
    assert classify_fetch_error(RuntimeError("connection timed out")) == "transient"


def test_classify_unknown_as_transient_conservative():
    assert classify_fetch_error(RuntimeError("strange thing")) == "transient"


# ── Tolerant cache parser ──────────────────────────────────────

def test_tolerant_parse_handles_truncated_tail():
    """Ако cache .json е cut на края, парсерът трябва да recover-не валидните серии."""
    full = '{"A": {"x": 1}, "B": {"x": 2}, "C": {"x":'  # truncated при C
    out = tolerant_parse_cache(full)
    assert "A" in out
    assert "B" in out
    assert "C" not in out


def test_tolerant_parse_empty_string_returns_empty():
    assert tolerant_parse_cache("") == {}


def test_tolerant_parse_garbage_returns_empty():
    assert tolerant_parse_cache("not json") == {}


# ── BaseAdapter — cache I/O ────────────────────────────────────

class _StubAdapter(BaseAdapter):
    """Test stub: _fetch_remote е controllable от tests."""

    SOURCE_NAME = "stub"

    def __init__(self, *args, fetch_response=None, fetch_error=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._fetch_response = fetch_response
        self._fetch_error = fetch_error

    def _fetch_remote(self, series_key, source_id):
        if self._fetch_error is not None:
            raise self._fetch_error
        return self._fetch_response if self._fetch_response is not None else pd.Series(dtype=float)


def test_base_adapter_stores_and_retrieves_from_cache(tmp_path):
    series = pd.Series([1.0, 2.0, 3.0], index=pd.date_range("2024-01-01", periods=3, freq="MS"))
    a = _StubAdapter(cache_path="c.json", base_dir=tmp_path, fetch_response=series, retry_backoff=[])
    s = a.fetch("KEY", "id", "monthly", force=True)
    assert len(s) == 3
    a.save_cache()  # save_cache() се извиква само от fetch_many; тук ръчно

    # Now load fresh adapter — кешът трябва да съдържа данните
    a2 = _StubAdapter(cache_path="c.json", base_dir=tmp_path, retry_backoff=[])
    s2 = a2._series_from_cache("KEY")
    assert len(s2) == 3
    assert s2.iloc[0] == 1.0


def test_base_adapter_fresh_within_ttl(tmp_path):
    series = pd.Series([1.0], index=pd.date_range("2024-01-01", periods=1, freq="MS"))
    a = _StubAdapter(cache_path="c.json", base_dir=tmp_path, fetch_response=series, retry_backoff=[])
    a.fetch("KEY", "id", "monthly", force=True)
    assert a._is_cache_fresh("KEY", "monthly")


def test_base_adapter_falls_back_to_cache_on_error(tmp_path):
    series = pd.Series([42.0], index=pd.date_range("2024-01-01", periods=1, freq="MS"))
    a = _StubAdapter(cache_path="c.json", base_dir=tmp_path, fetch_response=series, retry_backoff=[])
    a.fetch("KEY", "id", "monthly", force=True)

    a._fetch_response = None
    a._fetch_error = RuntimeError("HTTP 500 boom")
    s = a.fetch("KEY", "id", "monthly", force=True)
    assert not s.empty
    assert s.iloc[0] == 42.0
    assert "KEY" in a.last_fetch_failures()


def test_base_adapter_permanent_error_no_retry(tmp_path):
    """4xx грешки да не предизвикват retry — fail fast."""
    a = _StubAdapter(
        cache_path="c.json", base_dir=tmp_path,
        fetch_error=RuntimeError("HTTP 404 Not Found"),
        retry_backoff=[0, 0, 0],  # zero sleep за бързи tests
    )
    # _fetch_with_retry трябва да хвърли веднага
    call_count = {"n": 0}
    original = a._fetch_remote
    def counter(*args, **kwargs):
        call_count["n"] += 1
        return original(*args, **kwargs)
    a._fetch_remote = counter

    with pytest.raises(RuntimeError, match="404"):
        a._fetch_with_retry("KEY", "id")
    assert call_count["n"] == 1  # без retry


def test_base_adapter_transient_error_retries(tmp_path):
    """5xx грешки трябва да предизвикат retry."""
    a = _StubAdapter(
        cache_path="c.json", base_dir=tmp_path,
        fetch_error=RuntimeError("HTTP 503 Service Unavailable"),
        retry_backoff=[0, 0, 0],  # 3 retries, zero sleep
    )
    call_count = {"n": 0}
    original = a._fetch_remote
    def counter(*args, **kwargs):
        call_count["n"] += 1
        return original(*args, **kwargs)
    a._fetch_remote = counter

    with pytest.raises(RuntimeError, match="503"):
        a._fetch_with_retry("KEY", "id")
    assert call_count["n"] == 4  # 1 initial + 3 retries


def test_base_adapter_get_snapshot_skips_missing(tmp_path):
    series = pd.Series([1.0], index=pd.date_range("2024-01-01", periods=1, freq="MS"))
    a = _StubAdapter(cache_path="c.json", base_dir=tmp_path, fetch_response=series, retry_backoff=[])
    a.fetch("KEY1", "id", "monthly", force=True)
    snap = a.get_snapshot(["KEY1", "MISSING"])
    assert "KEY1" in snap
    assert "MISSING" not in snap


def test_base_adapter_invalidate(tmp_path):
    series = pd.Series([1.0], index=pd.date_range("2024-01-01", periods=1, freq="MS"))
    a = _StubAdapter(cache_path="c.json", base_dir=tmp_path, fetch_response=series, retry_backoff=[])
    a.fetch("KEY", "id", "monthly", force=True)
    assert a.get_cache_status("KEY")["is_cached"]
    a.invalidate("KEY")
    assert not a.get_cache_status("KEY")["is_cached"]


def test_base_adapter_find_stale_specs(tmp_path):
    series = pd.Series([1.0], index=pd.date_range("2024-01-01", periods=1, freq="MS"))
    a = _StubAdapter(cache_path="c.json", base_dir=tmp_path, fetch_response=series, retry_backoff=[])
    a.fetch("FRESH_KEY", "id1", "monthly", force=True)

    specs = [
        {"key": "FRESH_KEY", "source_id": "id1", "release_schedule": "monthly"},
        {"key": "MISSING_KEY", "source_id": "id2", "release_schedule": "monthly"},
    ]
    stale = a.find_stale_specs(specs)
    assert len(stale) == 1
    assert stale[0]["key"] == "MISSING_KEY"
