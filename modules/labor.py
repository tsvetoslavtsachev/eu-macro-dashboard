"""
modules/labor.py
================
Labor market lens за Eurozone.

Phase 0: STUB. Phase 2 ще реализира scoring логиката.

Pattern (от US `modules/labor.py`):
  SERIES = {key: {label, invert}, ...}    # серии за оценка
  CYCLICAL_SERIES = [keys ...]            # подмножество за cyclical composite
  CYCLICAL_WEIGHTS = [floats ...]         # weights суммат до 1.0
  REGIMES = [(threshold, label_bg, color), ...]

  def run(client) -> dict:
      # Връща unified shape:
      # {
      #   "module": "labor",
      #   "label": "Пазар на труда",
      #   "icon": "👷",
      #   "scores": {sub_score_key: {"score": float, "label": str}},
      #   "composite": float,                  # 0–100
      #   "regime": str,                       # BG label
      #   "regime_color": str,                 # hex
      #   "indicators": {series_key: {"score": ...}},
      #   "key_readings": [bullet str, ...],
      # }

EA series planning (Phase 1 catalog):
  EA_UNRATE              — Unemployment rate (Eurostat une_rt_m), invert=True
  EA_LFS_EMPLOYMENT      — Employment level (Eurostat lfsi_emp_q), invert=False
  EA_JOB_VACANCIES       — Job vacancy rate (Eurostat jvs_q_nace2), invert=False
  EA_NEGOTIATED_WAGES    — ECB negotiated wage indicator (ECB SDW), invert=False
  EA_LABOUR_COST_INDEX   — Eurostat lc_lci_lev, invert=False
  EA_HOURS_WORKED        — Eurostat namq_10_a10_e, invert=False

Серии с НЯМА US аналог (skip):
  ICSA / initial claims — EA няма unified weekly federal benefit signal
  JTSQUR / quits rate   — EA няма еквивалент (търси Job Vacancy Rate като proxy)
"""
from __future__ import annotations


SERIES: dict[str, dict] = {
    # TODO Phase 2: попълни след catalog/series.py
}


def run(client) -> dict:
    """Изчислява Labor lens compositе за EA. Phase 2 implementation."""
    raise NotImplementedError("modules.labor.run — Phase 2")
