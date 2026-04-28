"""
modules/ecb.py
==============
ECB monetary policy stance lens — НОВ EA-specific lens (без US аналог).

Phase 0: STUB. Phase 2 ще реализира scoring логиката.

Защо отделен lens:
  ECB не е equivalent на Fed, който в US е разпиляван през няколко lens-а.
  В EA политическата трансмисия е по-крехка (банково-доминирана икономика,
  fragmentation между core/periphery), затова заслужава dedicated lens.

EA series planning (Phase 1 catalog):
  EA_DFR                 — ECB Deposit Facility Rate (ECB FM.D.U2.EUR.4F.KR.DFR.LEV)
  EA_MRO                 — ECB Main Refinancing Operations rate
  EA_MLF                 — ECB Marginal Lending Facility rate
  EA_BALANCE_SHEET       — ECB total assets (ECB BSI/PASR)
  EA_TLTRO_OUTSTANDING   — TLTRO outstanding (ECB MIR/STR datasets)
  EA_REAL_DFR            — derived: DFR − HICP core YoY (real rate proxy)
  EA_BUND_10Y            — Germany 10Y Bund yield (proxy за EA risk-free)
  EA_OIS_2Y              — 2Y OIS rate (market expectations)
  EA_BANK_LENDING_VOLUME — MFI loans to non-financial corporations (ECB BSI)

Composite logic (планиран):
  - Stance score: real DFR (negative=loose, positive=tight)
  - Balance sheet trend: 3m MoM (expanding=QE, shrinking=QT)
  - Transmission stress: BTP-Bund spread (по-широко=fragmented)
  - Forward path: OIS 2Y vs current DFR (market hike/cut expectations)

Pattern: огледало на US module structure (макар че няма US еквивалент за
ECB lens — pattern за `run(client) -> dict` остава същия).
"""
from __future__ import annotations


SERIES: dict[str, dict] = {
    # TODO Phase 2
}


def run(client) -> dict:
    """Изчислява ECB policy stance composite. Phase 2 implementation."""
    raise NotImplementedError("modules.ecb.run — Phase 2")
