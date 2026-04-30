"""
export/weekly_briefing.py
=========================
HTML weekly briefing renderer за Eurozone — v1 (Phase 3).

Sections (BG):
  1. Header — дата, composite score, общ режим
  2. Executive Summary — 4-модулна таблица с lens scores и режими
  3. Per-module блокове — composite, key readings, sparkline placeholder
  4. Top Anomalies — серии с |z|>2 (от analysis/anomaly.py)
  5. Footer — методология + caveats

Phase 3.5+ ще добави:
  - Breadth per lens (когато peer_groups имат ≥2 серии)
  - Cross-lens divergence (когато CROSS_LENS_PAIRS се populate-нат)
  - Non-consensus highlights (когато се add-нат tagged серии)
  - WoW delta (след като state се persist-не)

Phase 4 — historical analogs.
Phase 5 — journal entries.

Self-contained HTML: inline CSS, без JS, без CDN.
"""
from __future__ import annotations
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from config import MODULE_WEIGHTS, MACRO_REGIMES
from core.scorer import get_regime


# ─── Utility ─────────────────────────────────────────────────────

def _fmt_score(s: Optional[float]) -> str:
    return f"{s:.1f}" if s is not None else "—"


def _fmt_pct(p: Optional[float]) -> str:
    return f"{p:.0f}" if p is not None else "—"


def _fmt_value(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, (int, float)):
        if abs(v) >= 1_000_000:
            return f"{v/1_000_000:.2f}M"
        if abs(v) >= 1000:
            return f"{v:,.0f}"
        return f"{v:.2f}"
    return str(v)


def _fmt_yoy(yoy: Optional[float], unit: str = "%") -> str:
    """Форматира YoY стойност. unit='pp' за rate series (HICP YoY, DFR),
    unit='%' за level series (price index, count)."""
    if yoy is None:
        return "—"
    sign = "+" if yoy >= 0 else ""
    return f"{sign}{yoy:.1f}{unit}"


# ─── Composite calculation ───────────────────────────────────────

def _compute_overall(modules_results: list[dict]) -> tuple[float, str, str]:
    """Връща (composite, regime_label, regime_color) от модулните резултати."""
    if not modules_results:
        return 50.0, "—", "#888"
    weighted = sum(
        r["composite"] * MODULE_WEIGHTS.get(r["module"], 0)
        for r in modules_results
    )
    total_w = sum(MODULE_WEIGHTS.get(r["module"], 0) for r in modules_results)
    composite = round(weighted / total_w, 1) if total_w else 50.0
    regime_label, regime_color = get_regime(composite, MACRO_REGIMES)
    return composite, regime_label, regime_color


# ─── Section renderers ───────────────────────────────────────────

def _render_header(today: date, composite: float, regime: str, color: str, n_series: int) -> str:
    return f"""
<header class="briefing-header">
  <h1>Седмичен макро брифинг — Еврозона</h1>
  <p class="meta">{today.strftime('%d %B %Y')} · {n_series} серии</p>
  <div class="overall-score" style="border-color: {color}">
    <div class="score-value" style="color: {color}">{composite:.1f}</div>
    <div class="score-label" style="color: {color}">{regime}</div>
    <div class="score-subtitle">Композитен макро score (0–100)</div>
  </div>
</header>
"""


def _render_executive(modules_results: list[dict]) -> str:
    rows = []
    for r in modules_results:
        score = r["composite"]
        regime = r["regime"]
        color = r["regime_color"]
        n_indic = len(r.get("indicators", {}))
        rows.append(f"""
        <tr>
          <td class="lens-name">{r['icon']} {r['label']}</td>
          <td class="score-cell" style="color: {color}; border-left: 4px solid {color}">{score:.1f}</td>
          <td class="regime-cell" style="color: {color}">{regime}</td>
          <td class="weight-cell">{MODULE_WEIGHTS.get(r['module'], 0)*100:.0f}%</td>
          <td class="n-cell">{n_indic}</td>
        </tr>
        """)
    return f"""
<section class="executive">
  <h2>Резюме по сектори</h2>
  <table class="lens-table">
    <thead><tr>
      <th>Сектор</th>
      <th>Score</th>
      <th>Режим</th>
      <th>Тегло</th>
      <th>Серии</th>
    </tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</section>
"""


