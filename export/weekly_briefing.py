"""
export/weekly_briefing.py
=========================
HTML weekly briefing renderer за Eurozone — US-style structure.

Sections (BG):
  1. Header — KPIs (n серии, n аномалии, n active cross-lens)
  2. Executive Summary — regime badge + narrative + breadth table
  3. Cross-Lens Divergence — pair cards (6 EA-specific двойки)
  4. Per-lens blocks — breadth tables по peer_group + lens anomalies
  5. Top Anomalies — серии с |z|>2 (display-by-type Δ)
  6. Historical Analogs (Phase 4)
  7. Journal entries (Phase 5)
  8. Footer — методология (collapsible)

Без composite scores в основното view (US-style focus върху breadth + direction).

Self-contained HTML: inline CSS, без JS, без CDN.
"""
from __future__ import annotations
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import math
import pandas as pd

from catalog.series import SERIES_CATALOG, ALLOWED_LENSES
from catalog.cross_lens_pairs import CROSS_LENS_PAIRS


# ─── Labels (BG) ─────────────────────────────────────────────────

LENS_ORDER = ["labor", "inflation", "growth", "credit", "ecb"]
LENS_LABEL_BG = {
    "labor":     "Пазар на труда",
    "inflation": "Инфлация",
    "growth":    "Растеж и активност",
    "credit":    "Финансови условия и кредит",
    "ecb":       "ЕЦБ парична политика",
}
LENS_ICON = {
    "labor": "👷", "inflation": "🔥", "growth": "📈",
    "credit": "🏛", "ecb": "🏦",
}
DIRECTION_LABEL_BG = {
    "expanding":         "разширяване",
    "contracting":       "свиване",
    "mixed":             "смесено",
    "insufficient_data": "недостатъчно данни",
}
DIRECTION_CSS = {
    "expanding":         "dir-up",
    "contracting":       "dir-dn",
    "mixed":             "dir-mix",
    "insufficient_data": "dir-ins",
}
STATE_LABEL_BG = {
    "both_up":           "↑↑ и двете нагоре",
    "both_down":         "↓↓ и двете надолу",
    "a_up_b_down":       "↑↓ A нагоре / B надолу",
    "a_down_b_up":       "↓↑ A надолу / B нагоре",
    "transition":        "⇄ преход",
    "insufficient_data": "недостатъчно данни",
}
STATE_CSS = {
    "both_up":           "state-up-up",
    "both_down":         "state-dn-dn",
    "a_up_b_down":       "state-mixed",
    "a_down_b_up":       "state-mixed",
    "transition":        "state-trans",
    "insufficient_data": "state-ins",
}


# ─── Format helpers ─────────────────────────────────────────────

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


# ─── Regime derivation (от cross-lens active states) ────────────

def _derive_regime(cross_report) -> tuple[str, str, str, Optional[str]]:
    """Derive (regime_label, regime_css, narrative, primary_driver) от 6-те EA pairs.

    Прости правила:
      - stagflation_test=both_up + inflation_anchoring=both_up → "Стагфлация + de-anchoring"
      - stagflation_test=both_up → "Stagflation watch"
      - pipeline_inflation=both_down + headline_measures свиване → "Disinflation"
      - fragmentation_risk=both_up → "Fragmentation"
      - ecb_transmission=both_up → "Transmission active"
      - all peer_groups свиване → "Synchronized slowdown"
      - otherwise → "Mixed / transition"
    """
    states = {p.pair_id: p.state for p in cross_report.pairs}

    if states.get("stagflation_test") == "both_up" and states.get("inflation_anchoring") == "both_up":
        return ("Стагфлация + de-anchoring",
                "regime-stag",
                "Заплати + базова инфлация и двете нагоре, очакванията следват — рискът ескалира; ЕЦБ под натиск.",
                "stagflation_test + inflation_anchoring")

    if states.get("stagflation_test") == "both_up":
        return ("Stagflation watch",
                "regime-stag",
                "Wage-price spiral компонентите натискат заедно нагоре — early warning без пълно потвърждение от очакванията.",
                "stagflation_test")

    if states.get("fragmentation_risk") == "both_up":
        return ("Фрагментационен режим",
                "regime-stress",
                "Periphery spreads се разширяват въпреки рестриктивна политика — TPI watch активен.",
                "fragmentation_risk")

    if states.get("pipeline_inflation") == "both_down" and states.get("inflation_anchoring") in ("both_down", "transition", "insufficient_data"):
        return ("Дезинфлация и охлаждане",
                "regime-cool",
                "PPI и core HICP отстъпват заедно — disinflation traction; ЕЦБ има пространство за политика.",
                "pipeline_inflation")

    if states.get("ecb_transmission") == "both_up":
        return ("Transmission active",
                "regime-soft",
                "ECB rates високи + bank lending се свива — restrictive stance ефективен.",
                "ecb_transmission")

    if states.get("ecb_transmission") == "a_up_b_down":
        return ("Transmission lag",
                "regime-dilem",
                "ECB hike-ва, но lending не се свива — typical lag window (12-24m EA), не failure.",
                "ecb_transmission")

    if states.get("sentiment_vs_hard_data") == "both_down":
        return ("Synchronized slowdown",
                "regime-slow",
                "Sentiment + hard data едновременно отслабват — recession watch.",
                "sentiment_vs_hard_data")

    if states.get("sentiment_vs_hard_data") == "both_up":
        return ("Разширяване",
                "regime-exp",
                "Sentiment + hard activity confirm-ват растеж.",
                "sentiment_vs_hard_data")

    return ("Преходно / смесено",
            "regime-trans",
            "Сигналите не са aligned; чакай confirm от next releases.",
            None)


