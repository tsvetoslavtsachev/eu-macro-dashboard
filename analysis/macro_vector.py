"""
analysis/macro_vector.py
========================
8-dimensional macro state vector за Eurozone historical analog engine.

Дименсии (8):
  1. unrate                  — EA_UNRATE level (%) [Eurostat]
  2. core_hicp_yoy           — EA_HICP_CORE level (%) [вече YoY от Eurostat]
  3. real_dfr                — ECB_DFR − EA_HICP_CORE (real policy rate, %)
  4. yc_10y2y                — EA_BUND_10Y − EA_BUND_2Y (curve slope, pp)
  5. sovereign_stress        — IT_10Y − DE_10Y (BTP-Bund spread, pp; EA proxy за HY OAS)
  6. ip_yoy                  — EA_IP YoY (%, computed)
  7. sahm                    — Sahm rule (3mma EA_UNRATE − min trailing 12m 3mma, pp)
  8. inflation_expectations  — ECB SPF long-term HICP point forecast (%, quarterly,
                               forward-filled to monthly)

Window: 1999-01-01 → сега (~26 години EMU история).
Pre-1999 синтетика (GDP-weighted DM legacy currencies) умишлено пропусната —
твърде шумна за meaningful analog match.

Различия от US version:
  - real_ffr → real_dfr (ECB Deposit Facility Rate)
  - hy_oas → sovereign_stress (BTP-Bund proxy; iTraxx е платено)
  - breakeven (T10YIE) → SPF long-term inflation expectations (different methodology
    но similar role: market vs survey-based expectations anchor)
  - Без proxy splicing — историята започва 1999

Запазен интерфейс (за analog_matcher.py / analog_pipeline.py):
  STATE_VECTOR_DIMS, DIM_LABELS_BG, DIM_UNITS — public consts
  MacroState — dataclass с as_array()
  build_history_matrix, z_score_matrix, build_current_vector — public functions

Phase 4.5: 8-dim activated. SPF expectations (EA_SPF_HICP_LT) са quarterly
с lag (~end-quarter release); forward-filled до monthly за alignment с другите
dims. Анализаторът интерпретира dim 8 като "anchoring" signal — близо до 2%
target = anchored, > 0.5pp deviation = de-anchoring risk.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


# ─── Public constants ────────────────────────────────────────────

ANALOG_WINDOW_START = "1999-01-01"  # EMU era

STATE_VECTOR_DIMS: list[str] = [
    "unrate",
    "core_hicp_yoy",
    "real_dfr",
    "yc_10y2y",
    "sovereign_stress",
    "ip_yoy",
    "sahm",
    "inflation_expectations",
]

DIM_LABELS_BG: dict[str, str] = {
    "unrate":                 "Безработица (EA)",
    "core_hicp_yoy":          "HICP базова инфлация",
    "real_dfr":               "Реален DFR",
    "yc_10y2y":               "Крива 10Y-2Y",
    "sovereign_stress":       "Sovereign стрес (BTP-Bund)",
    "ip_yoy":                 "Промишлено производство YoY",
    "sahm":                   "Sahm правило",
    "inflation_expectations": "Inflation очаквания (SPF LT)",
}

DIM_UNITS: dict[str, str] = {
    "unrate":                 "%",
    "core_hicp_yoy":          "%",
    "real_dfr":               "%",
    "yc_10y2y":               "pp",
    "sovereign_stress":       "pp",
    "ip_yoy":                 "%",
    "sahm":                   "pp",
    "inflation_expectations": "%",
}


# ─── MacroState dataclass ─────────────────────────────────────────

@dataclass
class MacroState:
    """Snapshot на macro state в конкретна дата."""
    as_of: pd.Timestamp
    raw: dict[str, float] = field(default_factory=dict)
    z: dict[str, float] = field(default_factory=dict)

    def as_array(self) -> np.ndarray:
        """7-D z-score vector за cosine similarity."""
        return np.array([self.z.get(d, np.nan) for d in STATE_VECTOR_DIMS])

    def is_complete(self) -> bool:
        """True ако всички dimensions са set (не NaN)."""
        arr = self.as_array()
        return not np.any(np.isnan(arr))


# ─── Helper transforms ────────────────────────────────────────────

def _to_month_end(s: pd.Series) -> pd.Series:
    """Resample към month-start (period start convention)."""
    if s.empty:
        return s
    s = s.copy()
    if not isinstance(s.index, pd.DatetimeIndex):
        s.index = pd.to_datetime(s.index)
    # Resample to monthly using mean (за daily/weekly серии)
    return s.resample("MS").mean().dropna()


def _yoy_pct(s: pd.Series) -> pd.Series:
    """YoY процентна промяна (12-period diff на monthly серия)."""
    if s.empty:
        return s
    return s.pct_change(periods=12).dropna() * 100


def _compute_sahm_rule(unrate_monthly: pd.Series) -> pd.Series:
    """Sahm rule: 3-month moving average UNRATE минус trailing 12m min на 3mma.

    Стойност > 0.5 historically signals recession.
    """
    if len(unrate_monthly) < 15:
        return pd.Series(dtype=float)
    ma3 = unrate_monthly.rolling(window=3).mean()
    trailing_min = ma3.rolling(window=12).min()
    return (ma3 - trailing_min).dropna()


# ─── History matrix builder ───────────────────────────────────────

def build_history_matrix(
    snapshot: dict[str, pd.Series],
    window_start: str = ANALOG_WINDOW_START,
) -> pd.DataFrame:
    """От snapshot {series_key → pd.Series} построява monthly DataFrame
    с колоните = STATE_VECTOR_DIMS.

    Връща пуст DataFrame ако ключовите серии липсват.
    """
    required = {
        "EA_UNRATE", "EA_HICP_CORE", "ECB_DFR",
        "EA_BUND_10Y", "EA_BUND_2Y",
        "IT_10Y", "DE_10Y",
        "EA_IP",
        "EA_SPF_HICP_LT",  # quarterly, forward-filled to monthly за dim 8
    }
    missing = required - set(snapshot.keys())
    if missing:
        # Не raise-ваме — пускаме непълен matrix, downstream ще сигнализира
        pass

    cols: dict[str, pd.Series] = {}

    # Dim 1: unrate (level)
    if "EA_UNRATE" in snapshot:
        cols["unrate"] = _to_month_end(snapshot["EA_UNRATE"])

    # Dim 2: core_hicp_yoy (вече е YoY %)
    if "EA_HICP_CORE" in snapshot:
        cols["core_hicp_yoy"] = _to_month_end(snapshot["EA_HICP_CORE"])

    # Dim 3: real_dfr = DFR − core_hicp_yoy
    if "ECB_DFR" in snapshot and "EA_HICP_CORE" in snapshot:
        dfr_m = _to_month_end(snapshot["ECB_DFR"])
        core_m = _to_month_end(snapshot["EA_HICP_CORE"])
        idx_common = dfr_m.index.intersection(core_m.index)
        cols["real_dfr"] = (dfr_m.loc[idx_common] - core_m.loc[idx_common]).dropna()

    # Dim 4: yc_10y2y = 10Y - 2Y
    if "EA_BUND_10Y" in snapshot and "EA_BUND_2Y" in snapshot:
        y10 = _to_month_end(snapshot["EA_BUND_10Y"])
        y2 = _to_month_end(snapshot["EA_BUND_2Y"])
        idx_common = y10.index.intersection(y2.index)
        cols["yc_10y2y"] = (y10.loc[idx_common] - y2.loc[idx_common]).dropna()

    # Dim 5: sovereign_stress = IT_10Y - DE_10Y
    if "IT_10Y" in snapshot and "DE_10Y" in snapshot:
        it = _to_month_end(snapshot["IT_10Y"])
        de = _to_month_end(snapshot["DE_10Y"])
        idx_common = it.index.intersection(de.index)
        cols["sovereign_stress"] = (it.loc[idx_common] - de.loc[idx_common]).dropna()

    # Dim 6: ip_yoy
    if "EA_IP" in snapshot:
        ip_m = _to_month_end(snapshot["EA_IP"])
        cols["ip_yoy"] = _yoy_pct(ip_m)

    # Dim 7: sahm
    if "EA_UNRATE" in snapshot:
        unrate_m = _to_month_end(snapshot["EA_UNRATE"])
        cols["sahm"] = _compute_sahm_rule(unrate_m)

    # Dim 8: inflation_expectations (quarterly SPF → forward-filled monthly)
    if "EA_SPF_HICP_LT" in snapshot:
        spf = snapshot["EA_SPF_HICP_LT"].copy()
        if not spf.empty:
            if not isinstance(spf.index, pd.DatetimeIndex):
                spf.index = pd.to_datetime(spf.index)
            # Quarterly наблюдения с date = quarter-start; resample към monthly
            # с forward-fill (всеки месец наследява последния известен SPF).
            spf_monthly = spf.resample("MS").ffill()
            cols["inflation_expectations"] = spf_monthly

    if not cols:
        return pd.DataFrame(columns=STATE_VECTOR_DIMS)

    df = pd.DataFrame(cols)
    df = df.reindex(columns=STATE_VECTOR_DIMS)  # стабилен column order
    df = df[df.index >= pd.Timestamp(window_start)]
    return df


def z_score_matrix(history_df: pd.DataFrame) -> pd.DataFrame:
    """Z-score всяка колонка спрямо собствената history."""
    if history_df.empty:
        return history_df

    z = pd.DataFrame(index=history_df.index, columns=history_df.columns, dtype=float)
    for col in history_df.columns:
        s = history_df[col].dropna()
        if len(s) < 2 or s.std() == 0:
            z[col] = 0.0
        else:
            mean = s.mean()
            std = s.std()
            z[col] = (history_df[col] - mean) / std
    return z


def build_current_vector(
    history_df: pd.DataFrame,
    z_df: Optional[pd.DataFrame] = None,
    today: Optional[pd.Timestamp] = None,
) -> Optional[MacroState]:
    """Връща MacroState за последния complete-case observation в history_df.

    Args:
        history_df: history matrix (от build_history_matrix)
        z_df: precomputed z-score matrix; ако None, изчислява го
        today: cut-off дата (default = последната налична)

    Returns:
        MacroState с raw + z за последния complete-case ред,
        или None ако няма complete-case ред (всички dims must be present).
    """
    if history_df.empty:
        return None

    if z_df is None:
        z_df = z_score_matrix(history_df)

    df = history_df
    if today is not None:
        df = df[df.index <= today]
        if df.empty:
            return None

    # Намираме последния complete-case ред (всички STATE_VECTOR_DIMS налични)
    available_dims = [d for d in STATE_VECTOR_DIMS if d in df.columns]
    if not available_dims:
        return None

    complete_mask = df[available_dims].notna().all(axis=1)
    if not complete_mask.any():
        return None

    last_complete_idx = df[complete_mask].index[-1]

    last_row = df.loc[last_complete_idx]
    last_z_row = z_df.loc[last_complete_idx] if last_complete_idx in z_df.index else None
    if last_z_row is None:
        return None

    raw = {
        col: float(last_row[col])
        for col in STATE_VECTOR_DIMS
        if col in last_row.index and pd.notna(last_row[col])
    }
    z = {
        col: float(last_z_row[col])
        for col in STATE_VECTOR_DIMS
        if col in last_z_row.index and pd.notna(last_z_row[col])
    }

    return MacroState(as_of=last_complete_idx, raw=raw, z=z)
