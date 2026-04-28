"""
export/weekly_briefing.py
=========================
HTML weekly briefing renderer за Eurozone.

Phase 0: STUB. Phase 3 ще реализира HTML template-а (BG labels) по
образец на US `export/weekly_briefing.py`.

Очакван интерфейс:
  def generate_weekly_briefing(
      snapshot: dict[str, pd.Series],
      output_path: str,
      top_anomalies_n: int = 10,
      today: Optional[date] = None,
      state_dir: Optional[str] = "data/state",
      persist_state: bool = True,
      analog_bundle: Optional[AnalogBundle] = None,  # Phase 4
      journal_entries: Optional[list[Any]] = None,   # Phase 5
  ) -> str:                                          # path to generated HTML

Sections (BG-labelled, identical structure със US):
  1. Executive Summary — composite score + regime label (BG: "ЗДРАВ" etc.)
  2. Седмична делта (WoW)
  3. Cross-lens divergence (6 EA-specific pair-и)
  4. Non-consensus readings
  5. Аномалии (top 10)
  6. Свързани журнал бележки (опционално, с --with-journal)
  7. Footer — методология + revision_prone caveats

Self-contained HTML (inline CSS, no JS, без CDN).
"""
from __future__ import annotations
from datetime import date
from typing import Any, Optional

import pandas as pd


def generate_weekly_briefing(
    snapshot: dict[str, pd.Series],
    output_path: str,
    top_anomalies_n: int = 10,
    today: Optional[date] = None,
    state_dir: Optional[str] = "data/state",
    persist_state: bool = True,
    analog_bundle: Optional[Any] = None,
    journal_entries: Optional[list[Any]] = None,
) -> str:
    """Генерира HTML briefing на български. Phase 3 implementation."""
    raise NotImplementedError("export.weekly_briefing.generate_weekly_briefing — Phase 3")
