"""Tests за export/weekly_briefing.py — US-style structure (rewrite)."""
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

from analysis.breadth import compute_lens_breadth
from analysis.divergence import compute_cross_lens_divergence
from analysis.anomaly import compute_anomalies
from catalog.series import ALLOWED_LENSES
from export.weekly_briefing import (
    generate_weekly_briefing,
    _augment_with_derived,
    _derive_regime,
    _render_header,
    _render_executive,
    _render_cross_lens_pairs,
    _render_lens_block,
    _render_top_anomalies,
    _render_footer,
    _fmt_breadth_pct,
)


# ── Fixtures ────────────────────────────────────────────────────

def monthly(values, end="2026-04-01"):
    idx = pd.date_range(end=end, periods=len(values), freq="MS")
    return pd.Series(values, index=idx)


def quarterly(values, end="2026-04-01"):
    idx = pd.date_range(end=end, periods=len(values), freq="QS")
    return pd.Series(values, index=idx)


@pytest.fixture
def sample_snapshot():
    np.random.seed(42)
    return {
        "EA_UNRATE": monthly(np.linspace(8.0, 6.5, 60)),
        "EA_LFS_EMP": quarterly(np.linspace(70.0, 75.0, 20)),
        "EA_EMPLOYMENT_EXP": monthly(np.linspace(95.0, 92.0, 12)),
        "EA_COMP_PER_EMPLOYEE": quarterly(np.linspace(400_000, 500_000, 20)),
        "EA_HICP_HEADLINE": monthly(np.linspace(0.5, 2.5, 60)),
        "EA_HICP_CORE": monthly(np.linspace(0.8, 2.3, 60)),
        "EA_HICP_SERVICES": monthly(np.linspace(1.0, 3.5, 60)),
        "EA_HICP_ENERGY": monthly(np.linspace(-1.0, 2.0, 60)),
        "EA_HICP_FOOD": monthly(np.linspace(0.5, 3.0, 60)),
        "EA_SPF_HICP_LT": quarterly([2.0] * 20),
        "EA_PPI_INTERMEDIATE": monthly(np.linspace(100, 130, 60)),
        "EA_IP": monthly(np.linspace(95, 105, 60)),
        "EA_RETAIL_VOL": monthly(np.linspace(95, 110, 60)),
        "EA_BUILDING_PRODUCTION": monthly(np.linspace(95, 100, 60)),
        "EA_PERMIT_DW": monthly(np.linspace(100, 95, 60)),
        "EA_GDP_QOQ": quarterly(np.linspace(40_000, 42_000, 20)),
        "EA_ESI": monthly(np.full(12, 95.0)),
        "EA_INDUSTRY_CONF": monthly(np.full(12, -5.0)),
        "EA_CONSTRUCTION_CONF": monthly(np.full(12, -5.0)),
        "EA_RETAIL_CONF": monthly(np.full(12, -3.0)),
        "EA_CONSUMER_CONF": monthly(np.linspace(-15, -10, 60)),
        "EA_CISS": monthly(np.linspace(0.05, 0.15, 60)),
        "EA_M3_YOY": monthly(np.linspace(8.0, 3.0, 60)),
        "EA_BANK_LOANS_NFC": monthly(np.linspace(2.0, 1.0, 60)),
        "EA_BANK_LOANS_HH": monthly(np.linspace(2.5, 1.5, 60)),
        "EA_BUND_10Y": monthly(np.linspace(0.5, 3.0, 60)),
        "EA_BUND_2Y": monthly(np.linspace(0.0, 2.0, 60)),
        "IT_10Y": monthly(np.linspace(2.0, 4.5, 60)),
        "FR_10Y": monthly(np.linspace(1.0, 3.5, 60)),
        "DE_10Y": monthly(np.linspace(0.5, 2.5, 60)),
        "ECB_DFR": monthly(np.linspace(0.0, 2.0, 60)),
        "ECB_MRO": monthly(np.linspace(0.5, 2.5, 60)),
        "ECB_MLF": monthly(np.linspace(1.0, 3.0, 60)),
        "ECB_BALANCE_SHEET": monthly(np.linspace(2_000_000, 7_000_000, 60)),
    }


@pytest.fixture
def augmented(sample_snapshot):
    return _augment_with_derived(sample_snapshot)


@pytest.fixture
def lens_reports(augmented):
    return {lens: compute_lens_breadth(lens, augmented) for lens in ALLOWED_LENSES}


@pytest.fixture
def cross_report(augmented):
    return compute_cross_lens_divergence(augmented)


@pytest.fixture
def anomaly_report(augmented):
    return compute_anomalies(augmented, z_threshold=2.0, top_n=10)


# ── Helpers ─────────────────────────────────────────────────────

def test_fmt_breadth_pct():
    assert _fmt_breadth_pct(0.5) == "50%"
    assert _fmt_breadth_pct(None) == "—"
    assert _fmt_breadth_pct(float("nan")) == "—"


