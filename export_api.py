"""
export_api.py
=============
Генерира два статични JSON файла за уеб дашборда:

  output/api/macro_state.json   — аналитичен слой (режими, аномалии, дивергенции)
  output/api/series_data.json   — времеви редове за графиките (последните N години)

Използва СЪЩИЯ pipeline като weekly_briefing.py — без нови изчисления,
само сериализира вече изчислените резултати в JSON формат.

Употреба:
  python export_api.py                  # от cache (без мрежа)
  python export_api.py --refresh        # force-fetch от ECB/Eurostat преди export
  python export_api.py --years 10       # последните 10 години в series_data
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

# ── path setup ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from catalog.series import SERIES_CATALOG, series_by_source
from catalog.polarity import polarity_for
from sources.ecb_adapter import EcbAdapter
from sources.eurostat_adapter import EurostatAdapter
from core.scorer import score_series
from core.display import change_kind, compute_change
from analysis.breadth import compute_lens_breadth
from analysis.health import lens_health
from analysis.divergence import compute_cross_lens_divergence, compute_intra_lens_divergence
from analysis.anomaly import compute_anomalies
from analysis.non_consensus import compute_non_consensus
from analysis.executive import compute_executive_summary

# ── константи ───────────────────────────────────────────────────────────────
OUTPUT_DIR = BASE_DIR / "output" / "api"
LENSES = ["labor", "growth", "inflation", "credit"]

# Кои серии да включим в series_data.json (ключови за графиките)
CHART_SERIES = {
    "labor": [
        "EA_UNRATE", "EA_LFS_EMP", "EA_EMPLOYMENT_EXP", "EA_COMP_PER_EMPLOYEE",
        "EA_UNEMP_YOUTH", "EA_EMPLOYMENT_PERSONS", "EA_WAGES_SALARIES",
        "EA_EMP_EXP_SERVICES",
    ],
    "inflation": [
        "EA_HICP_HEADLINE", "EA_HICP_CORE", "EA_HICP_SERVICES",
        "EA_HICP_ENERGY", "EA_HICP_FOOD", "EA_SPF_HICP_LT", "EA_PPI_INTERMEDIATE",
        "EA_SELLING_PRICE_EXP",
    ],
    "growth": [
        "EA_IP", "EA_RETAIL_VOL", "EA_BUILDING_PRODUCTION", "EA_PERMIT_DW",
        "EA_GDP_QOQ", "EA_ESI",
        "EA_CONSUMER_CONF", "EA_INDUSTRY_CONF", "EA_SERVICES_CONF",
        "EA_CONSTRUCTION_CONF", "EA_RETAIL_CONF",
        "EA_CAPACITY_UTIL", "EA_PRODUCTION_EXP",
    ],
    "credit": [
        "EA_CISS", "EA_M3_YOY", "EA_BANK_LOANS_NFC", "EA_BANK_LOANS_HH",
        "EA_BTP_BUND_SPREAD", "EA_OAT_BUND_SPREAD",
    ],
    "ecb": [
        "ECB_DFR", "ECB_MRO", "ECB_MLF", "ECB_BALANCE_SHEET",
        "EA_BUND_10Y", "EA_BUND_2Y",
    ],
}

ALL_CHART_SERIES = {s for series_list in CHART_SERIES.values() for s in series_list}


# ── JSON helpers ─────────────────────────────────────────────────────────────
def _clean(val: Any) -> Any:
    """Конвертира NaN/inf/Timestamp към JSON-safe типове."""
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        v = float(val)
        return None if (math.isnan(v) or math.isinf(v)) else v
    if isinstance(val, (np.bool_,)):
        return bool(val)
    if isinstance(val, pd.Timestamp):
        return str(val.date())
    return val


def _clean_dict(d: dict) -> dict:
    """Рекурсивно почиства речник от NaN/inf."""
    result = {}
    for k, v in d.items():
        if isinstance(v, dict):
            result[k] = _clean_dict(v)
        elif isinstance(v, list):
            result[k] = [_clean_dict(i) if isinstance(i, dict) else _clean(i) for i in v]
        else:
            result[k] = _clean(v)
    return result


def _safe_dump(obj: Any, path: Path) -> None:
    """Записва JSON с fallback за non-serializable типове."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)
    size_kb = path.stat().st_size / 1024
    print(f"  ✅ {path.name} ({size_kb:.1f} KB)")


