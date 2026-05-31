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
        self._json_bridge: Optional[dict] = None

    def _load_json_bridge(self) -> dict:
        """Lazy-load на committed data/bloomberg_bridge.json — CI fallback когато
        private parquet архив не е достъпен (vrm-data-archive не е clone-нат)."""
        if self._json_bridge is not None:
            return self._json_bridge
        import json
        json_path = self.base_dir / "data" / "bloomberg_bridge.json"
        if not json_path.exists():
            self._json_bridge = {}
            return self._json_bridge
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            self._json_bridge = data.get("series", {})
        except Exception as e:
            logger.error(f"bloomberg_bridge.json read failed — {e}")
            self._json_bridge = {}
        return self._json_bridge

    def _series_from_json(self, catalog_key: str) -> pd.Series:
        rec = self._load_json_bridge().get(catalog_key)
        if not rec or not rec.get("dates"):
            return pd.Series(dtype=float)
        s = pd.Series(rec["values"], index=pd.to_datetime(rec["dates"]))
        s = s.sort_index()
        s.name = catalog_key
        return s

    def _resolve_path(self, parquet_path: str) -> Path:
        p = Path(parquet_path)
        if p.is_absolute():
            return p
        return (self.base_dir / parquet_path).resolve()

    def fetch(self, catalog_key: str, parquet_path: str) -> pd.Series:
        full = self._resolve_path(parquet_path)
        if full.exists():
            try:
                df = pd.read_parquet(full)
                if not df.empty and "date" in df.columns and "value" in df.columns:
                    # Latest as_of per date (point-in-time извън adapter-а)
                    df = df.sort_values(["date", "as_of"]).drop_duplicates(
                        subset=["date"], keep="last"
                    )
                    s = pd.Series(df["value"].values, index=pd.to_datetime(df["date"]))
                    s = s.sort_index()
                    s.name = catalog_key
                    return s
                logger.warning(f"{catalog_key}: parquet malformed → опит за JSON bridge")
            except Exception as e:
                logger.error(f"{catalog_key}: parquet read failed ({e}) → опит за JSON bridge")
        # parquet липсва/невалиден → committed JSON bridge (CI path, без private архив)
        s = self._series_from_json(catalog_key)
        if s.empty:
            logger.warning(f"{catalog_key}: нито parquet, нито JSON bridge налични.")
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
