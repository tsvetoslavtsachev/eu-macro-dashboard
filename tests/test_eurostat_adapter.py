"""Tests за sources/eurostat_adapter.py с mocked HTTP responses."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sources.eurostat_adapter import (
    EurostatAdapter,
    parse_eurostat_period,
    parse_jsonstat,
)


# ── Period parser ──────────────────────────────────────────────

@pytest.mark.parametrize("period,expected", [
    # Monthly — два формата
    ("2024M01",    pd.Timestamp("2024-01-01")),
    ("2024-01",    pd.Timestamp("2024-01-01")),
    ("1983-01",    pd.Timestamp("1983-01-01")),
    # Quarterly — два формата
    ("2024Q1",     pd.Timestamp("2024-01-01")),
    ("2024-Q1",    pd.Timestamp("2024-01-01")),
    ("2024Q4",     pd.Timestamp("2024-10-01")),
    # Annual
    ("2024",       pd.Timestamp("2024-01-01")),
    # Daily
    ("2024-01-15", pd.Timestamp("2024-01-15")),
])
def test_parse_eurostat_period(period, expected):
    assert parse_eurostat_period(period) == expected


def test_parse_eurostat_period_returns_none_on_garbage():
    assert parse_eurostat_period("garbage") is None
    assert parse_eurostat_period("") is None


def test_daily_takes_precedence_over_monthly():
    """YYYY-MM-DD трябва да се interpret като daily, не monthly."""
    assert parse_eurostat_period("2024-01-15") == pd.Timestamp("2024-01-15")


# ── JSON-stat parser ───────────────────────────────────────────

def _jsonstat(periods: list[str], values: dict[int, float], non_time_dims: int = 5) -> dict:
    """Builds минимален JSON-stat 2.0 response.

    non_time_dims: брой дименсии преди time (всички size=1).
    """
    period_index = {p: i for i, p in enumerate(periods)}
    sizes = [1] * non_time_dims + [len(periods)]
    dim_ids = [f"d{i}" for i in range(non_time_dims)] + ["time"]
    return {
        "version": "2.0",
        "class": "dataset",
        "id": dim_ids,
        "size": sizes,
        "value": {str(k): v for k, v in values.items()},
        "dimension": {
            "time": {
                "category": {
                    "index": period_index,
                    "label": {p: p for p in periods},
                }
            }
        }
    }


def test_parse_jsonstat_returns_series():
    payload = _jsonstat(
        periods=["2024-01", "2024-02", "2024-03"],
        values={0: 10.0, 1: 11.5, 2: 9.8},
    )
    s = parse_jsonstat(payload)
    assert len(s) == 3
    assert s.iloc[0] == 10.0
    assert s.index[0] == pd.Timestamp("2024-01-01")


def test_parse_jsonstat_empty_when_no_dimension():
    assert parse_jsonstat({}).empty
    # Missing 'time' dimension трябва да хвърли
    with pytest.raises(ValueError, match="time"):
        parse_jsonstat({"dimension": {}, "id": ["geo"], "size": [1]})


def test_parse_jsonstat_handles_sparse_values():
    """Eurostat може да върне sparse value dict (липсващи indexes)."""
    payload = _jsonstat(
        periods=["2024-01", "2024-02", "2024-03", "2024-04"],
        values={0: 10.0, 2: 12.0},  # dirpусков 1 и 3
    )
    s = parse_jsonstat(payload)
    assert len(s) == 2
    assert s.loc[pd.Timestamp("2024-01-01")] == 10.0
    assert s.loc[pd.Timestamp("2024-03-01")] == 12.0


def test_parse_jsonstat_skips_null_values():
    payload = _jsonstat(
        periods=["2024-01", "2024-02"],
        values={0: 10.0, 1: 11.0},
    )
    payload["value"]["1"] = None
    s = parse_jsonstat(payload)
    assert len(s) == 1


def test_parse_jsonstat_with_offset_indexes():
    """Real Eurostat returns indexes starting от не-нула за серии със gap преди първото observation."""
    payload = _jsonstat(
        periods=["1983-01", "1983-02", "2000-01"],  # 3 periods registered
        values={2: 9.5},  # данни само от 2000
    )
    s = parse_jsonstat(payload)
    assert len(s) == 1
    assert s.iloc[0] == 9.5
    assert s.index[0] == pd.Timestamp("2000-01-01")


# ── Adapter HTTP behavior ──────────────────────────────────────

def _mock_response(status_code: int = 200, json_data: dict | None = None, text: str = "") -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.text = text
    r.json.return_value = json_data or {}
    return r


def test_eurostat_adapter_builds_url_with_filters(tmp_path):
    adapter = EurostatAdapter(base_dir=tmp_path, cache_path="cache.json")
    url = adapter._build_url("une_rt_m?geo=EA21&unit=PC_ACT")
    assert "data/une_rt_m" in url
    assert "format=JSON" in url
    assert "geo=EA21" in url
    assert "unit=PC_ACT" in url


def test_eurostat_adapter_builds_url_without_filters(tmp_path):
    adapter = EurostatAdapter(base_dir=tmp_path, cache_path="cache.json")
    url = adapter._build_url("une_rt_m")
    assert url.endswith("data/une_rt_m?format=JSON")


def test_eurostat_adapter_404_raises(tmp_path):
    adapter = EurostatAdapter(base_dir=tmp_path, cache_path="cache.json", retry_backoff=[])
    with patch.object(adapter._session, "get", return_value=_mock_response(404, text="Not Found")):
        with pytest.raises(ValueError, match="Not Found"):
            adapter._fetch_remote("TEST", "foo")


def test_eurostat_adapter_fetch_returns_series_from_mock(tmp_path):
    payload = _jsonstat(["2024-01", "2024-02"], {0: 1.0, 1: 2.0})
    adapter = EurostatAdapter(base_dir=tmp_path, cache_path="cache.json", retry_backoff=[])
    with patch.object(adapter._session, "get", return_value=_mock_response(200, json_data=payload)):
        s = adapter.fetch("TEST", "foo?bar=baz", "monthly", force=True)
    assert len(s) == 2
    assert s.iloc[0] == 1.0


def test_eurostat_adapter_caches_after_fetch(tmp_path):
    payload = _jsonstat(["2024-01"], {0: 42.0})
    adapter = EurostatAdapter(base_dir=tmp_path, cache_path="cache.json", retry_backoff=[])
    with patch.object(adapter._session, "get", return_value=_mock_response(200, json_data=payload)):
        adapter.fetch("TEST", "foo", "monthly", force=True)
    status = adapter.get_cache_status("TEST")
    assert status["is_cached"]
    assert status["n_observations"] == 1
