"""
sources/eurostat_adapter.py
===========================
Eurostat REST API adapter.

Phase 0: STUB. Phase 1 ще реализира пълния fetch+cache+retry pipeline.

API endpoint (без autenticija):
  https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}
  ?format=JSON&...filters

Примерни datasets:
  une_rt_m         — Unemployment rate, monthly
  prc_hicp_manr    — HICP all-items annual rate
  sts_inpr_m       — Industrial production index
  sts_trtu_m       — Retail trade volume
  sts_cobp_m       — Building permits
  ei_bsco_m        — Economic Sentiment Indicator (DG ECFIN consumer)
  lfsi_emp_q       — Employment (Labour Force Survey, quarterly)

Очакван интерфейс (същият като EcbAdapter):
  class EurostatAdapter:
      def __init__(self, cache_path="data/eurostat_cache.json", base_dir=None,
                   retry_backoff=None) -> None
      def fetch(series_key, eurostat_id, release_schedule, force=False) -> pd.Series
      def fetch_many(series_specs, force=False) -> dict[str, pd.Series]
      def save_cache() -> None

Cache: JSON файл `data/eurostat_cache.json`, същия shape като ECB.

Бележка: Eurostat серии могат да изискват filter параметри (geo=EA19, unit=PC,
sex=T, etc.). Catalog-ът ще съдържа filter dict-а в `id` или отделно поле.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, Optional

import pandas as pd


class EurostatAdapter:
    """Eurostat REST adapter. Phase 1 ще реализира тялото."""

    def __init__(
        self,
        cache_path: str = "data/eurostat_cache.json",
        base_dir: Optional[Path] = None,
        retry_backoff: Optional[list[int]] = None,
    ) -> None:
        self.cache_path = cache_path
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()
        self.retry_backoff = retry_backoff or [2, 5, 15]

    def fetch(
        self,
        series_key: str,
        eurostat_id: str,
        release_schedule: str,
        force: bool = False,
    ) -> pd.Series:
        """Fetch единична серия от Eurostat. Phase 1 implementation."""
        raise NotImplementedError("EurostatAdapter.fetch — Phase 1")

    def fetch_many(
        self,
        series_specs: list[dict[str, Any]],
        force: bool = False,
    ) -> dict[str, pd.Series]:
        """Fetch множество серии. Phase 1 implementation."""
        raise NotImplementedError("EurostatAdapter.fetch_many — Phase 1")

    def save_cache(self) -> None:
        """Persist кеша към disk. Phase 1 implementation."""
        raise NotImplementedError("EurostatAdapter.save_cache — Phase 1")
