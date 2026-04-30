"""
export/briefing_context.py
==========================
Markdown export за LLM analysis — Phase 9.

Различава се от weekly_briefing.py (HTML за човек):
  - Markdown structured за copy-paste в LLM context
  - BG language by default; английски ще се добави в Phase 10
  - Per-series fact cards с пълна metadata
  - Cross-spreads section с derived numbers (Phase 8)
  - Methodology footer с обяснение на metrics

Sections (BG):
  1. Header — timestamp, catalog scope, overall regime
  2. Executive — 5 lens composites + macro snapshot
  3. Themes — 3-4 sentence narrative capturing top themes
  4. Cross-Lens — 6 pairs current state
  5. Cross-Spreads — real DFR, yield curve, sovereign spreads, anchored band
  6. Anomalies — extreme readings per lens
  7. Series Fact Cards — annex с пълна metadata за всяка серия
  8. Methodology — обяснение на metrics + ограничения

Output:
  output/briefing_context_YYYY-MM-DD.md
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from catalog.series import SERIES_CATALOG, series_by_lens, series_by_peer_group
from catalog.cross_lens_pairs import CROSS_LENS_PAIRS
from config import (
    HISTORY_START, MODULE_WEIGHTS, ANCHORED_ZONES,
    NOMINAL_SERIES_NEED_DEFLATION,
)
from analysis.cross_spreads import (
    compute_real_dfr_forward,
    compute_yield_curve_spread,
    compute_sovereign_stress_spreads,
    assess_anchored_band,
    ppi_cpi_lead_lag,
)


# ============================================================
# Helpers
# ============================================================

LENS_LABEL_BG = {
    "labor":     "Пазар на труда",
    "inflation": "Инфлация",
    "growth":    "Растеж и активност",
    "credit":    "Финансови условия",
    "ecb":       "ЕЦБ парична политика",
}

LENS_ICON = {
    "labor": "👷", "inflation": "🔥", "growth": "📈",
    "credit": "🏛", "ecb": "🏦",
}


def _format_value(value: Optional[float], is_rate: bool = False, decimals: int = 2) -> str:
    """Форматира число с подходящо unit (% или pp)."""
    if value is None:
        return "—"
    if isinstance(value, (int, float)) and np.isnan(value):
        return "—"
    fmt = f"{{:.{decimals}f}}"
    return fmt.format(value)


def _series_percentile(series: pd.Series, value: float, history_start: str = HISTORY_START) -> Optional[float]:
    history = series[series.index >= pd.Timestamp(history_start)].dropna()
    if len(history) == 0:
        return None
    return float((history < value).sum() / len(history) * 100)


def _series_5y_window(series: pd.Series) -> pd.Series:
    if series.empty:
        return series
    cutoff = series.index.max() - pd.DateOffset(years=5)
    return series.loc[cutoff:]


def _last_n_readings(series: pd.Series, n: int = 6) -> list[tuple[str, float]]:
    if series.empty:
        return []
    tail = series.dropna().tail(n)
    return [(str(d.date()), float(v)) for d, v in tail.items()]


# ============================================================
# Section renderers
# ============================================================

def render_header(snapshot: dict[str, pd.Series]) -> str:
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    n_series = len(snapshot)
    n_catalog = len(SERIES_CATALOG)
    return (
        f"# Briefing Context — Eurozone Macro Dashboard\n\n"
        f"**Дата:** {today}\n"
        f"**Catalog:** {n_catalog} серии | **Snapshot:** {n_series} fetched\n"
        f"**History window:** от {HISTORY_START} (EMU era)\n"
        f"**Език:** български | **Audience:** LLM context за дълбок макро анализ\n\n"
    )


def render_executive(modules_results: list[dict]) -> str:
    """5-lens composite snapshot + macro score."""
    lines = ["## 1. Executive Summary\n"]

    if not modules_results:
        return "\n".join(lines) + "\n_Няма module results — стартирай --refresh._\n"

    # Composite macro
    weighted = sum(
        r["composite"] * MODULE_WEIGHTS.get(r["module"], 0)
        for r in modules_results
    )
    total_weight = sum(MODULE_WEIGHTS.get(r["module"], 0) for r in modules_results)
    overall = round(weighted / total_weight, 1) if total_weight else 50.0

    lines.append(f"**Композитен Macro Score: {overall}**\n")
    lines.append("| Тема | Composite | Regime | Серии |")
    lines.append("|---|---:|---|---:|")
    for r in modules_results:
        icon = LENS_ICON.get(r["module"], "")
        label = r["label"]
        n = len(r.get("indicators", {}))
        lines.append(f"| {icon} {label} | {r['composite']:.1f} | {r['regime']} | {n} |")
    lines.append("")
    return "\n".join(lines) + "\n"


def render_themes(modules_results: list[dict], snapshot: dict[str, pd.Series]) -> str:
    """3-4 sentence narrative capturing top themes."""
    lines = ["## 2. Главни теми (data-driven, без LLM intervention)\n"]

    # Inflation theme
    infl_result = next((r for r in modules_results if r["module"] == "inflation"), None)
    if infl_result:
        inflation_score = infl_result["composite"]
        if inflation_score > 70:
            lines.append(f"- **Инфлация ЕЛЕВИРАНА** (composite {inflation_score:.1f}) — натиск над ЕЦБ target.")
        elif inflation_score > 50:
            lines.append(f"- **Инфлация близо до целта** (composite {inflation_score:.1f}) — нормализация в ход.")
        else:
            lines.append(f"- **Инфлация ниска** (composite {inflation_score:.1f}) — потенциално deflation territory.")

    # Labor theme
    labor_result = next((r for r in modules_results if r["module"] == "labor"), None)
    if labor_result:
        labor_score = labor_result["composite"]
        regime = labor_result["regime"]
        lines.append(f"- **Labor: {regime}** (composite {labor_score:.1f}) — определя wage pass-through risk.")

    # ECB stance
    ecb_result = next((r for r in modules_results if r["module"] == "ecb"), None)
    if ecb_result:
        ecb_score = ecb_result["composite"]
        regime = ecb_result["regime"]
        lines.append(f"- **ЕЦБ stance: {regime}** (composite {ecb_score:.1f}).")

    # Credit
    credit_result = next((r for r in modules_results if r["module"] == "credit"), None)
    if credit_result:
        credit_score = credit_result["composite"]
        regime = credit_result["regime"]
        lines.append(f"- **Credit conditions: {regime}** (composite {credit_score:.1f}).")

    # Growth
    growth_result = next((r for r in modules_results if r["module"] == "growth"), None)
    if growth_result:
        growth_score = growth_result["composite"]
        regime = growth_result["regime"]
        lines.append(f"- **Растеж: {regime}** (composite {growth_score:.1f}).")

    return "\n".join(lines) + "\n\n"


def _peer_group_direction(snapshot: dict[str, pd.Series], peer_group: str) -> Optional[str]:
    """Простa direction класификация за peer_group breadth.

    Returns 'up' / 'down' / 'mixed' / None.
    """
    members = series_by_peer_group(peer_group)
    deltas = []
    for m in members:
        sid = m["_key"]
        s = snapshot.get(sid)
        if s is None or s.empty or len(s) < 13:
            continue
        recent = float(s.iloc[-1])
        year_ago_idx = s.index.max() - pd.DateOffset(years=1)
        past = s[s.index <= year_ago_idx]
        if past.empty:
            continue
        deltas.append(recent - float(past.iloc[-1]))

    if not deltas:
        return None

    pos = sum(1 for d in deltas if d > 0)
    neg = sum(1 for d in deltas if d < 0)
    if pos > 0 and neg == 0:
        return "up"
    if neg > 0 and pos == 0:
        return "down"
    if pos > neg:
        return "mostly_up"
    if neg > pos:
        return "mostly_down"
    return "mixed"


def render_cross_lens(snapshot: dict[str, pd.Series]) -> str:
    """6 cross-lens pairs current state."""
    lines = ["## 3. Cross-Lens двойки\n"]

    for pair in CROSS_LENS_PAIRS:
        slot_a = pair["slot_a"]
        slot_b = pair["slot_b"]

        dir_a = _peer_group_direction(snapshot, slot_a["peer_groups"][0]) if slot_a["peer_groups"] else None
        dir_b = _peer_group_direction(snapshot, slot_b["peer_groups"][0]) if slot_b["peer_groups"] else None

        # Простa state mapping
        if dir_a is None or dir_b is None:
            state = "transition"
        elif dir_a in ("up", "mostly_up") and dir_b in ("up", "mostly_up"):
            state = "both_up"
        elif dir_a in ("down", "mostly_down") and dir_b in ("down", "mostly_down"):
            state = "both_down"
        elif dir_a in ("up", "mostly_up") and dir_b in ("down", "mostly_down"):
            state = "a_up_b_down"
        elif dir_a in ("down", "mostly_down") and dir_b in ("up", "mostly_up"):
            state = "a_down_b_up"
        else:
            state = "transition"

        lines.append(f"### {pair['name_bg']}\n")
        lines.append(f"_{pair['question_bg']}_\n")
        lines.append(f"- **slot_a** ({slot_a['label']}): {dir_a or 'няма данни'}")
        lines.append(f"- **slot_b** ({slot_b['label']}): {dir_b or 'няма данни'}")
        lines.append(f"- **State:** `{state}`")
        lines.append(f"- **Интерпретация:** {pair['interpretations'][state]}")
        lines.append("")

    return "\n".join(lines) + "\n"


def render_cross_spreads(snapshot: dict[str, pd.Series]) -> str:
    """Phase 8 derived numbers: real DFR, yield curve, sovereign spreads, anchored band."""
    lines = ["## 4. Cross-Spreads и derived metrics\n"]

    # Real DFR
    real_dfr = compute_real_dfr_forward(snapshot)
    if real_dfr:
        stance = "restrictive" if real_dfr.is_restrictive else "neutral/loose"
        lines.append(
            f"### Реална policy rate (forward)\n\n"
            f"`real_DFR = ECB_DFR − SPF LT inflation = {real_dfr.nominal_rate:.2f}% − "
            f"{real_dfr.forward_inflation:.2f}% = **{real_dfr.real_rate:+.2f}pp**`\n\n"
            f"Stance: **{stance}**. > 0.5pp = restrictive, < 0pp = stimulative.\n"
        )

    # Yield curve
    curve = compute_yield_curve_spread(snapshot)
    if curve:
        slope_label = "inverted" if curve.is_inverted else ("flat" if abs(curve.spread_pp) < 0.25 else "positive")
        lines.append(
            f"### Yield curve (Bund 10Y-2Y)\n\n"
            f"`spread = {curve.spread_pp:+.2f}pp ({curve.spread_bps:+.0f}bps)` ({curve.last_date.date()})\n\n"
            f"Slope: **{slope_label}**. Inverted = recession risk proxy (post-EMU база).\n"
        )

    # Sovereign spreads
    spreads = compute_sovereign_stress_spreads(snapshot)
    if spreads:
        lines.append("### Sovereign spreads vs Bund\n")
        for sid, val in spreads.items():
            ctry = "BTP-Bund (IT)" if "BTP" in sid else "OAT-Bund (FR)"
            stress_level = "висок" if val > 1.5 else ("елевиран" if val > 0.8 else "нормален")
            lines.append(f"- **{ctry}**: {val:+.2f}pp — {stress_level} stress level.")
        lines.append("")

    # SPF anchored band
    spf = snapshot.get("EA_SPF_HICP_LT")
    if spf is not None and not spf.empty:
        latest = float(spf.iloc[-1])
        band = assess_anchored_band(latest, "EA_SPF_HICP_LT", series=spf)
        if band:
            zone = ANCHORED_ZONES["EA_SPF_HICP_LT"]
            lines.append(
                f"### SPF inflation expectations anchoring\n\n"
                f"Latest: **{latest:.2f}%** ({spf.index[-1].date()})\n\n"
                f"State: **{band.state}** (distance {band.distance_from_mean:+.2f}σ от mean {zone['mean']:.2f}%)\n\n"
                f"Empirical bands (от stable era {zone['stable_era']}, n={zone['n_observations']}):\n"
                f"- tight: [{zone['tight_band'][0]:.2f}, {zone['tight_band'][1]:.2f}]\n"
                f"- anchored: [{zone['anchored_band'][0]:.2f}, {zone['anchored_band'][1]:.2f}] (±1σ)\n"
                f"- de-anchored: outside [{zone['drift_band'][0]:.2f}, {zone['drift_band'][1]:.2f}]\n\n"
                f"{band.narrative_bg}\n"
            )

    # PPI-CPI lead-lag
    ll = ppi_cpi_lead_lag(snapshot)
    if ll:
        lines.append(
            f"### PPI → CPI core pipeline\n\n"
            f"Best lag: **{ll.best_lag} месеца** (correlation {ll.best_corr:.2f})\n\n"
            f"All lags: " + ", ".join(f"`{lag}m={c:.2f}`" for lag, c in sorted(ll.correlations.items())) + "\n"
        )

    return "\n".join(lines) + "\n"


def render_anomalies(modules_results: list[dict], snapshot: dict[str, pd.Series]) -> str:
    """Top extreme readings (|z-score| > 1.5) на base от scoring."""
    lines = ["## 5. Аномалии (|z| > 1.5)\n"]

    extreme: list[tuple[str, str, float, str]] = []  # (lens, sid, z, label)
    for r in modules_results:
        for sid, scored in r.get("indicators", {}).items():
            z = scored.get("z_score")
            if z is None:
                continue
            if abs(z) > 1.5:
                extreme.append((r["module"], sid, z, scored.get("name", sid)))

    if not extreme:
        lines.append("_Няма extreme z-scores в текущия snapshot._\n")
        return "\n".join(lines) + "\n"

    extreme.sort(key=lambda x: -abs(x[2]))
    for lens, sid, z, name in extreme[:8]:  # top 8
        sign = "↑" if z > 0 else "↓"
        lines.append(f"- {sign} `{sid}` ({lens}): z={z:+.2f} — {name}")
    lines.append("")
    return "\n".join(lines) + "\n"


def render_series_fact_cards(snapshot: dict[str, pd.Series]) -> str:
    """Per-series пълна metadata + последни 6 readings + 5y range."""
    lines = ["## 6. Series Fact Cards (annex)\n"]
    lines.append("Per series: ECB/Eurostat ID, percentile, 5y range, последни 6 readings, narrative.\n")

    by_lens: dict[str, list[str]] = {l: [] for l in LENS_LABEL_BG}

    for sid, meta in SERIES_CATALOG.items():
        for lens in meta.get("lens", []):
            if lens in by_lens:
                by_lens[lens].append(sid)

    for lens, sid_list in by_lens.items():
        if not sid_list:
            continue
        icon = LENS_ICON[lens]
        label = LENS_LABEL_BG[lens]
        lines.append(f"\n### {icon} {label}\n")

        for sid in sorted(sid_list):
            meta = SERIES_CATALOG[sid]
            series = snapshot.get(sid)

            lines.append(f"\n#### `{sid}` — {meta['name_bg']}\n")
            lines.append(f"- **Source:** {meta['source']} | **ID:** `{meta['id']}`")
            lines.append(f"- **Peer group:** {meta['peer_group']} | **Tags:** {meta['tags'] or '—'}")
            lines.append(
                f"- **Transform:** {meta['transform']} | **is_rate:** {meta['is_rate']} | "
                f"**Schedule:** {meta['release_schedule']}"
            )
            lines.append(f"- **History start:** {meta['historical_start']}")

            # Nominal flag
            if sid in NOMINAL_SERIES_NEED_DEFLATION:
                lines.append("- ⚠️ **Nominal series** — изисква deflation (HICP_CORE) за real анализ.")

            # SPF link
            if sid == "EA_SPF_HICP_LT":
                lines.append("- 🎯 **Anchored band** — виж секция 4 за empirical thresholds.")

            if series is None or series.empty:
                lines.append(f"- _no data в snapshot_")
                lines.append(f"- _{meta['narrative_hint']}_\n")
                continue

            latest = float(series.iloc[-1])
            last_date = series.index[-1].date()
            pct = _series_percentile(series, latest)
            window_5y = _series_5y_window(series).dropna()

            lines.append(f"- **Latest:** {latest:.3f} ({last_date}) | **Percentile (от {meta['historical_start']}):** {pct:.1f}/100" if pct is not None else f"- **Latest:** {latest:.3f}")

            if not window_5y.empty:
                lines.append(
                    f"- **5y window:** min {window_5y.min():.2f} | mean {window_5y.mean():.2f} | "
                    f"median {window_5y.median():.2f} | max {window_5y.max():.2f}"
                )

            readings = _last_n_readings(series, n=6)
            if readings:
                lines.append("- **Последни 6:** " + " · ".join(f"`{d}: {v:.2f}`" for d, v in readings))

            lines.append(f"- _{meta['narrative_hint']}_")

    return "\n".join(lines) + "\n"


def render_methodology() -> str:
    """Обяснение на metrics + ограничения."""
    return """
