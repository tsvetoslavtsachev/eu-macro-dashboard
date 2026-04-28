"""
sources/ecb_adapter.py
======================
ECB Statistical Data Warehouse (SDW) REST adapter.

Phase 0: STUB. Phase 1 ще реализира пълния fetch+cache+retry pipeline
по образец на US `sources/fred_adapter.py`.

API endpoint (без autenticija):
  https://data-api.ecb.europa.eu/service/data/{flowref}/{key}?format=jsondata

Примерни flowref-и:
  CISS  — Composite Indicator of Systemic Stress
  FM    — Financial Market data (rates, yields)
  IRS   — Long-term interest rate statistics
  BSI   — Balance Sheet Items (M3, lending)
  EXR   — Exchange Rates

Очакван интерфейс (огледало на FredAdapter):
  class EcbAdapter:
      def __init__(self, cache_path="data/ecb_cache.json", base_dir=None,
                   retry_backoff=None) -> None
      def fetch(series_key, ecb_id, release_schedule, force=False) -> pd.Series
      def fetch_many(series_specs, force=False) -> dict[str, pd.Series]
      def save_cache() -> None
      def find_stale_specs(specs) -> list[dict]
      def get_cache_status(series_key) -> dict
      def get_snapshot(series_keys) -> dict[str, pd.Series]
      def invalidate(series_key) -> None
      def last_fetch_failures() -> list[str]

Cache:
  JSON file `data/ecb_cache.json` със същия shape като FRED cache:
    {series_key: {"ecb_id": ..., "schedule": ..., "last_fetched": ISO,
                  "data": [{"date": "YYYY-MM-DD", "value": float}, ...]}}

Retry:
  3 retries with backoffs [2s, 5s, 15s] (от config.CACHE_TTL_HOURS_DEFAULT
  и адаптивен TTL по schedule).
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, Optional

import pandas as pd


class EcbAdapter:
    """ECB SDW REST adapter. Phase 1 ще реализира тялото."""

    def __init__(
        self,
        cache_path: str = "data/ecb_cache.json",
        base_dir: Optional[Path] = None,
        retry_backoff: Optional[list[int]] = None,
    ) -> None:
        self.cache_path = cache_path
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()
        self.retry_backoff = retry_backoff or [2, 5, 15]
        # TODO Phase 1: load cache, init session

    def fetch(
        self,
        series_key: str,
        ecb_id: str,
        release_schedule: str,
        force: bool = False,
    ) -> pd.Series:
        """Fetch единична серия от ECB SDW. Phase 1 implementation."""
        raise NotImplementedError("EcbAdapter.fetch — Phase 1")

    def fetch_many(
        self,
        series_specs: list[dict[str, Any]],
        force: bool = False,
    ) -> dict[str, pd.Series]:
        """Fetch множество серии. Phase 1 implementation."""
        raise NotImplementedError("EcbAdapter.fetch_many — Phase 1")

    def save_cache(self) -> None:
        """Persist кеша към disk. Phase 1 implementation."""
        raise NotImplementedError("EcbAdapter.save_cache — Phase 1")