# ─── Section: Header ─────────────────────────────────────────────

def _render_header(today: date, n_series: int, n_anomalies: int, n_active_cross: int) -> str:
    return f"""
<header class="brief-header">
  <div class="brief-title">
    <h1>Седмичен макро брифинг — Еврозона</h1>
    <div class="brief-subtitle">Генериран {today.strftime('%d %B %Y')} · ECB SDW + Eurostat данни</div>
  </div>
  <div class="brief-kpis">
    <div class="kpi"><div class="kpi-n">{n_series}</div><div class="kpi-l">серии</div></div>
    <div class="kpi"><div class="kpi-n">{n_anomalies}</div><div class="kpi-l">|z| &gt; 2</div></div>
    <div class="kpi"><div class="kpi-n">{n_active_cross}</div><div class="kpi-l">активни pairs</div></div>
  </div>
</header>
"""


# ─── Section: Executive Summary ──────────────────────────────────

def _render_executive(lens_reports: dict, cross_report, anomaly_report) -> str:
    regime_label, regime_css, narrative, driver = _derive_regime(cross_report)

    # Breadth row per lens (без composite scores!)
    rows = []
    for lens in LENS_ORDER:
        rep = lens_reports.get(lens)
        if rep is None:
            continue
        breadths = [
            pg.breadth_positive for pg in rep.peer_groups
            if not (isinstance(pg.breadth_positive, float) and math.isnan(pg.breadth_positive))
        ]
        avg_breadth = (sum(breadths) / len(breadths)) if breadths else None
        avg_str = _fmt_breadth_pct(avg_breadth)

        # Direction summary
        dir_counts = {"expanding": 0, "contracting": 0, "mixed": 0, "insufficient_data": 0}
        for pg in rep.peer_groups:
            dir_counts[pg.direction] = dir_counts.get(pg.direction, 0) + 1
        if dir_counts["expanding"] > dir_counts["contracting"]:
            dir_label = "разширяване"
            dir_class = "dir-up"
        elif dir_counts["contracting"] > dir_counts["expanding"]:
            dir_label = "свиване"
            dir_class = "dir-dn"
        else:
            dir_label = "смесено"
            dir_class = "dir-mix"

        n_anom = len(anomaly_report.by_lens.get(lens, []))
        n_new_extreme = sum(
            1 for r in anomaly_report.by_lens.get(lens, [])
            if getattr(r, "is_new_extreme", False)
        )
        new_str = f" <span class='ne-inline'>{n_new_extreme} NEW</span>" if n_new_extreme else ""

        icon = LENS_ICON.get(lens, "")
        label = LENS_LABEL_BG.get(lens, lens)
        rows.append(f"""
<tr>
  <td class="pg-name">{icon} {label}</td>
  <td><span class="dir-badge {dir_class}">{dir_label}</span></td>
  <td class="num">{avg_str}</td>
  <td class="num">{n_anom}{new_str}</td>
</tr>
""")

    driver_html = f'<div class="regime-driver">driver: {driver}</div>' if driver else ""

    return f"""
<section class="brief-section exec-section">
  <h2>Executive Summary</h2>
  <div class="exec-headline">
    <div class="regime-badge {regime_css}">
      <div class="regime-label">Режим</div>
      <div class="regime-val">{regime_label}</div>
      {driver_html}
    </div>
    <div class="exec-narrative">{narrative}</div>
  </div>

  <div class="exec-grid">
    <table class="regime-table">
      <thead><tr>
        <th>Тема</th><th>Посока</th><th>Breadth ↑</th><th>Аномалии</th>
      </tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
  </div>
</section>
"""