def _render_module_block(result: dict) -> str:
    """Отделен блок за всеки модул със scores, key readings."""
    indicators_rows = []
    for kr in result.get("key_readings", []):
        indicators_rows.append(f"""
        <tr>
          <td class="ind-label">{kr['label']}</td>
          <td class="ind-value">{_fmt_value(kr['value'])}</td>
          <td class="ind-yoy">{_fmt_yoy(kr.get('yoy'), kr.get('yoy_unit', '%'))}</td>
          <td class="ind-pct">{_fmt_pct(kr['percentile'])}<sub>p</sub></td>
          <td class="ind-score">{_fmt_score(kr['score'])}</td>
          <td class="ind-date">{kr.get('date', '—')}</td>
        </tr>
        """)
    if not indicators_rows:
        indicators_rows = ['<tr><td colspan="6" class="empty">няма налични серии</td></tr>']

    color = result["regime_color"]

    return f"""
<section class="module-block">
  <h3>{result['icon']} {result['label']}</h3>
  <div class="module-summary">
    <span class="module-score" style="color: {color}">{result['composite']:.1f}</span>
    <span class="module-regime" style="color: {color}">{result['regime']}</span>
  </div>
  <table class="indicators-table">
    <thead><tr>
      <th>Индикатор</th>
      <th>Стойност</th>
      <th>YoY</th>
      <th>Percentile</th>
      <th>Score</th>
      <th>Дата</th>
    </tr></thead>
    <tbody>{''.join(indicators_rows)}</tbody>
  </table>
</section>
"""


def _render_analogs(bundle: Any) -> str:
    """Historical Analog секция (Phase 4). bundle = AnalogBundle или None."""
    if bundle is None:
        return ""

    current = bundle.current_state
    analogs = bundle.analogs

    if not analogs:
        return f"""
<section class="analogs">
  <h2>Исторически аналози</h2>
  <p class="empty">Недостатъчно данни за анализ (история {len(bundle.history_df)} наблюдения).</p>
</section>
"""

    # Header със current state summary
    raw = current.raw
    state_lines = []
    from analysis.macro_vector import DIM_LABELS_BG, DIM_UNITS
    for dim, val in raw.items():
        label = DIM_LABELS_BG.get(dim, dim)
        unit = DIM_UNITS.get(dim, "")
        state_lines.append(f"<li><strong>{label}:</strong> {val:.2f}{unit}</li>")

    # Analog table
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

    # Forward outcomes — група по horizon
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
                <th>Dimension</th>
                <th>Median value</th>
                <th>Median Δ</th>
                <th>Range</th>
                <th>N</th>
              </tr></thead>
              <tbody>{''.join(rows)}</tbody>
            </table>
            """)

    return f"""
<section class="analogs">
  <h2>Исторически аналози</h2>
  <p class="meta">As-of: {current.as_of.strftime('%Y-%m')} ·
     Cosine similarity срещу {len(bundle.history_df)}-месечна EA история (от 1999)</p>

  <h3>Текущ макро state (7 dimensions)</h3>
  <ul class="state-list">{''.join(state_lines)}</ul>

  <h3>Топ {len(analogs)} най-подобни исторически периода</h3>
  <table class="analog-table">
    <thead><tr>
      <th>Rank</th>
      <th>Period</th>
      <th>Similarity</th>
      <th>Episode</th>
    </tr></thead>
    <tbody>{''.join(analog_rows)}</tbody>
  </table>

  <h3>Forward outcomes (медиана през analog-ите)</h3>
  <p class="meta">Какво се случи в избраните периоди след аналог-датата.
     Range = [min, max] през analogs; N = брой analogs с налични данни.</p>
  {''.join(horizon_blocks) if horizon_blocks else '<p class="empty">Няма forward данни (analog-ите са твърде близо до края на историята).</p>'}
