"""
modules/growth.py
=================
Growth lens за Eurozone.

Phase 0: STUB. Phase 2 ще реализира scoring логиката.

EA series planning (Phase 1 catalog):
  EA_GDP_QOQ             — Real GDP QoQ (Eurostat namq_10_gdp)
  EA_IP                  — Industrial production index (Eurostat sts_inpr_m)
  EA_RETAIL_TRADE        — Retail trade volume (Eurostat sts_trtu_m)
  EA_CONSTRUCTION        — Construction production index (Eurostat sts_copr_m)
  EA_BUILDING_PERMITS    — Building permits index (Eurostat sts_cobp_m)
  EA_ESI                 — Economic Sentiment Indicator (DG ECFIN ei_bsco_m)
  EA_CONSUMER_CONFIDENCE — DG ECFIN consumer subindex
  EA_INDUSTRY_CONFIDENCE — DG ECFIN industry subindex
  EA_NEW_ORDERS          — Manufacturing new orders (Eurostat sts_inno_m)

Pattern: огледало на US modules/growth.py.
ESI замества US ISM PMI (S&P Global PMI е платено).
"""
from __future__ import annotations


SERIES: dict[str, dict] = {
    # TODO Phase 2
}


def run(client) -> dict:
    """Изчислява Growth lens composite за EA. Phase 2 implementation."""
    raise NotImplementedError("modules.growth.run — Phase 2")