# ─── Section: Cross-Lens Divergence (pair cards) ─────────────────

def _render_cross_lens_pairs(cross_report) -> str:
    cards = []
    for p in cross_report.pairs:
        state_lbl = STATE_LABEL_BG.get(p.state, p.state)
        state_css = STATE_CSS.get(p.state, "state-trans")
        breadth_a_str = _fmt_breadth_pct(p.breadth_a)
        breadth_b_str = _fmt_breadth_pct(p.breadth_b)

        cards.append(f"""
<div class="pair-card">
  <div class="pair-head">
    <span class="pair-state {state_css}">{state_lbl}</span>
    <h3>{p.name_bg}</h3>
  </div>
  <div class="pair-question">{p.question_bg}</div>
  <div class="pair-grid">
    <div class="pair-slot">
      <div class="pair-slot-label">A · {p.slot_a_label}</div>
      <div class="pair-slot-val">{breadth_a_str}</div>
      <div class="pair-slot-n">n={p.n_a_available}</div>
    </div>
    <div class="pair-slot">
      <div class="pair-slot-label">B · {p.slot_b_label}</div>
      <div class="pair-slot-val">{breadth_b_str}</div>
      <div class="pair-slot-n">n={p.n_b_available}</div>
    </div>
  </div>
  <div class="pair-interp">{p.interpretation}</div>
</div>
""")

    return f"""
<section class="brief-section">
  <h2>Cross-Lens Divergence</h2>
  <div class="pair-wrap">
    {''.join(cards)}
  </div>
</section>
"""


# ─── Section: Per-Lens Blocks (breadth tables) ───────────────────

def _render_lens_block(lens: str, breadth_report, anomaly_report) -> str:
    lens_label = LENS_LABEL_BG.get(lens, lens)
    icon = LENS_ICON.get(lens, "")

    # Peer-group breadth table
    rows = []
    for pg in breadth_report.peer_groups:
        bp = _fmt_breadth_pct(pg.breadth_positive)
        be = _fmt_breadth_pct(pg.breadth_extreme)
        n_str = f"{pg.n_available}/{pg.n_members}"
        dir_label = DIRECTION_LABEL_BG.get(pg.direction, pg.direction)
        dir_class = DIRECTION_CSS.get(pg.direction, "dir-ins")
        ext_str = " ".join(
            f'<span class="ext-mark">{m}</span>' for m in pg.extreme_members
        ) if pg.extreme_members else ""

        rows.append(f"""
<tr>
  <td class="pg-name">{pg.name}</td>
  <td class="num">{bp}</td>
  <td class="num">{be}</td>
  <td class="num">{n_str}</td>
  <td><span class="dir-badge {dir_class}">{dir_label}</span></td>
  <td class="extremes">{ext_str}</td>
</tr>
""")

    # Anomalies in this lens (top 5)
    lens_anoms = anomaly_report.by_lens.get(lens, [])[:5]
    anom_items = []
    for r in lens_anoms:
        arrow = "↑" if r.direction == "up" else "↓"
        arrow_class = "up" if r.direction == "up" else "down"
        ne = ' <span class="ne">NEW 5Y MAX</span>' if (r.is_new_extreme and r.new_extreme_direction == "max") else \
             ' <span class="ne">NEW 5Y MIN</span>' if (r.is_new_extreme and r.new_extreme_direction == "min") else ""
        anom_items.append(
            f'<li><span class="arrow {arrow_class}">{arrow}</span> '
            f'<code>{r.series_key}</code> <span class="z">z={r.z_score:+.2f}</span>{ne} '
            f'<span class="pg">· {r.peer_group}</span></li>'
        )
    anoms_html = (
        f'<div class="lens-anoms"><h4>Аномалии в темата</h4><ol>{"".join(anom_items)}</ol></div>'
        if anom_items else
        '<div class="lens-anoms"><h4>Аномалии в темата</h4><p class="muted">Няма серии с |z|&gt;2.</p></div>'
    )

    return f"""
<section class="brief-section lens-block" data-lens="{lens}">
  <h2>{icon} {lens_label}</h2>

  <table class="breadth-table">
    <thead><tr>
      <th>Peer group</th><th>breadth ↑</th><th>breadth |z|&gt;2</th>
      <th>данни</th><th>посока</th><th>екстремни членове</th>
    </tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>

  {anoms_html}
</section>
"""


# ─── Section: Top Anomalies ──────────────────────────────────────