def _build_snapshot(adapters: dict, force: bool = False) -> dict:
    """Сглобява {series_key: pd.Series} от всички adapter-и."""
    snapshot: dict = {}
    for source_name, adapter in adapters.items():
        specs = [
            {"key": s["_key"], "source_id": s["id"], "release_schedule": s["release_schedule"]}
            for s in series_by_source(source_name)
        ]
        if force:
            results = adapter.fetch_many(specs, force=True)
        else:
            results = adapter.get_snapshot([s["key"] for s in specs])
        snapshot.update(results)
    return snapshot


# ── macro_state.json builder ─────────────────────────────────────────────────
def build_macro_state(snapshot: dict, today: date) -> dict:
    """
    Изгражда macro_state.json — аналитичният слой.
    """
    print("  🧮 Изчислявам lens breadth...")
    lens_reports = {
        lens: compute_lens_breadth(lens, snapshot)
        for lens in LENSES
    }

    print("  🧮 Изчислявам cross-lens divergences...")
    cross_report = compute_cross_lens_divergence(snapshot)

    print("  🧮 Изчислявам anomalies...")
    anomaly_report = compute_anomalies(
        snapshot, z_threshold=2.0, top_n=15, lookback_years=5
    )

    print("  🧮 Изчислявам non-consensus...")
    nc_report = compute_non_consensus(snapshot)

    print("  🧮 Изчислявам executive summary...")
    exec_summary = compute_executive_summary(
        cross_report=cross_report,
        lens_reports=lens_reports,
        anomaly_report=anomaly_report,
        nc_report=nc_report,
    )

    # ── Intra-lens divergences ──────────────────────────────────────────────
    intra_divs = {}
    for lens in LENSES:
        report = compute_intra_lens_divergence(lens, snapshot)
        intra_divs[lens] = []
        for d in report.divergences:
            base = d.to_dict()
            diff = base.get("diff")
            if diff is None:
                state = "transition"
            elif diff > 0.2:
                state = "a_up_b_down"
            elif diff < -0.2:
                state = "a_down_b_up"
            else:
                state = "transition"
            base.update({
                "name_bg": f"{d.group_a} vs {d.group_b}",
                "pair_id": f"{lens}__{d.group_a}__vs__{d.group_b}",
                "slot_a_label": d.group_a,
                "slot_b_label": d.group_b,
                "state": state,
            })
            intra_divs[lens].append(base)

    # ── Per-lens summary ────────────────────────────────────────────────────
    # Score идва от единния health примитив (робастен z + полярност + 10-г.
    # прозорец) — виж ../macro-satellite/LENS_SCORING_METHODOLOGY.md.
    lenses_out = {}
    for lens in LENSES:
        exec_row = next(
            (r for r in exec_summary.lens_rows if r.lens == lens), None
        )
        h = lens_health(lens, snapshot)
        lenses_out[lens] = {
            "score": _clean(h["score"]),
            "health_z": _clean(h["health_z"]),
            "direction": h["direction"],
            "breadth_pct": _clean(h["breadth_pct"]),
            "anomalies_count": exec_row.anomaly_count if exec_row else 0,
            "new_extreme_count": exec_row.new_extreme_count if exec_row else 0,
            "intra_divergences": intra_divs.get(lens, []),
        }

    # ── Top anomalies ───────────────────────────────────────────────────────
    top_anomalies = []
    for a in anomaly_report.top[:10]:
        top_anomalies.append({
            "series_id": a.series_key,
            "name_bg": a.series_name_bg,
            "lens": a.lens,
            "peer_group": a.peer_group,
            "z_score": _clean(a.z_score),
            "direction": a.direction,
            "current_value": _clean(a.last_value),
            "last_date": a.last_date,
            "is_new_extreme": a.is_new_extreme,
            "new_extreme_direction": a.new_extreme_direction,
            "narrative_hint": a.narrative_hint,
        })

    # ── Cross-lens divergences ───────────────────────────────────────────────
    cross_divs = []
    for pair in cross_report.pairs:
        cross_divs.append({
            "pair_id": pair.pair_id,
            "name_bg": pair.name_bg,
            "question_bg": pair.question_bg,
            "state": pair.state,
            "interpretation": pair.interpretation,
            "slot_a_label": pair.slot_a_label,
            "slot_b_label": pair.slot_b_label,
            "breadth_a": _clean(pair.breadth_a),
            "breadth_b": _clean(pair.breadth_b),
        })

    # ── Non-consensus highlights ─────────────────────────────────────────────
    nc_highlights = []
    for r in nc_report.highlights[:8]:
        nc_highlights.append({
            "series_id": r.series_key,
            "name_bg": SERIES_CATALOG.get(r.series_key, {}).get("name_bg", r.series_key),
            "lens": SERIES_CATALOG.get(r.series_key, {}).get("lens", []),
            "signal_strength": r.signal_strength,
            "percentile": _clean(getattr(r, "percentile", None)),
            "z_score": _clean(r.z_score),
            "direction": getattr(r, "direction", None) or getattr(r, "peer_direction", None),
        })

    return _clean_dict({
        "region": "EA",
        "as_of_date": str(today),
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "executive_summary": {
            "regime_key": exec_summary.regime_label,
            "regime_label_bg": exec_summary.regime_label_bg,
            "css_class": exec_summary.regime_css_class,
            "narrative": exec_summary.narrative_bg,
            "supporting_signals": exec_summary.supporting_signals,
            "primary_driver": exec_summary.primary_driver,
        },
        "lenses": lenses_out,
        "top_anomalies": top_anomalies,
        "cross_lens_divergences": cross_divs,
        "non_consensus_highlights": nc_highlights,
    })


