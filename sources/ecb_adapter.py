"""
sources/ecb_adapter.py
======================
ECB Data Portal SDMX REST adapter.

API endpoint (без autenticija):
  {base}/data/{flowref}/{key}?format=jsondata

  base    = "https://data-api.ecb.europa.eu/service" (от config.ECB_API_BASE)
  flowref = ECB dataset code (CISS, FM, IRS, BSI, ICP, EXR, ...)
  key     = period-separated dimension values (D.U2.Z0Z.4F.EC.SS_CIN.IDX)

Catalog usage:
  Series-ите имат source="ecb" и id="<flowref>/<key>", напр.
  "CISS/D.U2.Z0Z.4F.EC.SS_CIN.IDX". Adapter-ът split-ва на първото '/'.

Response: SDMX-JSON 1.0
  Документация: https://data-api.ecb.europa.eu/help

Cache:
  Файл `data/ecb_cache.json` (relative to project root).
  Adaptive TTL по release_schedule (виж sources/_base.py).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import requests

from sources._base import BaseAdapter

logger = logging.getLogger(__name__)


# ============================================================
# CONFIG
# ============================================================

DEFAULT_CACHE_PATH = "data/ecb_cache.json"
DEFAULT_TIMEOUT = 30  # секунди
USER_AGENT = "eu-macro-dashboard/0.1 (https://github.com/tsvetoslavtsachev/eu-macro-dashboard)"


# ============================================================
# Период parsing
# ============================================================

def parse_ecb_period(period: str) -> Optional[pd.Timestamp]:
    """Парсва ECB period string на pd.Timestamp.

    ECB ползва различни формати в зависимост от честотата:
      - "2024-01"      monthly
      - "2024-Q1"      quarterly
      - "2024"         annually
      - "2024-W01"     weekly
      - "2024-01-15"   daily

    Връща pd.Timestamp на първия ден на периода (период start),
    или None ако format-ът е unknown.
    """
    period = period.strip()
    if not period:
        return None
    try:
        if "Q" in period:
            year, q = period.split("-Q")
            month = (int(q) - 1) * 3 + 1
            return pd.Timestamp(year=int(year), month=month, day=1)
        if "W" in period:
            year, w = period.split("-W")
            return pd.Timestamp.fromisocalendar(int(year), int(w), 1)
        if len(period) == 4:  # годишен
            return pd.Timestamp(year=int(period), month=1, day=1)
        # Monthly или daily — pandas се справя; NaT → None
        ts = pd.to_datetime(period, errors="coerce")
        return None if pd.isna(ts) else ts
    except (ValueError, AttributeError):
        return None


# ============================================================
# SDMX-JSON parser
# ============================================================

def parse_sdmx_json(payload: dict) -> pd.Series:
    """Парсва ECB SDMX-JSON 1.0 response → pd.Series.

    Очакваният формат:
      {
        "dataSets": [{"series": {"0:0:...": {"observations": {"0": [val, ...]}}}}],
        "structure": {"dimensions": {"observation": [{"values": [{"id": "2024-01"}, ...]}]}}
      }

    Връща празна pd.Series ако payload-ът няма данни.
    Raise-ва ValueError ако структурата е unexpected.
    """
    datasets = payload.get("dataSets") or []
    if not datasets:
        return pd.Series(dtype=float)

    ds = datasets[0]
    series_dict = ds.get("series") or {}
    if not series_dict:
        return pd.Series(dtype=float)

    # Намираме observation dimension (обикновено TIME_PERIOD)
    structure = payload.get("structure") or {}
    dims = (structure.get("dimensions") or {}).get("observation") or []
    if not dims:
        raise ValueError("ECB SDMX response: missing observation dimension")

    time_values = dims[0].get("values") or []
    period_strings = [v.get("id", "") for v in time_values]

    # Вземаме първата (и обикновено единствена) series — каталогът дефинира конкретен key
    first_series_key = next(iter(series_dict))
    observations = series_dict[first_series_key].get("observations") or {}

    if len(series_dict) > 1:
        logger.warning(
            f"ECB response has {len(series_dict)} series; expected 1 — "
            f"взимаме само първата ({first_series_key})"
        )

    data: dict[pd.Timestamp, float] = {}
    for obs_idx_str, obs_array in observations.items():
        try:
            idx = int(obs_idx_str)
            if idx >= len(period_strings):
                continue
            period = period_strings[idx]
            ts = parse_ecb_period(period)
            if ts is None:
                continue
            value = obs_array[0] if obs_array else None
            if value is None:
                continue
            data[ts] = float(value)
        except (ValueError, TypeError, IndexError) as e:
            logger.debug(f"Skip observation {obs_idx_str}: {e}")
            continue

    if not data:
        return pd.Series(dtype=float)

    s = pd.Series(data).sort_index()
    return s


# ============================================================
# EcbAdapter
# ============================================================

class EcbAdapter(BaseAdapter):
    """ECB Data Portal SDMX REST adapter."""

    SOURCE_NAME = "ecb"

    def __init__(
        self,
        base_url: str = "https://data-api.ecb.europa.eu/service",
        cache_path: str | Path = DEFAULT_CACHE_PATH,
        base_dir: Optional[Path] = None,
        retry_backoff: Optional[list[int]] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        super().__init__(cache_path=cache_path, base_dir=base_dir, retry_backoff=retry_backoff)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        })

    def _build_url(self, source_id: str) -> str:
        """source_id е "<flowref>/<key>", напр. "CISS/D.U2.Z0Z.4F.EC.SS_CIN.IDX"."""
        if "/" not in source_id:
            raise ValueError(
                f"ECB source_id трябва да е '<flowref>/<key>' формат — получено: '{source_id}'"
            )
        flowref, key = source_id.split("/", 1)
        return f"{self.base_url}/data/{flowref}/{key}?format=jsondata"

    def _fetch_remote(self, series_key: str, source_id: str) -> pd.Series:
        url = self._build_url(source_id)
        logger.debug(f"ECB GET {url}")
        try:
            response = self._session.get(url, timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"ECB HTTP error: {e}") from e

        if response.status_code == 404:
            raise ValueError(f"ECB 404 Not Found: {source_id}")
        if response.status_code >= 400:
            err = RuntimeError(
                f"ECB HTTP {response.status_code}: {response.text[:200]}"
            )
            err.status_code = response.status_code  # type: ignore[attr-defined]
            raise err

        try:
            payload = response.json()
        except ValueError as e:
            raise RuntimeError(f"ECB invalid JSON: {e}") from e

        return parse_sdmx_json(payload)