def _render_top_anomalies(snapshot: dict[str, pd.Series], anomaly_report, top_n: int = 10) -> str:
    from core.display import change_kind, latest_change, fmt_change, fmt_value

    if not anomaly_report.top:
        return f"""
<section class="brief-section">
  <h2>Top Anomalies</h2>
  <p class="muted">Няма серии в опашката (|z|&gt;2) сред {len(snapshot)} наблюдавани.</p>
</section>
"""

    rows = []
    for r in anomaly_report.top[:top_n]:
        direction_arrow = "▲" if r.direction == "up" else "▼"
        new_extreme = " 🔥" if r.is_new_extreme else ""

        meta = SERIES_CATALOG.get(r.series_key, {})
        kind = change_kind(r.series_key, meta)

        raw_series = snapshot.get(r.series_key)
        cur_val_str = "—"
        delta_str = "—"
        if raw_series is not None and not raw_series.empty:
            cur_val_str = fmt_value(raw_series.dropna().iloc[-1], digits=3)
            schedule = meta.get("release_schedule", "monthly")
            periods = {"weekly": 4, "monthly": 1, "quarterly": 1, "annually": 1}.get(schedule, 1)
            delta_val = latest_change(raw_series, kind, periods=periods)
            delta_str = fmt_change(delta_val, kind)

        rows.append(f"""
<tr>
  <td><code>{r.series_key}</code></td>
  <td class="num">{cur_val_str}</td>
  <td class="num">{delta_str}</td>
  <td class="num"><span class="anom-z">{direction_arrow} {r.z_score:+.2f}</span></td>
  <td>{new_extreme}</td>
</tr>
""")

    return f"""
<section class="brief-section">
  <h2>Top Anomalies ({len(rows)}/{anomaly_report.total_flagged})</h2>
  <p class="muted">Top {len(rows)} от {anomaly_report.total_flagged} флагнати серии · стойност+Δ форматирани display-by-type</p>
  <table class="anom-table">
    <thead><tr>
      <th>Серия</th>
      <th class="num">Стойност</th>
      <th class="num">Δ</th>
      <th class="num">Z-score</th>
      <th>5Y extreme?</th>
    </tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</section>
"""


# ─── Section: Historical Analogs (Phase 4 — preserved) ──────────

def _render_analogs(bundle: Any) -> str:
    if bundle is None:
        return ""

    current = bundle.current_state
    analogs = bundle.analogs

    if not analogs:
        return f"""
<section class="brief-section analogs">
  <h2>Исторически аналози</h2>
  <p class="muted">Недостатъчно данни за анализ (история {len(bundle.history_df)} наблюдения).</p>
</section>
"""

    raw = current.raw
    state_lines = []
    from analysis.macro_vector import DIM_LABELS_BG, DIM_UNITS
    for dim, val in raw.items():
        label = DIM_LABELS_BG.get(dim, dim)
        unit = DIM_UNITS.get(dim, "")
        state_lines.append(f"<li><strong>{label}:</strong> {val:.2f}{unit}</li>")

    analog_rows = []
    for a in analogs:
        sim_strength = "силен" if a.similarity > 0.85 else "добър" if a.similarity > 0.7 else "слаб"
        analog_rows.append(f"""
<tr>
  <td class="rank">#{a.rank}</td>
  <td class="date">{a.date.strftime('%Y-%m')}</td>
  <td class="similarity">{a.similarity:.2f} ({sim_strength})</td>
  <td class="episode">{a.episode_label or '—'}</td>
</tr>
""")

    forward = bundle.forward
    horizon_blocks = []
    for h in forward.horizons:
        rows = []
        for dim in forward.dims:
            agg = next(
                (a for a in forward.aggregates if a.dim == dim and a.horizon_months == h),
                None,
            )
            if agg is None or agg.median_value is None:
                continue
            label = DIM_LABELS_BG.get(dim, dim)
            unit = DIM_UNITS.get(dim, "")
            delta_str = f"{agg.median_delta:+.2f}{unit}" if agg.median_delta is not None else "—"
            rows.append(f"""
<tr>
  <td>{label}</td>
  <td class="num">{agg.median_value:.2f}{unit}</td>
  <td class="num delta">{delta_str}</td>
  <td class="range">[{agg.min_value:.2f}, {agg.max_value:.2f}]</td>
  <td class="n-cell">{agg.n}</td>
</tr>
""")
        if rows:
            horizon_blocks.append(f"""
<h4>След {h} месеца</h4>
<table class="forward-table">
  <thead><tr>
    <th>Dimension</th><th>Median value</th><th>Median Δ</th><th>Range</th><th>N</th>
  </tr></thead>
  <tbody>{''.join(rows)}</tbody>
</table>
""")

    return f"""
<section class="brief-section analogs">
  <h2>Исторически аналози</h2>
  <p class="muted">As-of: {current.as_of.strftime('%Y-%m')} ·
     Cosine similarity срещу {len(bundle.history_df)}-месечна EA история (от 1999)</p>

  <h3>Текущ макро state</h3>
  <ul class="state-list">{''.join(state_lines)}</ul>

  <h3>Топ {len(analogs)} най-подобни исторически периода</h3>
  <table class="analog-table">
    <thead><tr>
      <th>Rank</th><th>Period</th><th>Similarity</th><th>Episode</th>
    </tr></thead>
    <tbody>{''.join(analog_rows)}</tbody>
  </table>

  <h3>Forward outcomes (медиана през analog-ите)</h3>
  {''.join(horizon_blocks) if horizon_blocks else '<p class="muted">Няма forward данни.</p>'}
</section>
"""


