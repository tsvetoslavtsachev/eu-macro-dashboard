"""
export/briefing_context.py
==========================
Markdown export за LLM analysis — Eurozone версия (US-style structure).

Generates Claude-friendly briefing context като .md файл с пълния analytical
state. Без composite scores — фокус върху breadth + direction + аномалии,
по същата шаблон като us-macro-dashboard.

Sections:
  1. Header — дата, theme count, cross-lens count, anomaly count
  2. Executive Summary — table: тема | посока | breadth ↑ | аномалии
  1.5. Cross-spreads и реални нива — derived metrics (real DFR forward,
       real wages, real M3, yield curve, sovereign spreads, anchored band,
       PPI→CPI pipeline)
  3. Темите по peer group — за всяка тема: peer_group breadth tables
  4. Cross-Lens Divergence — 6 двойки с 5-state interpretation list
  5. Top Anomalies (fact cards) — серии с |z|>2 + full metadata
  6. Методология (compact)

Inputs:
  - snapshot: dict[sid, pd.Series]
  - lens_reports: dict[lens, LensBreadthReport]
  - cross_report: CrossLensDivergenceReport
  - anomaly_report: AnomalyReport

Output: output/briefing_context_YYYY-MM-DD.md
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import math
import numpy as np
import pandas as pd

from catalog.series import SERIES_CATALOG
from catalog.cross_lens_pairs import CROSS_LENS_PAIRS
from config import (
    ANCHORED_ZONES,
    NOMINAL_SERIES_NEED_DEFLATION,
    CORE_DEFLATOR_KEY,
    POLICY_RATE_KEY,
    FORWARD_INFL_KEY,
    NOMINAL_10Y_KEY,
    NOMINAL_2Y_KEY,
)
from core.display import change_kind, compute_change, fmt_change, fmt_value
from core.primitives import _infer_yoy_periods
from export.data_status import (
    PERIOD_LENGTH_DAYS,
    RELEASE_LAG_DAYS,
    assess_data_staleness,
)


# ============================================================
# CONFIG
# ============================================================

HISTORY_YEARS = 5
FACT_CARD_TAIL = 6
LENS_ORDER = ["labor", "inflation", "growth", "credit", "ecb"]

LENS_LABEL_BG = {
    "labor":     "Пазар на труда",
    "inflation": "Инфлация",
    "growth":    "Растеж и активност",
    "credit":    "Финансови условия и кредит",
    "ecb":       "ЕЦБ парична политика",
}
DIRECTION_LABEL_BG = {
    "expanding":         "разширяване",
    "contracting":       "свиване",
    "mixed":             "смесено",
    "insufficient_data": "недостатъчно данни",
}
STATE_LABEL_BG = {
    "both_up":           "↑↑ и двете нагоре",
    "both_down":         "↓↓ и двете надолу",
    "a_up_b_down":       "↑↓ A нагоре / B надолу",
    "a_down_b_up":       "↓↑ A надолу / B нагоре",
    "transition":        "⇄ преход",
    "insufficient_data": "недостатъчно данни",
}


# ============================================================
# DERIVED SNAPSHOT (BTP-Bund, OAT-Bund spreads)
# ============================================================

def augment_snapshot_with_derived(snapshot: dict[str, pd.Series]) -> dict[str, pd.Series]:
    """Adds derived spread series — same logic като modules.credit без circular import."""
    augmented = dict(snapshot)
    de = augmented.get("DE_10Y")
    if de is None or de.empty:
        return augmented

    it = augmented.get("IT_10Y")
    if it is not None and not it.empty:
        spread = (it - de).dropna()
        if not spread.empty:
            augmented["EA_BTP_BUND_SPREAD"] = spread

    fr = augmented.get("FR_10Y")
    if fr is not None and not fr.empty:
        spread = (fr - de).dropna()
        if not spread.empty:
            augmented["EA_OAT_BUND_SPREAD"] = spread

    return augmented


# ============================================================
# COMPUTATIONAL HELPERS
# ============================================================

def _last_value(series: Optional[pd.Series]) -> Optional[float]:
    if series is None or series.empty:
        return None
    s = series.dropna()
    if s.empty:
        return None
    return float(s.iloc[-1])


def _last_obs_date(series: Optional[pd.Series]) -> Optional[date]:
    if series is None or series.empty:
        return None
    s = series.dropna()
    if s.empty:
        return None
    last = s.index[-1]
    return last.date() if hasattr(last, "date") else None


def _yoy_pct(series: Optional[pd.Series], periods: Optional[int] = None) -> Optional[float]:
    """YoY % за последното observation. Auto-inferra periods (12 monthly, 4 quarterly)."""
    if series is None or series.empty:
        return None
    s = series.dropna()
    if len(s) < 2:
        return None
    if periods is None:
        periods = _infer_yoy_periods(s)
    if len(s) <= periods:
        return None
    pct = s.pct_change(periods=periods) * 100
    last = pct.iloc[-1]
    if pd.isna(last):
        return None
    return float(last)


def _annualized_change(series: Optional[pd.Series], periods: int = 3) -> Optional[float]:
    """N-period change annualized."""
    if series is None or series.empty:
        return None
    s = series.dropna()
    if len(s) <= periods:
        return None
    cumulative = s.iloc[-1] / s.iloc[-1 - periods] - 1
    inferred = _infer_yoy_periods(s)
    if inferred <= 0:
        return None
    annualization_factor = inferred / periods
    return float(((1 + cumulative) ** annualization_factor - 1) * 100)


def _percentile_5y(series: Optional[pd.Series], history_years: int = 5) -> Optional[float]:
    if series is None or series.empty:
        return None
    s = series.dropna().sort_index()
    if len(s) < 2:
        return None
    last_idx = s.index[-1]
    cutoff = last_idx - pd.DateOffset(years=history_years)
    s5y = s[s.index >= cutoff]
    if len(s5y) < 2:
        return None
    last_value = float(s5y.iloc[-1])
    return float((s5y < last_value).sum() / len(s5y) * 100)


def _staleness_marker(level: str) -> str:
    return {
        "FRESH":      "",
        "EXPECTED":   "",
        "DATA_STALE": "❌ ",
        "UNKNOWN":    "(няма данни) ",
    }.get(level, "")


# ============================================================
# SECTION 1: HEADER
# ============================================================

def _render_header(today: date, lens_reports: dict, cross_report, anomaly_report) -> str:
    lines = [
        f"# Briefing Context — {today.isoformat()}",
        "",
        "Машинно-генериран **дълбок** analytical snapshot за LLM анализ. "
        "Подава всичкото което briefing.html-ът показва, плюс per-series fact cards "
        f"с {HISTORY_YEARS}-годишен исторически контекст.",
        "",
        "**Как да го ползваш:** копирай съдържанието или закачи файла в Claude чат "
        "и питай дълбоки въпроси за серии, темите или текущите аномалии. "
        "Всичко е детерминистично, без LLM нарация — само изчислени стойности.",
        "",
        "**Регион:** Eurozone (EA-20). **Източници:** ECB SDW + Eurostat REST.",
        "",
        f"- **Дата на брифинга:** {today.isoformat()}",
        f"- **Брой теми:** {len(lens_reports)}",
        f"- **Cross-lens двойки:** {len(cross_report.pairs)}",
        f"- **Аномалии (|z|>{anomaly_report.threshold:.0f}):** {anomaly_report.total_flagged} (top {len(anomaly_report.top)})",
    ]
    return "\n".join(lines)


# ============================================================
# SECTION 1: EXECUTIVE SUMMARY
# ============================================================

def _render_executive_summary(lens_reports: dict, anomaly_report) -> str:
    lines = ["## 1. Executive Summary", ""]
    lines.append("| Тема | Посока (general) | Breadth ↑ (avg) | Аномалии (|z|>2) |")
    lines.append("|---|---|---|---|")

    for lens in LENS_ORDER:
        rep = lens_reports.get(lens)
        if rep is None:
            continue
        breadths = [
            pg.breadth_positive for pg in rep.peer_groups
            if not (isinstance(pg.breadth_positive, float) and math.isnan(pg.breadth_positive))
        ]
        avg_breadth = (sum(breadths) / len(breadths)) if breadths else None
        avg_str = f"{avg_breadth*100:.0f}%" if avg_breadth is not None else "—"

        dir_counts = {"expanding": 0, "contracting": 0, "mixed": 0, "insufficient_data": 0}
        for pg in rep.peer_groups:
            dir_counts[pg.direction] = dir_counts.get(pg.direction, 0) + 1
        if dir_counts["expanding"] > dir_counts["contracting"]:
            general = "разширяване"
        elif dir_counts["contracting"] > dir_counts["expanding"]:
            general = "свиване"
        else:
            general = "смесено"

        n_anom = len(anomaly_report.by_lens.get(lens, []))
        lines.append(f"| {LENS_LABEL_BG.get(lens, lens)} | {general} | {avg_str} | {n_anom} |")
    return "\n".join(lines)


# ============================================================
# SECTION 1.5: CROSS-SPREADS И РЕАЛНИ НИВА (EA-specific)
# ============================================================

def _render_cross_spreads(snapshot: dict[str, pd.Series], today: date, history_years: int) -> str:
    """EU cross-spreads: real DFR forward, real wages/M3/lending, curve, sovereign spreads,
    anchored band, PPI→CPI pipeline."""
    parts = ["## 1.5 Cross-spreads и реални нива", ""]
    parts.append(
        "Производни числа за директно използване в теза. **Deflator: HICP Core** "
        f"(`{CORE_DEFLATOR_KEY}` YoY) — ЕЦБ-preferred underlying inflation. "
        f"**Real DFR forward** = `{POLICY_RATE_KEY}` − `{FORWARD_INFL_KEY}` "
        "(ECB SPF long-term). Тези числа НЕ са в каталога — изчислени са тук от налични серии."
    )
    parts.append("")

    # ─── Core HICP YoY (deflator) ───
    # EA_HICP_CORE has transform=level (RCH_A is already YoY%) → just take last value
    core_hicp_yoy = _last_value(snapshot.get(CORE_DEFLATOR_KEY))

    # ═══════════════════════════════════════
    # Реални нива
    # ═══════════════════════════════════════
    parts.append("### Реални нива")
    parts.append("")

    if core_hicp_yoy is None:
        parts.append("_HICP Core липсва — реалните нива не могат да се изчислят._")
        parts.append("")
    else:
        parts.append(
            f"_HICP Core (`{CORE_DEFLATOR_KEY}`) YoY = **{core_hicp_yoy:+.2f}%** — "
            f"използва се като deflator._"
        )
        parts.append("")
        parts.append("| Метрика | Стойност | Интерпретация |")
        parts.append("|---|---|---|")

        # Real wages (compensation per employee — quarterly, periods=4 за raw level)
        comp = snapshot.get("EA_COMP_PER_EMPLOYEE")
        if comp is not None and not comp.empty:
            comp_yoy = _yoy_pct(comp, periods=4)  # quarterly
            if comp_yoy is not None:
                real = comp_yoy - core_hicp_yoy
                interp = (
                    "workers winning (real wage growth)" if real > 0.5 else
                    "workers losing (real wages contract)" if real < -0.3 else
                    "essentially flat — реално workers не печелят"
                )
                parts.append(
                    f"| Real wages (compensation Q-o-Q ann.) | "
                    f"{real:+.2f}% (nominal {comp_yoy:+.2f}% − HICP core {core_hicp_yoy:+.2f}%) | {interp} |"
                )

        # Real DFR forward (ECB_DFR − SPF LT)
        dfr_now = _last_value(snapshot.get(POLICY_RATE_KEY))
        spf_lt = _last_value(snapshot.get(FORWARD_INFL_KEY))
        if dfr_now is not None and spf_lt is not None:
            real_dfr = dfr_now - spf_lt
            interp = (
                "**clearly restrictive**" if real_dfr > 1.5 else
                "moderately restrictive" if real_dfr > 0.5 else
                "near neutral" if real_dfr > -0.5 else
                "stimulative"
            )
            parts.append(
                f"| **Real DFR (forward)** | "
                f"{real_dfr:+.2f}% ({real_dfr*100:+.0f} bps) "
                f"= DFR {dfr_now:.2f}% − SPF LT {spf_lt:.2f}% | {interp} |"
            )

        # Real M3 (M3_YOY is already YoY%; subtract HICP_CORE YoY)
        m3_yoy = _last_value(snapshot.get("EA_M3_YOY"))
        if m3_yoy is not None:
            real = m3_yoy - core_hicp_yoy
            interp = (
                "expansionary (excess liquidity)" if real > 2.0 else
                "modest expansion" if real > 0.5 else
                "neutral" if real > -0.5 else
                "contractionary"
            )
            parts.append(f"| Real M3 (YoY) | {real:+.2f}% (nominal M3 {m3_yoy:+.2f}%) | {interp} |")

        # Real bank lending NFC
        nfc_yoy = _last_value(snapshot.get("EA_BANK_LOANS_NFC"))
        if nfc_yoy is not None:
            real = nfc_yoy - core_hicp_yoy
            interp = (
                "real corporate credit expansion" if real > 1.0 else
                "neutral" if real > -0.5 else
                "real credit contraction (transmission active)"
            )
            parts.append(
                f"| Real bank lending NFC (YoY) | {real:+.2f}% (nominal {nfc_yoy:+.2f}%) | {interp} |"
            )

        # Real bank lending HH
        hh_yoy = _last_value(snapshot.get("EA_BANK_LOANS_HH"))
        if hh_yoy is not None:
            real = hh_yoy - core_hicp_yoy
            interp = (
                "real household credit expansion" if real > 1.0 else
                "neutral" if real > -0.5 else
                "real household credit contraction"
            )
            parts.append(
                f"| Real bank lending HH (YoY) | {real:+.2f}% (nominal {hh_yoy:+.2f}%) | {interp} |"
            )
        parts.append("")

    # ═══════════════════════════════════════
    # Yield curve
    # ═══════════════════════════════════════
    parts.append("### Yield curve")
    parts.append("")
    bund_10y = _last_value(snapshot.get(NOMINAL_10Y_KEY))
    bund_2y = _last_value(snapshot.get(NOMINAL_2Y_KEY))
    if bund_10y is None or bund_2y is None:
        parts.append("_Bund 10Y или 2Y липсва — curve spread не може да се изчисли._")
    else:
        spread = bund_10y - bund_2y
        bps = spread * 100
        interp = (
            "**inverted** — recession proxy (EA history: 2008, 2011 inverted преди cycle turn)"
            if spread < 0 else
            "flat (late-cycle / pre-recession)" if spread < 0.5 else
            "normal slope" if spread < 1.5 else
            "steep (early-cycle / re-acceleration)"
        )
        parts.append("| Spread | Стойност | Интерпретация |")
        parts.append("|---|---|---|")
        parts.append(f"| Bund 10Y-2Y | {bps:+.0f} bps ({spread:+.2f}pp) | {interp} |")
        parts.append("")
        parts.append("_Note: 10Y-3M spread не е в каталога; добавянето е Phase 2 candidate._")
        parts.append("")

    # ═══════════════════════════════════════
    # Sovereign spreads (BTP-Bund, OAT-Bund)
    # ═══════════════════════════════════════
    parts.append("### Sovereign stress (vs Bund) — EA-unique fragmentation proxy")
    parts.append("")
    btp = _last_value(snapshot.get("EA_BTP_BUND_SPREAD"))
    oat = _last_value(snapshot.get("EA_OAT_BUND_SPREAD"))
    if btp is None and oat is None:
        parts.append("_DE_10Y или peripheral 10Y липсва — spreads не могат да се изчислят._")
    else:
        parts.append("| Spread | Стойност | Интерпретация |")
        parts.append("|---|---|---|")
        if btp is not None:
            interp = (
                "**висок stress** — fragmentation regime (TPI candidate)" if btp > 2.0 else
                "елевиран (watch list)" if btp > 1.0 else
                "нормален" if btp > 0.5 else
                "compressed (benign convergence)"
            )
            parts.append(f"| BTP-Bund (IT-DE 10Y) | {btp:+.2f}pp ({btp*100:+.0f} bps) | {interp} |")
        if oat is not None:
            interp = (
                "France-specific stress" if oat > 1.0 else
                "елевиран" if oat > 0.6 else
                "нормален"
            )
            parts.append(f"| OAT-Bund (FR-DE 10Y) | {oat:+.2f}pp ({oat*100:+.0f} bps) | {interp} |")
        parts.append("")
        parts.append(
            "_Контекст: post-2022 ECB има explicit TPI (Transmission Protection "
            "Instrument) — fragmentation може да се абсорбира, не assume-вай 2011 repeat._"
        )
        parts.append("")

    # ═══════════════════════════════════════
    # Anchored band проверка (SPF LT)
    # ═══════════════════════════════════════
    parts.append("### Anchored band проверка — SPF inflation expectations")
    parts.append("")
    spf_zone = ANCHORED_ZONES.get(FORWARD_INFL_KEY)
    spf_series = snapshot.get(FORWARD_INFL_KEY)
    if spf_zone and spf_series is not None and not spf_series.empty:
        cur = float(spf_series.iloc[-1])
        anch_lo, anch_hi = spf_zone["anchored_band"]
        drift_lo, drift_hi = spf_zone["drift_band"]
        if anch_lo <= cur <= anch_hi:
            zone_state = "✅ в anchored band (±1σ)"
        elif drift_lo <= cur <= drift_hi:
            zone_state = f"⚠ drifting (между ±1σ и ±2σ от mean {spf_zone['mean']:.2f}%)"
        else:
            zone_state = f"❌ DE-ANCHORED (beyond ±2σ от {spf_zone['mean']:.2f}%)"
        pct = _percentile_5y(spf_series, history_years)
        pct_str = f"{pct:.0f}%" if pct is not None else "—"
        sigma_dist = (cur - spf_zone["mean"]) / spf_zone["std"] if spf_zone["std"] > 0 else 0.0
        parts.append("| Серия | Текущо | Anchored zone (±1σ) | Състояние | 5y percentile |")
        parts.append("|---|---|---|---|---|")
        parts.append(
            f"| `{FORWARD_INFL_KEY}` | {cur:.2f}% | "
            f"[{anch_lo:.2f}, {anch_hi:.2f}]% | {zone_state} ({sigma_dist:+.2f}σ) | {pct_str} |"
        )
        parts.append("")
        parts.append(
            f"_Empirical band derived от **stable era 2003-2019** "
            f"(n={spf_zone['n_observations']} quarterly): mean = {spf_zone['mean']:.2f}%, "
            f"std = {spf_zone['std']:.2f}pp. ECB target = {spf_zone['ecb_target']:.2f}%._"
        )
        parts.append("")
    else:
        parts.append("_SPF LT липсва — anchored band проверка не може да се направи._")
        parts.append("")

    # ═══════════════════════════════════════
    # PPI → CPI pipeline (EA: PPI Intermediate, lead 3-6m typically)
    # ═══════════════════════════════════════
    parts.append("### Inflation pipeline (PPI Intermediate → HICP Core)")
    parts.append("")
    ppi_raw = snapshot.get("EA_PPI_INTERMEDIATE")
    if ppi_raw is not None and not ppi_raw.empty and core_hicp_yoy is not None:
        ppi_yoy = _yoy_pct(ppi_raw)  # PPI level → YoY%
        if ppi_yoy is not None:
            ppi_3m = _annualized_change(ppi_raw, periods=3)
            # HICP core е already YoY% (level transform); 3m annualized чрез pct_change
            # на raw HICP level не е достъпен (RCH_A = вече rate). Използваме само YoY за CPI.
            gap_yoy = ppi_yoy - core_hicp_yoy
            if gap_yoy > 1.0:
                interp = "**PPI горещ → CPI core likely up (3-6m EA lag)**"
            elif gap_yoy < -1.0:
                interp = "**PPI cooler → CPI core може да последва (disinflation pipeline)**"
            else:
                interp = "PPI и CPI core aligned — neutral pipeline"
            parts.append(f"- PPI Intermediate: **{ppi_yoy:+.2f}% YoY**" +
                         (f" · {ppi_3m:+.2f}% 3m annualized" if ppi_3m is not None else ""))
            parts.append(f"- HICP Core: **{core_hicp_yoy:+.2f}% YoY**")
            parts.append(f"- YoY gap (PPI − CPI core): **{gap_yoy:+.2f}pp**")
            parts.append(f"- Pipeline signal: {interp}")
            parts.append("")
            parts.append(
                "_EA PPI→CPI lag е по-дълъг от US (3-6m vs 1-3m) — bank-based "
                "transmission и rigid pricing structures slow pass-through._"
            )
        else:
            parts.append("_PPI YoY не може да се изчисли (история < 12m)._")
    else:
        parts.append("_PPI Intermediate или HICP Core липсва._")
    parts.append("")
    return "\n".join(parts)


# ============================================================
# SECTION 2: ТЕМИ ПО PEER GROUP
# ============================================================

def _fmt_breadth_pct(v) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "—"
    if math.isnan(f):
        return "—"
    return f"{f*100:.0f}%"


def _render_themes(lens_reports: dict) -> str:
    parts = ["## 2. Темите по peer group", ""]
    for lens in LENS_ORDER:
        rep = lens_reports.get(lens)
        if rep is None:
            continue
        parts.append(f"### {LENS_LABEL_BG.get(lens, lens)}")
        parts.append("")
        parts.append("| Peer group | breadth ↑ | breadth |z|>2 | данни | посока | екстремни членове |")
        parts.append("|---|---|---|---|---|---|")
        for pg in rep.peer_groups:
            bp = _fmt_breadth_pct(pg.breadth_positive)
            be = _fmt_breadth_pct(pg.breadth_extreme)
            n_str = f"{pg.n_available}/{pg.n_members}"
            dir_lbl = DIRECTION_LABEL_BG.get(pg.direction, pg.direction)
            ext_str = ", ".join(f"`{m}`" for m in pg.extreme_members) if pg.extreme_members else "—"
            parts.append(f"| {pg.name} | {bp} | {be} | {n_str} | {dir_lbl} | {ext_str} |")
        parts.append("")
    return "\n".join(parts)


# ============================================================
# SECTION 3: CROSS-LENS DIVERGENCE
# ============================================================

def _render_cross_lens(cross_report) -> str:
    parts = ["## 3. Cross-Lens Divergence", ""]
    pair_lookup = {p["id"]: p for p in CROSS_LENS_PAIRS}

    for pair_reading in cross_report.pairs:
        pair_meta = pair_lookup.get(pair_reading.pair_id, {})
        narrative = pair_meta.get("narrative", "")
        state_lbl = STATE_LABEL_BG.get(pair_reading.state, pair_reading.state)
        breadth_a = _fmt_breadth_pct(pair_reading.breadth_a)
        breadth_b = _fmt_breadth_pct(pair_reading.breadth_b)

        parts.append(f"### {pair_reading.name_bg}")
        parts.append("")
        parts.append(f"**Въпрос:** {pair_reading.question_bg}")
        parts.append("")
        if narrative:
            parts.append(f"**Контекст:** {narrative}")
            parts.append("")
        parts.append(f"**Текущо състояние:** {state_lbl} (`{pair_reading.state}`)")
        parts.append("")
        parts.append(f"**Интерпретация:** {pair_reading.interpretation}")
        parts.append("")

        parts.append("| Slot | Label | Breadth | n |")
        parts.append("|---|---|---|---|")
        parts.append(f"| A | {pair_reading.slot_a_label} | {breadth_a} | {pair_reading.n_a_available} |")
        parts.append(f"| B | {pair_reading.slot_b_label} | {breadth_b} | {pair_reading.n_b_available} |")
        parts.append("")

        slot_a_pgs = pair_meta.get("slot_a", {}).get("peer_groups", [])
        slot_b_pgs = pair_meta.get("slot_b", {}).get("peer_groups", [])
        slot_a_inv = pair_meta.get("slot_a", {}).get("invert", {})
        slot_b_inv = pair_meta.get("slot_b", {}).get("invert", {})
        parts.append("**Състав:**")
        parts.append(
            "- A peer_groups: " +
            ", ".join(f"`{p}`" + (" (inv)" if slot_a_inv.get(p) else "") for p in slot_a_pgs)
        )
        parts.append(
            "- B peer_groups: " +
            ", ".join(f"`{p}`" + (" (inv)" if slot_b_inv.get(p) else "") for p in slot_b_pgs)
        )
        parts.append("")

        # All 5 states with active marked
        interps = pair_meta.get("interpretations", {})
        if interps:
            parts.append("**Всички възможни състояния:**")
            for state_key, interp in interps.items():
                state_lbl_alt = STATE_LABEL_BG.get(state_key, state_key)
                marker = " ← АКТИВНО" if state_key == pair_reading.state else ""
                parts.append(f"- `{state_key}` ({state_lbl_alt}): {interp}{marker}")
            parts.append("")
    return "\n".join(parts)


# ============================================================
# SECTION 4: TOP ANOMALIES (FACT CARDS)
# ============================================================

def _render_anomalies(anomaly_report, snapshot, today: date, history_years: int) -> str:
    parts = ["## 4. Top Anomalies (fact cards)", ""]
    if not anomaly_report.top:
        parts.append("_Няма серии с |z|>2 в момента._")
        return "\n".join(parts)

    parts.append(
        f"Серии с **|z|>{anomaly_report.threshold:.0f}** "
        f"(lookback {anomaly_report.lookback_years}y), "
        f"сортирани по абсолютна сила. Всеки fact card съдържа стойност, "
        f"делта в правилни units (bps/Δ/%), 5-годишен range, "
        f"последни {FACT_CARD_TAIL} readings и narrative_hint."
    )
    parts.append("")
    parts.append(
        "> ⚠ **Caveat за NEW 5Y MAX/MIN flags:** 5y window = post-COVID era. "
        "За по-дълъг исторически контекст (sovereign crisis 2011, GFC 2008) виж "
        "explorer данните или направи отделен query."
    )
    parts.append("")

    for i, a in enumerate(anomaly_report.top, 1):
        parts.append(_series_fact_card(a.series_key, snapshot, today, history_years, rank=i, anomaly=a))
        parts.append("")
    return "\n".join(parts)


def _series_fact_card(
    sid: str,
    snapshot: dict,
    today: date,
    history_years: int,
    rank: Optional[int] = None,
    anomaly=None,
) -> str:
    """Markdown fact card за единична серия с full context."""
    meta = SERIES_CATALOG.get(sid, {})
    series = snapshot.get(sid, pd.Series(dtype=float))

    title = meta.get("name_bg", sid)
    rank_prefix = f"#{rank} " if rank else ""

    if series.empty:
        return f"### {rank_prefix}`{sid}` — {title}\n_(няма данни в snapshot-а)_"

    s = series.dropna().sort_index()
    last_value = float(s.iloc[-1])
    last_date_obj = s.index[-1].date() if hasattr(s.index[-1], "date") else None
    last_date_str = str(last_date_obj) if last_date_obj else str(s.index[-1])[:10]

    kind = change_kind(sid, meta)

    try:
        long_periods = _infer_yoy_periods(s)
    except Exception:
        long_periods = 12
    try:
        long_chg_series = compute_change(s, kind, long_periods)
        short_chg_series = compute_change(s, kind, 1)
        long_chg = long_chg_series.iloc[-1] if not long_chg_series.empty else float("nan")
        short_chg = short_chg_series.iloc[-1] if not short_chg_series.empty else float("nan")
    except Exception:
        long_chg = float("nan")
        short_chg = float("nan")

    # 5y window stats
    cutoff = pd.Timestamp(last_date_str) - pd.DateOffset(years=history_years)
    s_hist = s[s.index >= cutoff]
    if len(s_hist) > 1:
        hist_min = float(s_hist.min())
        hist_max = float(s_hist.max())
        hist_median = float(s_hist.median())
        below_count = int((s_hist < last_value).sum())
        pct_rank = below_count / len(s_hist) * 100
        std = float(s_hist.std())
        mean = float(s_hist.mean())
        z = (last_value - mean) / std if std != 0 else 0.0
    else:
        hist_min = hist_max = hist_median = pct_rank = z = float("nan")

    tail = s.tail(FACT_CARD_TAIL)

    lines = []
    lines.append(f"### {rank_prefix}`{sid}` — {title}")
    lines.append("")

    # Identification (ECB or Eurostat)
    source = meta.get("source", "?")
    source_id = meta.get("id", sid)
    lens_str = " / ".join(meta.get("lens", []))
    peer_str = meta.get("peer_group", "")
    tags = meta.get("tags") or []
    tags_str = " · ".join(f"`{t}`" for t in tags) if tags else ""
    src_label = {"ecb": "ECB", "eurostat": "Eurostat", "derived": "Derived"}.get(source, source.upper())

    lines.append(
        f"- **{src_label}:** `{source_id}` · **Тема:** {lens_str} · **Peer:** {peer_str}"
        + (f" · **Тагове:** {tags_str}" if tags_str else "")
    )

    # Period-aware staleness (Phase 8d)
    release_schedule = meta.get("release_schedule", "monthly")
    if last_date_obj:
        stale_status, stale_age = assess_data_staleness(
            last_date_str, release_schedule, today=today,
        )
        if stale_status == "DATA_STALE":
            period_lag = PERIOD_LENGTH_DAYS.get(release_schedule, 30) + RELEASE_LAG_DAYS.get(release_schedule, 30)
            lines.append(
                f"- ❌ **Staleness:** очакваният next release беше преди ~{stale_age - period_lag:.0f} дни "
                f"(threshold: {period_lag}d за {release_schedule})"
            )
        elif release_schedule == "quarterly" and stale_age is not None:
            lines.append(
                f"- ℹ **Quarterly note:** EA quarterly има 50d release lag. "
                f"Last_obs = {last_date_str}; следващ release около "
                f"{(last_date_obj + timedelta(days=PERIOD_LENGTH_DAYS['quarterly'] + RELEASE_LAG_DAYS['quarterly'])).isoformat()}."
            )

    # Nominal warning
    if sid in NOMINAL_SERIES_NEED_DEFLATION:
        lines.append(
            f"- ⚠ **Nominal:** тази серия е nominal — за thesis-claim "
            "за real growth, виж секция 1.5 (Cross-spreads → Real wages/M3/lending)"
        )

    # SPF anchored band link
    if sid == FORWARD_INFL_KEY:
        lines.append("- 🎯 **Anchored band** — виж секция 1.5 за empirical thresholds.")

    # Current state line
    extreme_marker = ""
    if anomaly:
        if anomaly.is_new_extreme and anomaly.new_extreme_direction == "max":
            extreme_marker = " · **NEW 5Y MAX** ⚠"
        elif anomaly.is_new_extreme and anomaly.new_extreme_direction == "min":
            extreme_marker = " · **NEW 5Y MIN** ⚠"

    pct_str = f"{pct_rank:.0f}%" if not math.isnan(pct_rank) else "—"
    lines.append(
        f"- **Текущо ({last_date_str}):** {fmt_value(last_value)} · "
        f"**z** {z:+.2f} · **percentile (5y)** {pct_str}"
        + (f" · **Δ direction** {anomaly.direction}" if anomaly else "")
        + extreme_marker
    )

    # Change line
    long_lbl = "Δ1y" if long_periods >= 12 else f"Δ{long_periods}p"
    lines.append(
        f"- **Промяна:** {long_lbl} {fmt_change(long_chg, kind)} · "
        f"Δ short {fmt_change(short_chg, kind)} (display: {kind})"
    )

    # 5y range
    if not (math.isnan(hist_min) or math.isnan(hist_max)):
        lines.append(
            f"- **5y range:** мин {fmt_value(hist_min)} · "
            f"медиана {fmt_value(hist_median)} · макс {fmt_value(hist_max)}"
        )

    # Last readings
    lines.append(f"- **Последни {len(tail)} readings:**")
    for dt, val in tail.items():
        d_str = dt.date() if hasattr(dt, "date") else str(dt)[:10]
        lines.append(f"  - {d_str} → {fmt_value(float(val))}")

    # Narrative hint
    hint = meta.get("narrative_hint") or ""
    if hint:
        lines.append(f"- **Тълкуване (от каталога):** {hint}")

    return "\n".join(lines)


# ============================================================
# SECTION 5: METHODOLOGY (compact)
# ============================================================

def _render_methodology_compact() -> str:
    return """## 5. Методология (compact)

