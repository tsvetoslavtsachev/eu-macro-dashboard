"""
modules/inflation.py
====================
Inflation lens за Eurozone.

Phase 0: STUB. Phase 2 ще реализира scoring логиката.

EA series planning (Phase 1 catalog):
  EA_HICP_HEADLINE       — HICP all items YoY (Eurostat prc_hicp_manr)
  EA_HICP_CORE           — HICP excl energy & food YoY (Eurostat prc_hicp_manr subset)
  EA_HICP_SERVICES       — HICP services component YoY
  EA_HICP_GOODS          — HICP non-energy industrial goods YoY
  EA_HICP_ENERGY         — HICP energy YoY (volatile, separate)
  EA_INFLATION_SWAPS_5Y5Y — ECB 5Y5Y inflation swap rate (forward expectations)
  EA_SPF_INFLATION_2Y    — ECB Survey of Professional Forecasters 2Y expectation
  EA_PPI                 — Producer prices (Eurostat sts_inppd_m)
  EA_NEGOTIATED_WAGES_YOY — ECB indicator (двойно tagged: labor + inflation)

Pattern: огледало на US modules/inflation.py.
"""
from __future__ import annotations


SERIES: dict[str, dict] = {
    # TODO Phase 2
}


def run(client) -> dict:
    """Изчислява Inflation lens composite за EA. Phase 2 implementation."""
    raise NotImplementedError("modules.inflation.run — Phase 2")