# ─── Section: Journal (Phase 5 — preserved) ─────────────────────

_STATUS_LABELS_BG = {
    "open_question": "❓ Отворен въпрос",
    "hypothesis":    "🧪 Хипотеза",
    "finding":       "✓ Извод",
    "decision":      "◆ Решение",
}
_TOPIC_LABELS_BG = {
    "labor": "Трудов пазар", "inflation": "Инфлация", "credit": "Кредит",
    "growth": "Растеж", "analogs": "Исторически аналози",
    "regime": "Режими", "methodology": "Методология",
}


def _render_journal(entries: list) -> str:
    if not entries:
        return ""
    rows = []
    for e in entries[:8]:
        topic_bg = _TOPIC_LABELS_BG.get(e.topic, e.topic)
        status_bg = _STATUS_LABELS_BG.get(e.status, e.status)
        tags_str = " · ".join(f"<code>{t}</code>" for t in e.tags) if e.tags else "—"
        rows.append(f"""
<tr>
  <td class="j-date">{e.date.isoformat()}</td>
  <td class="j-topic">{topic_bg}</td>
  <td class="j-title">{e.title}</td>
  <td class="j-status">{status_bg}</td>
  <td class="j-tags">{tags_str}</td>
</tr>
""")

    return f"""
<section class="brief-section journal-section">
  <h2>📓 Свързани журнал бележки</h2>
  <p class="muted">{len(entries)} записа в журнала · показани {min(len(entries), 8)} най-скорошни</p>
  <table class="journal-table">
    <thead><tr>
      <th>Дата</th><th>Тема</th><th>Заглавие</th><th>Статус</th><th>Тагове</th>
    </tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</section>
"""


# ─── Section: Footer ─────────────────────────────────────────────

def _render_footer(today: date, n_series: int) -> str:
    return f"""
<footer class="brief-footer">
  <h2>Методология</h2>
  <details class="method">
    <summary><strong>Източници</strong></summary>
    <p>ECB Statistical Data Warehouse + Eurostat REST API (без API ключ). Adaptive cache TTL по release schedule.</p>
  </details>
  <details class="method">
    <summary><strong>Breadth ↑ (per peer group)</strong></summary>
    <p>% серии в peer group с положителен 1-периоден momentum. Прагове: &gt;60% разширяване, &lt;40% свиване, между = смесено. Под 2 серии = недостатъчно данни.</p>
  </details>
  <details class="method">
    <summary><strong>Breadth |z|&gt;2</strong></summary>
    <p>% серии в групата със стойност &gt;2 стандартни отклонения от 5y mean (екстремна).</p>
  </details>
  <details class="method">
    <summary><strong>Cross-Lens двойки</strong></summary>
    <p>6 EA-specific pairs включително fragmentation_risk (BTP-Bund vs ECB) и ecb_transmission (rates vs bank lending) — без US аналози. 5 възможни state-а: both_up / both_down / a_up_b_down / a_down_b_up / transition.</p>
  </details>
  <details class="method">
    <summary><strong>Sovereign spreads</strong></summary>
    <p>BTP-Bund (IT-DE), OAT-Bund (FR-DE) — derived в credit модул. BTP &gt; 1.5pp = висок stress; &gt; 0.8pp = елевиран.</p>
  </details>
  <details class="method">
    <summary><strong>Anchored zones (SPF)</strong></summary>
    <p>Empirical bands от 2003-2019 stable era (mean 1.91%, std 0.13pp, n=50): tight ±0.5σ, anchored ±1σ [1.78, 2.04], drifting ±2σ, de-anchored beyond. ECB target = 2.00%.</p>
  </details>
  <details class="method">
    <summary><strong>Caveats и ограничения</strong></summary>
    <p>v1 — {n_series} серии; пo-къса EA история (1999) от US (1970+); DG ECFIN sentiment series имат само 12mo (teibs010/020/030); SPF е quarterly (forward-fill за monthly join); yield curve = 10Y-2Y (10Y-3M не е в catalog). Малки peer groups (1 серия) → "недостатъчно данни"; нужни ≥2 серии за breadth.</p>
  </details>
  <p class="generated">Генериран на {today.strftime('%d %B %Y, %H:%M')} ·
     <a href="https://github.com/tsvetoslavtsachev/eu-macro-dashboard">eu-macro-dashboard</a></p>
</footer>
"""