- **Breadth ↑** — % серии в peer group с положителен 1-периоден momentum. Прагове: >60% разширяване, <40% свиване, между = смесено.
- **Breadth |z|>2** — % серии в групата със стойност >2 стандартни отклонения от 5y mean (екстремна).
- **z-score** — стандартизирана отдалеченост от 5y средна. |z|>2 = ~5% от времето в нормална дистрибуция.
- **Percentile (5y)** — къде стои текущата стойност в 5-годишното разпределение (0% = нов 5y минимум, 100% = нов 5y максимум).
- **Cross-lens states** — `both_up` / `both_down` / `a_up_b_down` / `a_down_b_up` (divergence) / `transition` (между прагове) / `insufficient_data`.
- **Display-by-type** — за rate-нива (BUND, BTP, OAT, ECB_DFR, UNRATE) Δ е в bps; за signed индекси (CISS, ESI, confidence) — абсолютна делта; за price levels (HICP, IP, GDP) — %.
- **Period-aware staleness** — series flagged като DATA_STALE ако last_obs > period_length + release_lag (EU quarterly threshold = 140d, monthly = 60d).
- **Anchored band (SPF)** — empirical bands derived от 2003-2019 stable era (mean 1.91%, std 0.13pp, n=50). ECB target = 2.00%.
- **EA-specific cross-lens pairs** — `fragmentation_risk` (BTP-Bund vs ECB rates) и `ecb_transmission` (rates vs bank lending) са EA-уникални; останалите 4 имат US аналози.
- **Малки peer groups (2 серии)** — 1 серия флипваща = 50pp промяна. Малките групи са по-волатилни в breadth.
"""


# ============================================================
# PUBLIC API
# ============================================================

def generate_briefing_context(
    snapshot: dict[str, pd.Series],
    lens_reports: dict,
    cross_report,
    anomaly_report,
    today: date,
    output_path: str | Path,
    history_years: int = HISTORY_YEARS,
) -> str:
    """Генерира briefing_context_YYYY-MM-DD.md за LLM analysis.

    Args:
        snapshot: {sid → pd.Series}.
        lens_reports: {lens → LensBreadthReport}.
        cross_report: CrossLensDivergenceReport.
        anomaly_report: AnomalyReport.
        today: дата за file name + header.
        output_path: директория за изход (или директно файл — handles both).
        history_years: 5y window default.

    Returns:
        Абсолютен path към записания .md файл (str).
    """
    sections = [
        _render_header(today, lens_reports, cross_report, anomaly_report),
        _render_executive_summary(lens_reports, anomaly_report),
        _render_cross_spreads(snapshot, today, history_years),
        _render_themes(lens_reports),
        _render_cross_lens(cross_report),
        _render_anomalies(anomaly_report, snapshot, today, history_years),
        _render_methodology_compact(),
    ]
    body = "\n\n".join(sections)

    out_path = Path(output_path)
    if out_path.suffix == ".md":
        # Direct file path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(body, encoding="utf-8")
        return str(out_path.resolve())
    else:
        # Directory — generate filename
        out_path.mkdir(parents=True, exist_ok=True)
        out_file = out_path / f"briefing_context_{today.isoformat()}.md"
        out_file.write_text(body, encoding="utf-8")
        return str(out_file.resolve())
