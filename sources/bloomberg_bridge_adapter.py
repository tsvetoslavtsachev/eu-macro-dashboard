"""
sources/bloomberg_bridge_adapter.py
====================================
Чете parquet файлове от private vrm-data-archive репо.

Mirror на US версията — виж us-macro-dashboard/sources/bloomberg_bridge_adapter.py
за пълен design doc + license disкусия.

Catalog usage:
    "EA_INFL_SWAP_5Y": {
        "source": "bloomberg_bridge",
        "parquet_path": "../../../vrm-data-archive/parquet/EA_INFL_SWAP_5Y.parquet",
        "license_class": "bloomberg_internal_use",
        ...
    }

Public CI render-ите трябва да минават `public_only=True` за skip на
bloomberg_internal_use серии.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)


class BloombergBridgeAdapter:
    """Чете Bloomberg-sourced parquet файлове от private архив."""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).parent.parent

    def _resolve_path(self, parquet_path: str) -> Path:
        p = Path(parquet_path)
        if p.is_absolute():
            return p
        return (self.base_dir / parquet_path).resolve()

    def fetch(self, catalog_key: str, parquet_path: str) -> pd.Series:
        full = self._resolve_path(parquet_path)
        if not full.exists():
            logger.warning(
                f"{catalog_key}: parquet не съществува на {full}. "
                "vrm-data-archive репо mounted/cloned?"
            )
            return pd.Series(dtype=float)
        try:
            df = pd.read_parquet(full)
        except Exception as e:
            logger.error(f"{catalog_key}: parquet read failed — {e}")
            return pd.Series(dtype=float)
        if df.empty or "date" not in df.columns or "value" not in df.columns:
            logger.warning(f"{catalog_key}: missing date/value or empty")
            return pd.Series(dtype=float)
        # Latest as_of per date (point-in-time извън adapter-а)
        df = df.sort_values(["date", "as_of"]).drop_duplicates(
            subset=["date"], keep="last"
        )
        s = pd.Series(df["value"].values, index=pd.to_datetime(df["date"]))
        s = s.sort_index()
        s.name = catalog_key
        return s

    def get_snapshot(
        self,
        catalog: dict[str, dict[str, Any]],
        public_only: bool = False,
    ) -> dict[str, pd.Series]:
        out: dict[str, pd.Series] = {}
        for key, meta in catalog.items():
            if meta.get("source") != "bloomberg_bridge":
                continue
            if public_only:
                lic = meta.get("license_class", "bloomberg_internal_use")
                if lic not in ("source_public", "derived_only"):
                    continue
            path = meta.get("parquet_path")
            if not path:
                logger.warning(f"{key}: missing parquet_path")
                continue
            s = self.fetch(key, path)
            if not s.empty:
                out[key] = s
        return out

    def get_cache_status(self, catalog_key: str, parquet_path: str) -> dict[str, Any]:
        s = self.fetch(catalog_key, parquet_path)
        if s.empty:
            return {
                "is_cached": False,
                "last_fetched": None,
                "last_observation": None,
                "n_observations": 0,
            }
        return {
            "is_cached": True,
            "last_fetched": None,
            "last_observation": s.index.max().strftime("%Y-%m-%d"),
            "n_observations": len(s),
        }