# ── series_data.json builder ─────────────────────────────────────────────────
def build_series_data(snapshot: dict, today: date, years: int = 7) -> dict:
    """
    Изгражда series_data.json — времеви редове за графиките.
    Включва само CHART_SERIES, последните `years` години.
    """
    cutoff = pd.Timestamp(today) - pd.DateOffset(years=years)
    series_out = {}

    for series_id in ALL_CHART_SERIES:
        if series_id not in snapshot:
            continue

        raw_series = snapshot[series_id]
        meta = SERIES_CATALOG.get(series_id, {})

        filtered = raw_series[raw_series.index >= cutoff].dropna()
        if filtered.empty:
            continue

        lens_list = meta.get("lens", [])
        primary_lens = lens_list[0] if lens_list else "other"

        kind = change_kind(series_id, meta)
        transform = meta.get("transform", "level")

        # Прилагаме transform: за nominalно растящи серии каталогът декларира
        # transform=yoy_pct/qoq_pct → графиката и percentile се правят върху
        # процентната промяна, не върху суровото ниво. Иначе percentile
        # винаги клони към 100 за растящи серии.
        if transform == "yoy_pct":
            chart_periods = 12
        elif transform == "qoq_pct":
            chart_periods = 3
        else:
            chart_periods = None

        if chart_periods is not None:
            try:
                display_series = compute_change(raw_series, "percent", periods=chart_periods).dropna()
            except Exception:
                display_series = raw_series
        else:
            display_series = raw_series

        display_filtered = display_series[display_series.index >= cutoff].dropna()
        if display_filtered.empty:
            continue

        latest_val = float(display_filtered.iloc[-1])
        latest_date = str(display_filtered.index[-1].date())

        if chart_periods is not None:
            yoy_val = None
        else:
            try:
                changes = compute_change(filtered, kind, periods=12)
                yoy_val = float(changes.iloc[-1]) if not changes.empty and not pd.isna(changes.iloc[-1]) else None
            except Exception:
                yoy_val = None

        dates = [str(d.date()) for d in display_filtered.index]
        values = [_clean(v) for v in display_filtered.values]

        # Единният health примитив — робастен z спрямо 10-г. плъзгаща норма върху
        # каталожно-трансформираната серия + полярност. score=50 е близката норма;
        # percentile е trailing-10г ранг (вече НЕ клони към 100 за растящите серии).
        score_data = score_series(
            raw_series, name=series_id,
            is_rate=bool(meta.get("is_rate", False)),
            transform=transform,
            polarity=polarity_for(series_id, primary_lens),
        )

        series_out[series_id] = {
            "meta": {
                "name_bg": meta.get("name_bg", series_id),
                "name_en": meta.get("name_en", series_id),
                "lens": primary_lens,
                "lens_all": lens_list,
                "peer_group": meta.get("peer_group", ""),
                "transform": meta.get("transform", "level"),
                "is_rate": meta.get("is_rate", False),
                "change_kind": kind,
                "release_schedule": meta.get("release_schedule", "monthly"),
                "narrative_hint": meta.get("narrative_hint", ""),
            },
            "latest": {
                "date": latest_date,
                "value": _clean(latest_val),
                "yoy_change": _clean(yoy_val),
                "percentile": _clean(score_data.get("percentile")),
                "z_score": _clean(score_data.get("z_score")),
                "health_z": _clean(score_data.get("health_z")),
                "score": _clean(score_data.get("score")),
                "regime": score_data.get("regime_label"),
            },
            "chart": {
                "dates": dates,
                "values": values,
            },
        }

    return _clean_dict({
        "region": "EA",
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "years_included": years,
        "series_count": len(series_out),
        "series": series_out,
    })