def test_augment_with_derived(sample_snapshot):
    aug = _augment_with_derived(sample_snapshot)
    assert "EA_BTP_BUND_SPREAD" in aug
    assert "EA_OAT_BUND_SPREAD" in aug


def test_augment_no_de_returns_unchanged():
    snap = {"IT_10Y": monthly([5.0])}
    aug = _augment_with_derived(snap)
    assert "EA_BTP_BUND_SPREAD" not in aug


# ── Regime derivation ──────────────────────────────────────────

def test_derive_regime_returns_label_css_narrative(cross_report):
    label, css, narrative, driver = _derive_regime(cross_report)
    assert isinstance(label, str) and label
    assert css.startswith("regime-")
    assert isinstance(narrative, str) and len(narrative) > 10


# ── Section renderers ──────────────────────────────────────────

def test_render_header_includes_kpis():
    html = _render_header(date(2026, 4, 30), 34, 6, 2)
    assert "34" in html
    assert "kpi" in html
    assert "Седмичен макро брифинг" in html
    # No composite score in header (US-style)
    assert "score-value" not in html


def test_render_executive_no_composite_scores(lens_reports, cross_report, anomaly_report):
    html = _render_executive(lens_reports, cross_report, anomaly_report)
    assert "regime-badge" in html
    assert "regime-table" in html
    assert "Breadth" in html
    # NO composite score columns
    assert ">Score<" not in html
    # Direction badges present
    assert "dir-badge" in html


def test_render_cross_lens_pairs_has_six_cards(cross_report):
    html = _render_cross_lens_pairs(cross_report)
    assert html.count('class="pair-card"') == 6
    assert "Cross-Lens Divergence" in html
    assert "pair-state" in html


def test_render_lens_block_has_breadth_table(lens_reports, anomaly_report):
    html = _render_lens_block("inflation", lens_reports["inflation"], anomaly_report)
    assert "breadth-table" in html
    assert "peer group" in html.lower()
    assert "Инфлация" in html


def test_render_top_anomalies_table(sample_snapshot, anomaly_report):
    html = _render_top_anomalies(sample_snapshot, anomaly_report, top_n=10)
    assert "Top Anomalies" in html
    if anomaly_report.total_flagged > 0:
        assert "anom-z" in html


def test_render_footer_has_methodology():
    html = _render_footer(date(2026, 4, 30), 34)
    assert "Методология" in html
    assert "details" in html
    assert "Breadth" in html


# ── Full briefing generation ───────────────────────────────────

def test_generate_briefing_creates_html_file(tmp_path, sample_snapshot):
    output = tmp_path / "out" / "test_briefing.html"
    path = generate_weekly_briefing(
        snapshot=sample_snapshot,
        output_path=str(output),
        today=date(2026, 4, 28),
    )
    assert Path(path).exists()
    html = Path(path).read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html
    assert 'lang="bg"' in html


def test_generate_briefing_no_composite_in_output(tmp_path, sample_snapshot):
    """User feedback: composite scores са излишни в HTML-а."""
    output = tmp_path / "ctx.html"
    generate_weekly_briefing(
        snapshot=sample_snapshot,
        output_path=str(output),
        today=date(2026, 4, 28),
    )
    html = output.read_text(encoding="utf-8")
    assert "Композитен макро score" not in html
    assert "Композитен Macro Score" not in html
    # NO module-block sections (per-lens score blocks)
    assert 'class="module-block"' not in html


def test_generate_briefing_includes_us_style_sections(tmp_path, sample_snapshot):
    output = tmp_path / "ctx.html"
    generate_weekly_briefing(
        snapshot=sample_snapshot,
        output_path=str(output),
        today=date(2026, 4, 28),
    )
    html = output.read_text(encoding="utf-8")
    assert 'class="kpi"' in html
    assert "regime-badge" in html
    assert html.count('class="pair-card"') == 6
    assert html.count('class="brief-section lens-block"') == 5
    assert 'class="breadth-table"' in html


def test_generate_briefing_handles_empty_snapshot(tmp_path):
    output = tmp_path / "out" / "empty.html"
    path = generate_weekly_briefing(
        snapshot={},
        output_path=str(output),
        today=date(2026, 4, 28),
    )
    assert Path(path).exists()


def test_generate_briefing_creates_output_directory(tmp_path, sample_snapshot):
    output = tmp_path / "deeply" / "nested" / "out.html"
    generate_weekly_briefing(
        snapshot=sample_snapshot,
        output_path=str(output),
        today=date(2026, 4, 28),
    )
    assert output.exists()


def test_generate_briefing_modules_results_param_ignored(tmp_path, sample_snapshot):
    """Backwards-compat: modules_results parameter accepted but ignored."""
    output = tmp_path / "ctx.html"
    generate_weekly_briefing(
        snapshot=sample_snapshot,
        modules_results=[{"composite": 99.0}],  # ignored
        output_path=str(output),
        today=date(2026, 4, 28),
    )
    html = output.read_text(encoding="utf-8")
    # 99.0 от modules_results не трябва да се появи в HTML
    assert "99.0" not in html