## 7. Methodology

### Score (0-100)
Per-series percentile rank спрямо историческия диапазон (EMU era 1999+).
Висок score = top-of-history; нисък = bottom. Invert flag обръща
семантиката за "lower is better" series (e.g., unemployment).

### Composite weights per lens
- **Labor:** UNRATE 0.40, LFS 0.25, EXP 0.10, WAGES 0.25
- **Inflation:** HICP HEADLINE 0.20, CORE 0.30, SERVICES 0.25, ENERGY 0.05, FOOD 0.05, PPI 0.15
- **Growth:** IP 0.30, RETAIL 0.25, BUILDING 0.15, GDP 0.20, ESI 0.10
- **Credit:** CISS 0.30, sovereign_spreads 0.25 (split BTP/OAT), bank_lending 0.20 (split NFC/HH), Bund 0.15, M3 0.10
- **ECB:** DFR 0.55, balance_sheet 0.30, MRO 0.15

### Composite Macro
weighted avg на lens composites: inflation 0.30, growth 0.20, credit 0.20, labor 0.15, ecb 0.15.

### YoY semantics (is_rate flag)
- is_rate=True → YoY column показва **pp delta** (HICP 2.4% → 2.0% = -0.4pp, не -16.7%)
- is_rate=False → YoY е relative % change (за индекси, balance scores, levels)