# ── main ─────────────────────────────────────────────────────────────────────
def main(args) -> None:
    today = date.today()

    print("\n" + "=" * 60)
    print("  Export API JSON  --  eu-macro-dashboard")
    print("=" * 60)
    print(f"  {datetime.now().strftime('%A, %d %B %Y · %H:%M')}")
    print("=" * 60 + "\n")

    adapters = {
        "ecb": EcbAdapter(),
        "eurostat": EurostatAdapter(),
    }

    if args.refresh:
        print("Refresh на ECB/Eurostat данни (force)...")
        for source_name, adapter in adapters.items():
            specs = [
                {"key": s["_key"], "source_id": s["id"], "release_schedule": s["release_schedule"]}
                for s in series_by_source(source_name)
            ]
            adapter.fetch_many(specs, force=True)
        print()

    snapshot = _build_snapshot(adapters, force=False)
    print(f"Snapshot: {len(snapshot)}/{len(SERIES_CATALOG)} серии с данни\n")

    if len(snapshot) < 5:
        print("Твърде малко серии в snapshot — вероятно cache е празен.")
        print("Стартирай с --refresh за да изтеглиш данни.\n")
        sys.exit(1)

    print("Генерирам macro_state.json...")
    macro_state = build_macro_state(snapshot, today)
    _safe_dump(macro_state, OUTPUT_DIR / "macro_state.json")

    print("\nГенерирам series_data.json...")
    series_data = build_series_data(snapshot, today, years=args.years)
    _safe_dump(series_data, OUTPUT_DIR / "series_data.json")

    print(f"\nDone! Файловете са в: {OUTPUT_DIR}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Export EA macro analysis to JSON API files for web dashboard."
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force-fetch всички ECB/Eurostat серии преди export.",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=7,
        help="Колко години история да включим в series_data.json (default: 7).",
    )
    args = parser.parse_args()
    main(args)