</section>
"""


_STATUS_LABELS_BG = {
    "open_question": "❓ Отворен въпрос",
    "hypothesis":    "🧪 Хипотеза",
    "finding":       "✓ Извод",
    "decision":      "◆ Решение",
}

_TOPIC_LABELS_BG = {
    "labor":       "Трудов пазар",
    "inflation":   "Инфлация",
    "credit":      "Кредит",
    "growth":      "Растеж",
    "analogs":     "Исторически аналози",
    "regime":      "Режими",
    "methodology": "Методология",
}


def _render_journal(entries: list) -> str:
    """Свързани journal entries — filter-нати relevant за текущия briefing."""
    if not entries:
        return ""

    rows = []
    for e in entries[:8]:  # cap at 8 most recent
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
<section class="journal">
  <h2>Свързани журнал бележки</h2>
  <p class="meta">{len(entries)} записа в журнала · показани {min(len(entries), 8)} най-скорошни</p>
  <table class="journal-table">
    <thead><tr>
      <th>Дата</th>
      <th>Тема</th>
      <th>Заглавие</th>
      <th>Статус</th>
      <th>Тагове</th>
    </tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</section>
"""


def _render_anomalies(snapshot: dict[str, pd.Series], top_n: int = 10) -> str:
    """Top anomalies — серии с |z|>2 от analysis/anomaly.py.

    Phase 7: добавени са две нови колони — стойност (raw) и Δ (промяна),
    форматирани с display-by-type logic от core/display.py.
    """
    from analysis.anomaly import compute_anomalies
    from catalog.series import SERIES_CATALOG
    from core.display import (
        change_kind, latest_change, fmt_change, fmt_value,
    )

    if not snapshot:
        return ""

    try:
        report = compute_anomalies(snapshot, top_n=top_n)
    except Exception as e:
        return f'<section><h2>Аномалии</h2><p class="empty">Грешка: {e}</p></section>'

    if not report.top:
        return f'<section><h2>Аномалии (|z|>2)</h2><p class="empty">Няма серии в опашката (|z|>2) сред {len(snapshot)} наблюдавани.</p></section>'

    rows = []
    for r in report.top:
        direction_arrow = "▲" if r.direction == "up" else "▼"
        new_extreme = " 🔥" if r.is_new_extreme else ""

        # Display-by-type: value + Δ
        meta = SERIES_CATALOG.get(r.series_key, {})
        kind = change_kind(r.series_key, meta)

        raw_series = snapshot.get(r.series_key)
        cur_val_str = "—"
        delta_str = "—"
        if raw_series is not None and not raw_series.empty:
            cur_val_str = fmt_value(raw_series.dropna().iloc[-1], digits=3)
            # Δ = month-over-month за monthly+ schedule, иначе weekly
            schedule = meta.get("release_schedule", "monthly")
            periods = {"weekly": 4, "monthly": 1, "quarterly": 1, "annually": 1}.get(schedule, 1)
            delta_val = latest_change(raw_series, kind, periods=periods)
            delta_str = fmt_change(delta_val, kind)

        rows.append(f"""
        <tr>
          <td class="anom-key">{r.series_key}</td>
          <td class="anom-value">{cur_val_str}</td>
          <td class="anom-delta">{delta_str}</td>
          <td class="anom-z">{direction_arrow} {r.z_score:+.2f}</td>
          <td class="anom-extreme">{new_extreme}</td>
        </tr>
        """)
    return f"""
<section class="anomalies">
  <h2>Аномалии (|z|&gt;2)</h2>
  <p class="meta">Топ {len(report.top)} от {report.total_flagged} флагнати серии · стойност+Δ форматирани display-by-type</p>
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


def _render_footer(today: date, n_series: int, n_modules: int) -> str:
    return f"""
