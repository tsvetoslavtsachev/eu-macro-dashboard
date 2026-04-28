"""
sources/eurostat_adapter.py
===========================
Eurostat REST API adapter (JSON-stat 2.0 format).

API endpoint (без autenticija):
  {base}/data/{dataset}?{filters}

  base    = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0"
  dataset = Eurostat dataset code (une_rt_m, prc_hicp_manr, sts_inpr_m, ...)
  filters = query string limiting dimensions (geo=EA20, unit=PC, ...)

Catalog usage:
  Series-ите имат source="eurostat" и id="<dataset>?<filter_string>", напр.
  "une_rt_m?geo=EA20&unit=PC_ACT&sex=T&age=TOTAL&s_adj=SA". Adapter-ът
  split-ва на първото '?'.

  Filter values са КРИТИЧНИ — ако пропуснем filter за някоя dimension,
  Eurostat връща dataset с няколко серии (multi-cell). Catalog-ът трябва
  да дефинира filter за всяка dimension с >1 value (освен time).

Response: JSON-stat 2.0
  Документация: https://ec.europa.eu/eurostat/web/json-and-unicode-web-services

Cache:
  Файл `data/eurostat_cache.json`. Adaptive TTL по release_schedule.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import requests

from sources._base import BaseAdapter

logger = logging.getLogger(__name__)


DEFAULT_CACHE_PATH = "data/eurostat_cache.json"
DEFAULT_TIMEOUT = 30
USER_AGENT = "eu-macro-dashboard/0.1 (https://github.com/tsvetoslavtsachev/eu-macro-dashboard)"


# ============================================================
# Период parsing — Eurostat-специфични формати
# ============================================================

# Eurostat ползва два варианта на period strings: с "M/Q/W" разделител или
# с тире. Поддържаме и двата.
_MONTHLY_M_RE = re.compile(r"^(\d{4})M(\d{2})$")            # "2024M01"
_MONTHLY_DASH_RE = re.compile(r"^(\d{4})-(\d{2})$")         # "2024-01"
_QUARTERLY_Q_RE = re.compile(r"^(\d{4})Q([1-4])$")          # "2024Q1"
_QUARTERLY_DASH_RE = re.compile(r"^(\d{4})-Q([1-4])$")      # "2024-Q1"
_ANNUAL_RE = re.compile(r"^(\d{4})$")                       # "2024"
_WEEKLY_W_RE = re.compile(r"^(\d{4})W(\d{2})$")             # "2024W01"
_WEEKLY_DASH_RE = re.compile(r"^(\d{4})-W(\d{2})$")         # "2024-W01"
_DAILY_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")        # "2024-01-15"


def parse_eurostat_period(period: str) -> Optional[pd.Timestamp]:
    """Парсва Eurostat period string на pd.Timestamp (period start).

    Поддържа monthly, quarterly, annually, weekly, daily — във всеки от
    "M/Q/W" и "-" разделени варианти, които Eurostat използва според
    dataset-а.
    """
    period = period.strip()

    # Daily проверяваме ПЪРВО (4-2-2) преди monthly dash (4-2), за да не
    # се сбърка YYYY-MM-DD с YYYY-MM.
    if _DAILY_RE.match(period):
        try:
            return pd.to_datetime(period)
        except ValueError:
            return None

    if m := _MONTHLY_M_RE.match(period):
        year, month = int(m.group(1)), int(m.group(2))
        return pd.Timestamp(year=year, month=month, day=1)

    if m := _MONTHLY_DASH_RE.match(period):
        year, month = int(m.group(1)), int(m.group(2))
        return pd.Timestamp(year=year, month=month, day=1)

    if m := _QUARTERLY_Q_RE.match(period) or _QUARTERLY_DASH_RE.match(period):
        year, q = int(m.group(1)), int(m.group(2))
        return pd.Timestamp(year=year, month=(q - 1) * 3 + 1, day=1)

    if m := _ANNUAL_RE.match(period):
        return pd.Timestamp(year=int(m.group(1)), month=1, day=1)

    if m := _WEEKLY_W_RE.match(period) or _WEEKLY_DASH_RE.match(period):
        year, w = int(m.group(1)), int(m.group(2))
        try:
            return pd.Timestamp.fromisocalendar(year, w, 1)
        except (ValueError, AttributeError):
            return None

    return None


# ============================================================
# JSON-stat 2.0 parser
# ============================================================

def parse_jsonstat(payload: dict) -> pd.Series:
    """Парсва Eurostat JSON-stat 2.0 → pd.Series (time-indexed).

    Очакваме single time series (всички non-time dimensions filter-нати към
    single value). Ако payload-ът съдържа multi-cell, взимаме секцията
    индексирана по time dimension и хвърляме warning ако има множествени
    стойности за non-time dimension.

    Format:
      {
        "id": ["geo", "unit", ..., "time"],
        "size": [1, 1, ..., N_time],
        "value": {"0": 8.1, "1": 8.2, ...},
        "dimension": {"time": {"category": {"index": {"2024M01": 0, ...}}}}
      }
    """
    if not payload or "dimension" not in payload:
        return pd.Series(dtype=float)

    dim_ids = payload.get("id") or []
    if "time" not in dim_ids:
        raise ValueError("Eurostat response missing 'time' dimension")

    time_idx = dim_ids.index("time")
    sizes = payload.get("size") or []

    # Проверяваме че всички non-time dimensions са с size=1 (filter-нати)
    multi_dims = [
        (dim_ids[i], sizes[i]) for i in range(len(dim_ids))
        if i != time_idx and sizes[i] > 1
    ]
    if multi_dims:
        logger.warning(
            f"Eurostat response има non-singular non-time dimensions: {multi_dims}. "
            f"Catalog-ът трябва да добави filters за тези. Взимам първите indexes."
        )

    time_dim = (payload.get("dimension") or {}).get("time") or {}
    period_index_map: dict[str, int] = (
        ((time_dim.get("category") or {}).get("index") or {})
    )
    if not period_index_map:
        return pd.Series(dtype=float)

    # invert: index → period string
    inverted: dict[int, str] = {idx: period for period, idx in period_index_map.items()}

    values_dict = payload.get("value") or {}

    # Computing the flat-index pattern: за single-value non-time dims,
    # the flat index за time index `t` е just `t` (всички други indexes са 0).
    # Това важи само ако time е last dimension (default за Eurostat).
    if time_idx != len(dim_ids) - 1:
        logger.warning(
            f"Eurostat response: time dimension не е последната ({time_idx} vs {len(dim_ids)-1}). "
            f"Parsing може да е неточен."
        )

    data: dict[pd.Timestamp, float] = {}
    for flat_idx_str, value in values_dict.items():
        try:
            flat_idx = int(flat_idx_str)
        except ValueError:
            continue
        if value is None:
            continue
        # Time е последната dim → time_index = flat_idx % size_of_time
        time_size = sizes[time_idx] if time_idx < len(sizes) else 0
        if time_size <= 0:
            continue
        time_index = flat_idx % time_size
        period = inverted.get(time_index)
        if not period:
            continue
        ts = parse_eurostat_period(period)
        if ts is None:
            continue
        try:
            data[ts] = float(value)
        except (ValueError, TypeError):
            continue

    if not data:
        return pd.Series(dtype=float)

    return pd.Series(data).sort_index()


# ============================================================
# EurostatAdapter
# ============================================================

class EurostatAdapter(BaseAdapter):
    """Eurostat REST API adapter."""

    SOURCE_NAME = "eurostat"

    def __init__(
        self,
        base_url: str = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0",
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
        """source_id е "<dataset>?<filter_string>" или просто "<dataset>"."""
        if "?" in source_id:
            dataset, filters = source_id.split("?", 1)
        else:
            dataset, filters = source_id, ""
        url = f"{self.base_url}/data/{dataset}?format=JSON"
        if filters:
            url += f"&{filters}"
        return url

    def _fetch_remote(self, series_key: str, source_id: str) -> pd.Series:
        url = self._build_url(source_id)
        logger.debug(f"Eurostat GET {url}")
        try:
            response = self._session.get(url, timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Eurostat HTTP error: {e}") from e

        if response.status_code == 404:
            raise ValueError(f"Eurostat 404 Not Found: {source_id}")
        if response.status_code >= 400:
            err = RuntimeError(
                f"Eurostat HTTP {response.status_code}: {response.text[:200]}"
            )
            err.status_code = response.status_code  # type: ignore[attr-defined]
            raise err

        try:
            payload = response.json()
        except ValueError as e:
            raise RuntimeError(f"Eurostat invalid JSON: {e}") from e

        return parse_jsonstat(payload)
