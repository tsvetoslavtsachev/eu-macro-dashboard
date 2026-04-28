"""Tests за sources/ecb_adapter.py с mocked HTTP responses."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sources.ecb_adapter import (
    EcbAdapter,
    parse_ecb_period,
    parse_sdmx_json,
)


# ── Period parser ──────────────────────────────────────────────

@pytest.mark.parametrize("period,expected", [
    ("2024-01",    pd.Timestamp("2024-01-01")),
    ("2024-Q1",    pd.Timestamp("2024-01-01")),
    ("2024-Q2",    pd.Timestamp("2024-04-01")),
    ("2024-Q4",    pd.Timestamp("2024-10-01")),
    ("2024",       pd.Timestamp("2024-01-01")),
    ("2024-01-15", pd.Timestamp("2024-01-15")),
])
def test_parse_ecb_period(period, expected):
    assert parse_ecb_period(period) == expected


def test_parse_ecb_period_returns_none_on_garbage():
    assert parse_ecb_period("garbage") is None
    assert parse_ecb_period("") is None


# ── SDMX-JSON parser ───────────────────────────────────────────

def _sdmx_payload(periods: list[str], values: list[float]) -> dict:
    """Builds минимален SDMX-JSON 1.0 response."""
    obs_dict = {str(i): [v, 0] for i, v in enumerate(values)}
    return {
        "header": {"id": "test"},
        "dataSets": [{
            "series": {
                "0:0:0:0:0:0": {"observations": obs_dict}
            }
        }],
        "structure": {
            "dimensions": {
                "observation": [{
                    "id": "TIME_PERIOD",
                    "values": [{"id": p} for p in periods]
                }]
            }
        }
    }


def test_parse_sdmx_returns_series():
    payload = _sdmx_payload(["2024-01", "2024-02", "2024-03"], [10.0, 11.5, 9.8])
    s = parse_sdmx_json(payload)
    assert len(s) == 3
    assert s.iloc[0] == 10.0
    assert s.iloc[-1] == 9.8
    assert s.index[0] == pd.Timestamp("2024-01-01")
    assert s.index[-1] == pd.Timestamp("2024-03-01")


def test_parse_sdmx_empty_when_no_datasets():
    assert parse_sdmx_json({}).empty
    assert parse_sdmx_json({"dataSets": []}).empty
    assert parse_sdmx_json({"dataSets": [{"series": {}}]}).empty


def test_parse_sdmx_skips_invalid_periods():
    payload = _sdmx_payload(["2024-01", "garbage", "2024-03"], [10.0, 11.5, 9.8])
    s = parse_sdmx_json(payload)
    assert len(s) == 2  # garbage период е пропуснат
    assert pd.Timestamp("2024-01-01") in s.index
    assert pd.Timestamp("2024-03-01") in s.index


def test_parse_sdmx_handles_null_values():
    # Observation array без value (e.g. [null, 0]) — пропуска се
    payload = _sdmx_payload(["2024-01", "2024-02"], [10.0, 11.0])
    payload["dataSets"][0]["series"]["0:0:0:0:0:0"]["observations"]["1"] = [None, 0]
    s = parse_sdmx_json(payload)
    assert len(s) == 1
    assert s.iloc[0] == 10.0


# ── Adapter HTTP behavior ──────────────────────────────────────

def _mock_response(status_code: int = 200, json_data: dict | None = None, text: str = "") -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.text = text
    r.json.return_value = json_data or {}
    return r


def test_ecb_adapter_builds_correct_url(tmp_path):
    adapter = EcbAdapter(base_dir=tmp_path, cache_path="cache.json")
    url = adapter._build_url("CISS/D.U2.Z0Z.4F.EC.SS_CIN.IDX")
    assert url == "https://data-api.ecb.europa.eu/service/data/CISS/D.U2.Z0Z.4F.EC.SS_CIN.IDX?format=jsondata"


def test_ecb_adapter_rejects_bad_source_id(tmp_path):
    adapter = EcbAdapter(base_dir=tmp_path, cache_path="cache.json")
    with pytest.raises(ValueError, match="flowref"):
        adapter._build_url("NO_SLASH_HERE")


def test_ecb_adapter_404_raises_value_error(tmp_path):
    adapter = EcbAdapter(base_dir=tmp_path, cache_path="cache.json", retry_backoff=[])
    with patch.object(adapter._session, "get", return_value=_mock_response(404, text="Not Found")):
        with pytest.raises(ValueError, match="Not Found"):
            adapter._fetch_remote("TEST", "FOO/BAR")


def test_ecb_adapter_500_attached_status_code(tmp_path):
    """500 errors must have status_code attribute for classification."""
    adapter = EcbAdapter(base_dir=tmp_path, cache_path="cache.json", retry_backoff=[])
    with patch.object(adapter._session, "get", return_value=_mock_response(500, text="boom")):
        try:
            adapter._fetch_remote("TEST", "FOO/BAR")
            pytest.fail("expected exception")
        except RuntimeError as e:
            assert getattr(e, "status_code", None) == 500


def test_ecb_adapter_fetch_returns_series_from_mock(tmp_path):
    payload = _sdmx_payload(["2024-01", "2024-02"], [1.0, 2.0])
    adapter = EcbAdapter(base_dir=tmp_path, cache_path="cache.json", retry_backoff=[])
    with patch.object(adapter._session, "get", return_value=_mock_response(200, json_data=payload)):
        s = adapter.fetch("TEST", "FOO/BAR", "monthly", force=True)
    assert len(s) == 2
    assert s.iloc[0] == 1.0


def test_ecb_adapter_caches_after_fetch(tmp_path):
    payload = _sdmx_payload(["2024-01"], [42.0])
    adapter = EcbAdapter(base_dir=tmp_path, cache_path="cache.json", retry_backoff=[])
    with patch.object(adapter._session, "get", return_value=_mock_response(200, json_data=payload)):
        adapter.fetch("TEST", "FOO/BAR", "monthly", force=True)
    status = adapter.get_cache_status("TEST")
    assert status["is_cached"] is True
    assert status["n_observations"] == 1
    assert status["last_observation"] == "2024-01-01"


def test_ecb_adapter_falls_back_to_cache_on_failure(tmp_path):
    payload = _sdmx_payload(["2024-01"], [42.0])
    adapter = EcbAdapter(base_dir=tmp_path, cache_path="cache.json", retry_backoff=[])
    with patch.object(adapter._session, "get", return_value=_mock_response(200, json_data=payload)):
        adapter.fetch("TEST", "FOO/BAR", "monthly", force=True)
    # Сега fetch-ът да фейлне, но трябва да върне cache fallback
    with patch.object(adapter._session, "get", return_value=_mock_response(500, text="boom")):
        s = adapter.fetch("TEST", "FOO/BAR", "monthly", force=True)
    assert not s.empty
    assert s.iloc[0] == 42.0
    assert "TEST" in adapter.last_fetch_failures()