<footer>
  <h2>Методология</h2>
  <details class="method">
    <summary><strong>Източници</strong></summary>
    <p>ECB Statistical Data Warehouse + Eurostat REST API (без API ключ).
    Adaptive cache TTL по release schedule.</p>
  </details>
  <details class="method">
    <summary><strong>Теми (5)</strong></summary>
    <p>labor, inflation, growth, credit, ECB — {n_modules} активни модула в текущия brief.
    Всяка тема има собствен composite (0-100), regime label и breakdown по peer_groups.</p>
  </details>
  <details class="method">
    <summary><strong>Score (0-100)</strong></summary>
    <p>Percentile rank спрямо 1999+ исторически разпределение (EMU era).
    Висок score = top-of-history. Invert flag обръща семантиката за "lower is better"
    series (UNRATE, M3 свиване, etc.).</p>
  </details>
  <details class="method">
    <summary><strong>Композитен macro score</strong></summary>
    <p>Weighted average по config.MODULE_WEIGHTS:
    inflation 30%, credit 20%, growth 20%, labor 15%, ECB 15%.</p>
  </details>
  <details class="method">
    <summary><strong>Sovereign spreads</strong></summary>
    <p>BTP-Bund (IT-DE), OAT-Bund (FR-DE) — derived в credit модул (Phase 1.5).
    BTP > 1.5pp = висок stress; > 0.8pp = елевиран.</p>
  </details>
  <details class="method">
    <summary><strong>Anchored zones (SPF)</strong></summary>
    <p>Empirical bands от 2003-2019 stable era (mean 1.91%, std 0.13pp, n=50):
    tight ±0.5σ, anchored ±1σ [1.78, 2.04], drifting ±2σ, de-anchored beyond.
    ECB target reference: 2.00%.</p>
  </details>
  <details class="method">
    <summary><strong>Caveats и ограничения</strong></summary>
    <p>v1 — {n_series} серии; пo-къса EA история (1999) от US (1970+);
    DG ECFIN sentiment series имат само 12mo (teibs010/020/030);
    SPF е quarterly (forward-fill за monthly join);
    yield curve = 10Y-2Y (10Y-3M не е в catalog).</p>
  </details>
  <p class="generated">Генериран на {today.strftime('%d %B %Y, %H:%M')} ·
     <a href="https://github.com/tsvetoslavtsachev/eu-macro-dashboard">eu-macro-dashboard</a></p>
</footer>
"""


# ─── Skeleton ────────────────────────────────────────────────────

_CSS = """
* { box-sizing: border-box; }
body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 24px;
       background: #f8f9fa; color: #1a1a1a; line-height: 1.5; }
.container { max-width: 1100px; margin: 0 auto; }

