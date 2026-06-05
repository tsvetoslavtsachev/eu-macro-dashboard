"""
sources/sdmx_csv_adapter.py
===========================
Generic SDMX-CSV REST adapter — OECD SDMX 2.1 + NBB .Stat (SDMX 2.1).

И двата източника връщат SDMX-CSV с колони TIME_PERIOD + OBS_VALUE. Понеже
URL структурите им се различават (OECD: `dataflow,key` + `?format=csvfile`;
NBB: `agency,flow,version/key/all` + Accept header), catalog `id` носи ЦЕЛИЯ
request URL — adapter-ът просто GET-ва source_id и парсва CSV-то.

Catalog usage:
  source="oecd" | "nbb", id="<full request URL>".

Response: SDMX-CSV 1.0 (semicolon? — не; OECD/NBB ползват comma). UTF-8 (OECD с BOM).
  Observation value → колона OBS_VALUE; период (YYYY-MM monthly) → TIME_PERIOD.

Cache:
  Отделен файл на източник (data/oecd_cache.json, data/nbb_cache.json).
  Adaptive TTL по release_schedule (виж sources/_base.py).
"""
from __future__ import annotations

import csv
import io
import logging
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from sources._base import BaseAdapter

logger = logging.getLogger(__name__)


# ============================================================
# CONFIG
# ============================================================

DEFAULT_TIMEOUT = 30  # секунди
USER_AGENT = "eu-macro-dashboard/0.1 (https://github.com/tsvetoslavtsachev/eu-macro-dashboard)"
# OECD keys off `?format=csvfile`; NBB keys off Accept header. Изпращаме и двете.
CSV_ACCEPT = "application/vnd.sdmx.data+csv;version=1.0.0, text/csv, */*"

TIME_COL = "TIME_PERIOD"
VALUE_COL = "OBS_VALUE"


# ============================================================
# SDMX-CSV parser
# ============================================================

def parse_sdmx_csv(raw: str, series_key: str = "") -> pd.Series:
    """SDMX-CSV текст → monthly pd.Series (DatetimeIndex, sorted).

    Очаква колони TIME_PERIOD (YYYY-MM) + OBS_VALUE. Пропуска празни стойности
    и периоди, които не се парсват. Ако response-ът съдържа >1 серия (повече от
    една стойност за период), raise-ва ValueError — caller-ите подават
    single-series URL. Връща празна Series ако няма observations.
    """
    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames:
        return pd.Series(dtype=float)

    cols = {c.strip().upper().lstrip("﻿"): c for c in reader.fieldnames}
    tcol = cols.get(TIME_COL)
    vcol = cols.get(VALUE_COL)
    if not tcol or not vcol:
        raise ValueError(
            f"{series_key}: SDMX-CSV липсват {TIME_COL}/{VALUE_COL}; колони={reader.fieldnames}"
        )

    data: dict[str, float] = {}
    for row in reader:
        t = (row.get(tcol) or "").strip()
        v = (row.get(vcol) or "").strip()
        if not t or v == "":
            continue
        try:
            val = float(v)
        except ValueError:
            continue
        if t in data:
            raise ValueError(
                f"{series_key}: дублиран период {t} — URL връща >1 серия "
                f"(подай single-series URL)"
            )
        data[t] = val

    if not data:
        return pd.Series(dtype=float)

    idx = pd.to_datetime(list(data.keys()), errors="coerce")
    s = pd.Series(list(data.values()), index=idx)
    s = s[~s.index.isna()]  # маха периоди, които не се парсват (NaT)
    return s.sort_index()


# ============================================================
# SdmxCsvAdapter
# ============================================================

class SdmxCsvAdapter(BaseAdapter):
    """Generic SDMX-CSV adapter (OECD, NBB). source_id = пълен request URL."""

    SOURCE_NAME = "sdmx_csv"

    def __init__(
        self,
        cache_path: str | Path,
        source_name: Optional[str] = None,
        base_dir: Optional[Path] = None,
        retry_backoff: Optional[list[int]] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        super().__init__(cache_path=cache_path, base_dir=base_dir, retry_backoff=retry_backoff)
        if source_name:
            self.SOURCE_NAME = source_name  # instance override (oecd / nbb)
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": CSV_ACCEPT,
            "User-Agent": USER_AGENT,
        })

    def _fetch_remote(self, series_key: str, source_id: str) -> pd.Series:
        if not source_id.lower().startswith("http"):
            raise ValueError(
                f"{self.SOURCE_NAME} source_id трябва да е пълен URL — получено: '{source_id[:60]}'"
            )
        logger.debug(f"{self.SOURCE_NAME} GET {source_id}")
        try:
            response = self._session.get(source_id, timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"{self.SOURCE_NAME} HTTP error: {e}") from e

        if response.status_code == 404:
            raise ValueError(f"{self.SOURCE_NAME} 404 Not Found: {source_id}")
        if response.status_code >= 400:
            err = RuntimeError(
                f"{self.SOURCE_NAME} HTTP {response.status_code}: {response.text[:200]}"
            )
            err.status_code = response.status_code  # type: ignore[attr-defined]
            raise err

        raw = response.content.decode("utf-8-sig")  # OECD CSV носи BOM
        return parse_sdmx_csv(raw, series_key)