# ─── CSS ────────────────────────────────────────────────────────

_CSS = """
* { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  margin: 0; padding: 0;
  background: #f8f9fa;
  color: #1a1a1a;
  line-height: 1.5;
}
.brief-main { max-width: 1100px; margin: 0 auto; padding: 28px 24px 60px; }

/* Header */
.brief-header {
  display: flex; justify-content: space-between; align-items: flex-end;
  border-bottom: 2px solid #222; padding-bottom: 14px; margin-bottom: 24px;
  flex-wrap: wrap; gap: 16px;
}
.brief-title h1 { margin: 0; font-size: 26px; font-weight: 600; }
.brief-subtitle { color: #666; font-size: 13px; margin-top: 4px; }
.brief-kpis { display: flex; gap: 14px; }
.kpi {
  background: #fff; border: 1px solid #e0e0e0; border-radius: 6px;
  padding: 8px 14px; text-align: center; min-width: 84px;
}
.kpi-n { font-size: 22px; font-weight: 600; color: #222; }
.kpi-l { font-size: 10.5px; color: #777; text-transform: uppercase; letter-spacing: 0.5px; }

/* Sections */
.brief-section { margin-bottom: 28px; background: #fff; padding: 18px 20px;
                 border: 1px solid #e0e0e0; border-radius: 8px; }
.brief-section h2 {
  font-size: 17px; text-transform: uppercase; letter-spacing: 1px;
  color: #333; border-bottom: 1px solid #ddd; padding-bottom: 6px; margin: 0 0 14px;
}
.brief-section h3 { font-size: 14.5px; margin: 14px 0 8px; }
.brief-section h4 { font-size: 12.5px; text-transform: uppercase; color: #666; letter-spacing: 0.7px; margin: 0 0 8px; }
.muted { color: #888; font-style: italic; font-size: 13px; }

/* Executive Summary */
.exec-section { background: #fff; }
.exec-headline { display: grid; grid-template-columns: minmax(220px, 280px) 1fr; gap: 18px; align-items: start; margin-bottom: 14px; }
.regime-badge { padding: 12px 14px; border-radius: 6px; text-align: center; border: 1px solid currentColor; }
.regime-badge .regime-label { font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.6px; opacity: 0.75; }
.regime-badge .regime-val { font-size: 18px; font-weight: 700; margin: 4px 0 6px; line-height: 1.25; }
.regime-badge .regime-driver { font-size: 10.5px; opacity: 0.6; font-family: monospace; }
.regime-stag   { background: #fdecec; color: #8a2020; }
.regime-soft   { background: #e9f5ee; color: #1e6b30; }
.regime-cool   { background: #e8f2ff; color: #2050a0; }
.regime-dilem  { background: #fff2e0; color: #8a4010; }
.regime-exp    { background: #e6f4ea; color: #1e6b30; }
.regime-slow   { background: #f3e8ff; color: #6030a0; }
.regime-stress { background: #fee0e0; color: #a02020; }
.regime-trans  { background: #f1f1f1; color: #555; }
.exec-narrative { background: #fafbfc; border-left: 3px solid #888; padding: 10px 14px;
                  font-size: 14px; line-height: 1.55; color: #222; border-radius: 0 4px 4px 0; }
.exec-grid { display: grid; grid-template-columns: 1fr; gap: 16px; align-items: start; }
.regime-table { width: 100%; border-collapse: collapse; font-size: 13px; background: #fff; }
.regime-table th, .regime-table td { padding: 7px 10px; text-align: left; border-bottom: 1px solid #eee; }
.regime-table th { background: #fafafa; color: #555; font-weight: 500; font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.5px; }
.ne-inline { display: inline-block; background: #ffeedd; color: #a05020; font-size: 10px; padding: 1px 5px; border-radius: 3px; font-weight: 600; margin-left: 4px; font-family: monospace; }
@media (max-width: 760px) {
  .exec-headline { grid-template-columns: 1fr; }
}

/* Cross-Lens pair cards */
.pair-wrap { display: grid; grid-template-columns: repeat(auto-fit, minmax(330px, 1fr)); gap: 14px; }
.pair-card { background: #fafbfc; border: 1px solid #e0e0e0; border-radius: 8px; padding: 14px 16px; }
.pair-head { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.pair-head h3 { margin: 0; font-size: 14.5px; font-weight: 600; }
.pair-state { font-size: 10.5px; padding: 3px 8px; border-radius: 4px; font-weight: 600; white-space: nowrap; }
.state-up-up { background: #fee; color: #a03030; }
.state-dn-dn { background: #e8f2ff; color: #2050a0; }
.state-mixed { background: #fff5d6; color: #806020; }
.state-trans { background: #eee; color: #555; }
.state-ins   { background: #f3f3f3; color: #999; }
.pair-question { font-size: 12.5px; color: #666; font-style: italic; margin-bottom: 10px; }
.pair-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }
.pair-slot { background: #fff; border: 1px solid #eee; border-radius: 5px; padding: 8px 10px; }
.pair-slot-label { font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: 0.5px; }
.pair-slot-val { font-family: 'Consolas', 'Monaco', monospace; font-size: 18px; font-weight: 600; margin-top: 4px; color: #222; }
.pair-slot-n { font-size: 10.5px; color: #999; }
.pair-interp { background: #fff; border-left: 3px solid #999; padding: 8px 12px; font-size: 13px; color: #333; border-radius: 0 4px 4px 0; }

/* Per-lens blocks */
.lens-block h2 { color: #222; }
.breadth-table, .anom-table { width: 100%; border-collapse: collapse; background: #fff;
                              border: 1px solid #e0e0e0; font-size: 13px; margin-bottom: 14px; }
.breadth-table th, .breadth-table td,
.anom-table th, .anom-table td { padding: 7px 10px; text-align: left; border-bottom: 1px solid #eee; vertical-align: middle; }
.breadth-table th, .anom-table th { background: #fafafa; color: #555; font-weight: 500; font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.5px; }
.num { font-family: 'Consolas', 'Monaco', monospace; text-align: right; }
.pg-name { font-weight: 500; }
.dir-badge { font-size: 11px; padding: 2px 8px; border-radius: 3px; font-weight: 500; }
.dir-up  { background: #e6f4ea; color: #1e6b30; }
.dir-dn  { background: #fdeaea; color: #a02020; }
.dir-mix { background: #fff5d6; color: #806020; }
.dir-ins { background: #f1f1f1; color: #888; }
.ext-mark { display: inline-block; background: #fff3d6; border: 1px solid #e8c97a; color: #806020; padding: 1px 6px; border-radius: 3px; font-size: 10.5px; font-family: monospace; margin-right: 4px; }
.extremes { max-width: 260px; }

.lens-anoms { background: #fafafa; border: 1px solid #eee; border-radius: 6px; padding: 10px 14px; }
.lens-anoms ol { margin: 0; padding-left: 20px; }
.lens-anoms li { font-size: 13px; margin-bottom: 4px; }
.arrow { font-family: monospace; font-weight: 600; }
.arrow.up { color: #1e6b30; }
.arrow.down { color: #a02020; }
.ne { display: inline-block; background: #ffeedd; color: #a05020; font-size: 10.5px; padding: 1px 6px; border-radius: 3px; font-weight: 600; margin-left: 4px; font-family: monospace; }
.z { font-family: monospace; color: #555; margin: 0 6px; }
.pg { color: #888; font-size: 12px; margin-left: 4px; }

/* Anomalies table */
.anom-z { font-family: monospace; font-weight: 600; }
.anom-table .num { font-variant-numeric: tabular-nums; }

/* Code */
code { font-family: 'Consolas', 'Monaco', monospace; background: #f4f4f4; padding: 1px 5px; border-radius: 3px; font-size: 12.5px; }

/* Analogs (preserved) */
.analogs h3 { margin-top: 18px; }
.analogs h4 { margin: 16px 0 8px 0; font-size: 13px; color: #555; text-transform: uppercase; letter-spacing: 0.4px; }
.analogs .state-list { list-style: none; padding: 0; display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; }
.analogs .state-list li { background: #f5f6f8; padding: 8px 12px; border-radius: 6px; font-size: 13px; }
.analog-table, .forward-table { width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 12px; }
.analog-table th, .analog-table td, .forward-table th, .forward-table td { padding: 7px 10px; text-align: left; border-bottom: 1px solid #eee; }
.analog-table th, .forward-table th { background: #fafafa; color: #555; font-weight: 500; font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.5px; }
.analog-table td.rank { font-weight: 700; color: #0066cc; }
.analog-table td.similarity { font-variant-numeric: tabular-nums; font-weight: 600; }
.analog-table td.episode { font-style: italic; color: #555; }
.forward-table td.num { text-align: right; font-variant-numeric: tabular-nums; }
.forward-table td.delta { font-weight: 600; }
.forward-table td.range { color: #777; font-size: 12px; font-variant-numeric: tabular-nums; }
.forward-table td.n-cell { text-align: center; color: #888; }

/* Journal (preserved) */
.journal-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.journal-table th, .journal-table td { padding: 7px 10px; text-align: left; border-bottom: 1px solid #eee; }
.journal-table th { background: #fafafa; color: #555; font-weight: 500; font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.5px; }
.journal-table td.j-date { font-variant-numeric: tabular-nums; color: #666; font-size: 12px; }
.journal-table td.j-topic { color: #555; }
.journal-table td.j-title { font-weight: 500; }
.journal-table td.j-status { font-size: 12px; color: #555; }

/* Footer */
.brief-footer { margin-top: 30px; padding: 24px 0; color: #555; font-size: 13px; }
.brief-footer h2 { font-size: 15px; margin-bottom: 8px; }
.brief-footer .generated { color: #888; font-size: 12px; margin-top: 16px; }
.brief-footer a { color: #0066cc; text-decoration: none; }
.brief-footer details.method { margin: 4px 0; padding: 6px 10px; background: #f7f7f7; border-radius: 4px; }
.brief-footer details.method summary { cursor: pointer; font-weight: normal; padding: 2px 0; }
.brief-footer details.method[open] { background: #fff; border: 1px solid #e0e0e0; }
.brief-footer details.method p { margin: 6px 0 0 16px; color: #444; line-height: 1.5; }

@media print {
  body { background: white; padding: 0; }
  .brief-section { box-shadow: none; }
}
"""