### Cross-Lens pairs (5-state interpretations)
- both_up / both_down: convergence
- a_up_b_down / a_down_b_up: divergence
- transition: mixed / insufficient signal

### SPF anchored zones (Phase 8)
Empirical bands от stable era 2003-2019 (n=50): mean=1.91%, std=0.13pp.
- tight (±0.5σ), anchored (±1σ), drifting (±2σ), de-anchored (beyond).
- ECB target reference: 2.00%.

### Period-aware staleness
- weekly: FRESH < 7d; DATA_STALE > 12d
- monthly: FRESH < 30d; DATA_STALE > 60d
- quarterly: FRESH < 90d; DATA_STALE > 140d (EU release_lag = 50d)
- annually: FRESH < 365d; DATA_STALE > 455d

### Limitations
1. SPF е quarterly — forward-fill за monthly join (smoothing artifact possible)
2. DG ECFIN sentiment series (teibs010/020/030) имат само 12mo история — не usable за percentile
3. Real growth deflator winner = HICP_CORE; alternative GDP deflator не е в catalog
4. Yield curve = 10Y-2Y; 10Y-3M не е в catalog (Phase 2 candidate)
5. Cross-lens direction е простa year-over-year delta; за продукционен use → breadth analysis (analysis/breadth.py)
"""


# ============================================================
# Main entry
# ============================================================

def _augment_snapshot_with_derived(snapshot: dict[str, pd.Series]) -> dict[str, pd.Series]:
    """Adds derived spread series (BTP-Bund, OAT-Bund) to snapshot за cross-lens render.

    Same logic като modules.credit._compute_derived_spreads — without circular import.
    """
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


def generate_briefing_context(
    snapshot: dict[str, pd.Series],
    modules_results: list[dict],
    output_path: str | Path,
) -> str:
    """Генерира briefing_context_YYYY-MM-DD.md за LLM analysis.

    Returns: full markdown text. Ako output_path е дадено — записва файла.
    """
    augmented = _augment_snapshot_with_derived(snapshot)

    parts = [
        render_header(augmented),
        render_executive(modules_results),
        render_themes(modules_results, augmented),
        render_cross_lens(augmented),
        render_cross_spreads(augmented),
        render_anomalies(modules_results, augmented),
        render_series_fact_cards(augmented),
        render_methodology(),
    ]
    text = "\n".join(parts)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    return text
