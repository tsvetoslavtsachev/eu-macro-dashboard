"""Tests за export/weekly_briefing.py."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from export.weekly_briefing import (
    _compute_overall,
    _render_header,
    _render_executive,
    _render_module_block,
    _render_anomalies,
    generate_weekly_briefing,
)


# ── Fixtures ────────────────────────────────────────────────────

def _module_result(name: str, composite: float = 60.0, regime: str = "ЗДРАВ") -> dict:
    return {
        "module": name,
        "label": f"Test {name}",
        "icon": "📊",
        "composite": composite,
        "regime": regime,
        "regime_color": "#00c853",
        "scores": {"primary": {"score": composite, "label": "Primary"}},
        "indicators": {f"{name.upper()}_X": {"name": "X", "current_value": 1.0,
                                              "score": composite, "percentile": 50.0,
                                              "z_score": 0.0, "yoy_change": 1.5,
                                              "last_date": "2026-03-01"}},
        "sparklines": {},
        "historical_context": {},
        "key_readings": [{"id": f"{name.upper()}_X", "label": "X-test",
                          "value": 1.0, "date": "2026-03-01", "yoy": 1.5,
                          "percentile": 50.0, "score": composite}],
    }


def _snapshot() -> dict[str, pd.Series]:
    idx = pd.date_range("2024-01-01", periods=24, freq="MS")
    return {
        "EA_UNRATE": pd.Series(np.linspace(7.5, 6.2, 24), index=idx),
        "EA_HICP_HEADLINE": pd.Series(np.linspace(0.5, 2.5, 24), index=idx),
    }


# ── _compute_overall ────────────────────────────────────────────

def test_compute_overall_weighted_average():
    results = [
        _module_result("inflation", composite=80.0),
        _module_result("labor", composite=60.0),
    ]
    composite, regime, color = _compute_overall(results)
    # inflation weight=0.30, labor weight=0.15 → weighted avg = 73.3
    assert composite == pytest.approx(73.3, rel=0.05)
    assert regime  # not empty
    assert color.startswith("#")


def test_compute_overall_empty():
    composite, regime, color = _compute_overall([])
    assert composite == 50.0


def test_compute_overall_unknown_module_zero_weight():
    """Модул със 0 weight в config не влиза в композита."""
    composite, _, _ = _compute_overall([
        _module_result("unknown_module", composite=99.0),
    ])
    assert composite == 50.0  # zero weight → fallback


# ── Section renderers ───────────────────────────────────────────

def test_render_header_contains_all_pieces():
    html = _render_header(date(2026, 4, 28), 65.5, "ЗДРАВ", "#69f0ae", 15)
    assert "65.5" in html
    assert "ЗДРАВ" in html
    assert "15 серии" in html
    assert "April 2026" in html or "2026" in html  # locale-dependent


def test_render_executive_lists_all_modules():
    results = [_module_result("labor"), _module_result("inflation")]
    html = _render_executive(results)
    assert "labor" in html.lower() or "Test labor" in html
    assert "Test inflation" in html
    assert "60.0" in html


def test_render_module_block_includes_indicators():
    result = _module_result("labor")
    html = _render_module_block(result)
    assert "Test labor" in html
    assert "X-test" in html  # key reading label


def test_render_anomalies_empty_message_when_no_data():
    html = _render_anomalies({}, top_n=10)
    # Без snapshot returns empty string
    assert html == ""


def test_render_anomalies_no_flagged_message():
    """Snapshot със свои серии но без |z|>2."""
    # Флатна серия — z-score = 0
    idx = pd.date_range("2024-01-01", periods=60, freq="MS")
    flat = pd.Series([5.0] * 60, index=idx)
    snap = {"EA_UNRATE": flat}
    html = _render_anomalies(snap, top_n=10)
    assert "Аномалии" in html
    assert "Няма серии" in html


# ── Full briefing generation ────────────────────────────────────

def test_generate_briefing_creates_html_file(tmp_path):
    output = tmp_path / "out" / "test_briefing.html"
    results = [
        _module_result("labor", composite=80.0, regime="ГОРЕЩ"),
        _module_result("inflation", composite=70.0, regime="ЕЛЕВИРАНА"),
    ]
    path = generate_weekly_briefing(
        snapshot=_snapshot(),
        modules_results=results,
        output_path=str(output),
        today=date(2026, 4, 28),
    )
    assert Path(path).exists()
    html = Path(path).read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html
    assert 'lang="bg"' in html
    assert "ГОРЕЩ" in html
    assert "ЕЛЕВИРАНА" in html
    # Composite section present
    assert "Композитен" in html or "score-value" in html


def test_generate_briefing_handles_zero_modules(tmp_path):
    output = tmp_path / "out" / "empty.html"
    path = generate_weekly_briefing(
        snapshot={},
        modules_results=[],
        output_path=str(output),
        today=date(2026, 4, 28),
    )
    assert Path(path).exists()
    html = Path(path).read_text(encoding="utf-8")
    # При empty модулите композитът трябва да е 50 (fallback)
    assert "50.0" in html


def test_generate_briefing_creates_output_directory(tmp_path):
    """Trябва автоматично да създаде липсващата директория."""
    output = tmp_path / "deeply" / "nested" / "out.html"
    generate_weekly_briefing(
        snapshot={},
        modules_results=[],
        output_path=str(output),
        today=date(2026, 4, 28),
    )
    assert output.exists()