def _skeleton(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="bg">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="brief-main">
{body}
</div>
</body>
</html>
"""


# ─── Augment snapshot with derived spreads ──────────────────────

def _augment_with_derived(snapshot: dict[str, pd.Series]) -> dict[str, pd.Series]:
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


# ─── Main entry ──────────────────────────────────────────────────

def generate_weekly_briefing(
    snapshot: dict[str, pd.Series],
    output_path: str,
    today: Optional[date] = None,
    top_anomalies_n: int = 10,
    analog_bundle: Optional[Any] = None,
    journal_entries: Optional[list[Any]] = None,
    modules_results: Optional[list[dict]] = None,  # accepted for backwards compat, unused
) -> str:
    """Генерира HTML briefing (US-style: breadth + direction, без composite scores).

    Args:
        snapshot: {series_key: pd.Series}.
        output_path: file path за HTML.
        today: дата за header (default = днес).
        top_anomalies_n: брой top anomalies.
        analog_bundle: optional AnalogBundle (Phase 4).
        journal_entries: optional list of JournalEntry (Phase 5).
        modules_results: deprecated (за backwards compat) — игнорира се.

    Returns:
        Абсолютния път до записания HTML.
    """
    from analysis.breadth import compute_lens_breadth
    from analysis.divergence import compute_cross_lens_divergence
    from analysis.anomaly import compute_anomalies

    today = today or date.today()
    augmented = _augment_with_derived(snapshot)

    # Compute reports
    lens_reports = {}
    for lens in ALLOWED_LENSES:
        try:
            lens_reports[lens] = compute_lens_breadth(lens, augmented)
        except Exception:
            pass

    cross_report = compute_cross_lens_divergence(augmented)
    anomaly_report = compute_anomalies(augmented, z_threshold=2.0, top_n=top_anomalies_n)

    n_active_cross = sum(
        1 for p in cross_report.pairs
        if p.state in ("both_up", "both_down", "a_up_b_down", "a_down_b_up")
    )

    # Render sections
    body_parts = [
        _render_header(today, len(augmented), anomaly_report.total_flagged, n_active_cross),
        _render_executive(lens_reports, cross_report, anomaly_report),
        _render_cross_lens_pairs(cross_report),
    ]

    for lens in LENS_ORDER:
        if lens in lens_reports:
            body_parts.append(_render_lens_block(lens, lens_reports[lens], anomaly_report))

    body_parts.append(_render_top_anomalies(augmented, anomaly_report, top_anomalies_n))

    if analog_bundle is not None:
        body_parts.append(_render_analogs(analog_bundle))

    if journal_entries:
        body_parts.append(_render_journal(journal_entries))

    body_parts.append(_render_footer(today, len(augmented)))

    title = f"EA Macro Briefing — {today.isoformat()}"
    html = _skeleton(title, "\n".join(body_parts))

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return str(out_path.resolve())