.briefing-header { background: white; border-radius: 12px; padding: 32px;
                   margin-bottom: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.briefing-header h1 { margin: 0 0 8px 0; font-size: 28px; }
.briefing-header .meta { color: #666; margin: 0 0 24px 0; font-size: 14px; }

.overall-score { border-left: 8px solid; padding: 16px 24px; }
.overall-score .score-value { font-size: 56px; font-weight: 700; line-height: 1; }
.overall-score .score-label { font-size: 22px; font-weight: 600; margin-top: 4px;
                              text-transform: uppercase; letter-spacing: 0.5px; }
.overall-score .score-subtitle { font-size: 13px; color: #666; margin-top: 8px; }

section { background: white; border-radius: 12px; padding: 24px;
          margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
section h2 { margin: 0 0 16px 0; font-size: 18px; border-bottom: 2px solid #eee;
             padding-bottom: 8px; }
section h3 { margin: 0 0 12px 0; font-size: 16px; }
section .meta { color: #666; font-size: 13px; margin-top: -8px; margin-bottom: 12px; }

table { width: 100%; border-collapse: collapse; font-size: 14px; }
th { text-align: left; padding: 10px 12px; background: #f0f1f3;
     font-weight: 600; font-size: 12px; text-transform: uppercase;
     letter-spacing: 0.3px; color: #555; }
td { padding: 10px 12px; border-bottom: 1px solid #eee; }
tr:last-child td { border-bottom: none; }
td.score-cell, td.module-score, .module-score { font-weight: 700; font-size: 15px;
                                                font-variant-numeric: tabular-nums; }
td.regime-cell, .module-regime { font-weight: 600; text-transform: uppercase;
                                  letter-spacing: 0.4px; font-size: 12px; }

.module-block .module-summary { padding: 12px 0; display: flex; gap: 16px; align-items: baseline; }
.module-block .module-score { font-size: 28px; }
.module-block .module-regime { font-size: 14px; }

.empty { color: #999; font-style: italic; padding: 16px; text-align: center; }

footer { padding: 24px; color: #555; font-size: 13px; }
footer h2 { font-size: 15px; margin-bottom: 8px; }
footer ul { margin: 0 0 16px 0; padding-left: 20px; }
footer li { margin-bottom: 4px; }
footer .generated { color: #888; font-size: 12px; }
footer a { color: #0066cc; text-decoration: none; }
footer a:hover { text-decoration: underline; }
footer details.method { margin: 4px 0; padding: 6px 10px; background: #f7f7f7; border-radius: 4px; }
footer details.method summary { cursor: pointer; font-weight: normal; padding: 2px 0; }
footer details.method[open] { background: #fff; border: 1px solid #e0e0e0; }
footer details.method p { margin: 6px 0 0 16px; color: #444; line-height: 1.5; }

td.anom-z { font-variant-numeric: tabular-nums; font-weight: 600; }
td.anom-value, td.anom-delta { font-variant-numeric: tabular-nums; text-align: right; }
td.anom-delta { font-weight: 600; }
.anom-table th.num, .indicators-table th.num, .forward-table th.num { text-align: right; }
td.ind-value, td.ind-yoy, td.ind-pct, td.ind-score { font-variant-numeric: tabular-nums;
                                                      text-align: right; }
td.ind-date { color: #666; font-size: 12px; }
sub { font-size: 0.7em; color: #777; }

.analogs h3 { margin-top: 24px; }
.analogs h4 { margin: 16px 0 8px 0; font-size: 13px; color: #555;
              text-transform: uppercase; letter-spacing: 0.4px; }
.analogs .state-list { list-style: none; padding: 0;
                       display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; }
.analogs .state-list li { background: #f5f6f8; padding: 8px 12px;
                          border-radius: 6px; font-size: 13px; }
.analog-table td.rank { font-weight: 700; color: #0066cc; }
.analog-table td.similarity { font-variant-numeric: tabular-nums; font-weight: 600; }
.analog-table td.episode { font-style: italic; color: #555; }
.forward-table td.num { text-align: right; font-variant-numeric: tabular-nums; }
.forward-table td.delta { font-weight: 600; }
.forward-table td.range { color: #777; font-size: 12px; font-variant-numeric: tabular-nums; }
.forward-table td.n-cell { text-align: center; color: #888; }

.journal-table td.j-date { font-variant-numeric: tabular-nums; color: #666; font-size: 13px; }
.journal-table td.j-topic { color: #555; }
.journal-table td.j-title { font-weight: 500; }
.journal-table td.j-status { font-size: 12px; color: #555; }
.journal-table td.j-tags code { background: #f0f1f3; padding: 2px 6px;
                                 border-radius: 3px; font-size: 11px; }

@media print {
  body { background: white; padding: 0; }
  section, .briefing-header { box-shadow: none; border: 1px solid #ddd; }
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
<div class="container">
{body}
</div>
</body>
</html>
"""


# ─── Main entry ──────────────────────────────────────────────────

def generate_weekly_briefing(
    snapshot: dict[str, pd.Series],
    modules_results: list[dict],
    output_path: str,
    today: Optional[date] = None,
    top_anomalies_n: int = 10,
    analog_bundle: Optional[Any] = None,    # Phase 4
    journal_entries: Optional[list[Any]] = None,  # Phase 5
) -> str:
    """Генерира HTML briefing.

    Args:
        snapshot: {series_key: pd.Series} — fetched от adapters
        modules_results: list от dict-ове върнати от modules.{labor,inflation,growth,ecb}.run
        output_path: file path за HTML
        today: дата за header (default = днес)
        top_anomalies_n: брой top anomalies в списъка

    Returns:
        Абсолютния път до записания HTML.
    """
    today = today or date.today()

    composite, regime, color = _compute_overall(modules_results)

    body_parts = [
        _render_header(today, composite, regime, color, len(snapshot)),
        _render_executive(modules_results),
    ]

    for r in modules_results:
        body_parts.append(_render_module_block(r))

    if analog_bundle is not None:
        body_parts.append(_render_analogs(analog_bundle))

    body_parts.append(_render_anomalies(snapshot, top_n=top_anomalies_n))

    if journal_entries:
        body_parts.append(_render_journal(journal_entries))

    body_parts.append(_render_footer(today, len(snapshot), len(modules_results)))

    html = _skeleton(
        title=f"EA Macro Briefing — {today.isoformat()}",
        body="\n".join(body_parts),
    )

    output_path = str(output_path)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path
