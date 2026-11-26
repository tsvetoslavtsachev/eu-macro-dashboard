"""sources — data source adapters + adapter registry."""
from __future__ import annotations


def build_adapters() -> dict:
    """Канонична карта source_name → adapter instance.

    Единственото място, където adapter-ите се регистрират. Викан от run.py и
    export_api.py — гарантира че всеки code path вижда ЕДНИ И СЪЩИ източници
    (иначе серия може тихо да липсва в един път, но не в друг).

    bloomberg_bridge НЕ е тук. Зарежда се само в `run.py` (_build_snapshot там,
    62e8808); `export_api.py` (JSON-ите за светлините и блока) НЕ го зарежда, затова
    суаповете и CDS-ите не влизат в публикуваната оценка, а групата `sovereign_cds`
    е празна. Оставено така по решение на Ц. (ПРОЛЕТР4, ЕЗ-3, 26.11.2026): достъпът
    до Bloomberg е несигурен; описът е в `_orchestration/prolet/BLOOMBERG-MESECHNI-DANNI.md`.
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
