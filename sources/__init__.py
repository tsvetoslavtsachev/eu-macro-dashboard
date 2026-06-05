"""sources — data source adapters + adapter registry."""
from __future__ import annotations


def build_adapters() -> dict:
    """Канонична карта source_name → adapter instance.

    Единственото място, където adapter-ите се регистрират. Викан от run.py и
    export_api.py — гарантира че всеки code path вижда ЕДНИ И СЪЩИ източници
    (иначе серия може тихо да липсва в един път, но не в друг).

    bloomberg_bridge се зарежда отделно (parquet/committed JSON в _build_snapshot),
    НЕ оттук.
    """
    from sources.ecb_adapter import EcbAdapter
    from sources.eurostat_adapter import EurostatAdapter
    from sources.sdmx_csv_adapter import SdmxCsvAdapter

    return {
        "ecb": EcbAdapter(),
        "eurostat": EurostatAdapter(),
        "oecd": SdmxCsvAdapter("data/oecd_cache.json", source_name="oecd"),
        "nbb": SdmxCsvAdapter("data/nbb_cache.json", source_name="nbb"),
    }
