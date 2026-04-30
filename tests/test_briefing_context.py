"""Tests за export/briefing_context.py — US-style structure (Phase 9 rewrite)."""
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
from export.briefing_context import (
    augment_snapshot_with_derived,
    generate_briefing_context,
    _render_header,
    _render_executive_summary,
    _render_themes,
    _render_cross_lens,
    _render_cross_spreads,
    _render_anomalies,
    _render_methodology_compact,
    _yoy_pct,
    _percentile_5y,
)


# ── Fixtures ──────────────────────────────────────────────────

def monthly(values, end="2026-04-01"):
    idx = pd.date_range(end=end, periods=len(values), freq="MS")
    return pd.Series(values, index=idx)


def quarterly(values, end="2026-04-01"):
    idx = pd.date_range(end=end, periods=len(values), freq="QS")
    return pd.Series(values, index=idx)


@pytest.fixture
def sample_snapshot():
    """Comprehensive snapshot за integration tests."""
    np.random.seed(42)
    return {
        "EA_UNRATE": monthly(np.linspace(8.0, 6.5, 60)),
        "EA_LFS_EMP": quarterly(np.linspace(70.0, 75.0, 20)),
        "EA_EMPLOYMENT_EXP": monthly(np.linspace(95.0, 98.0, 12)),
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
        "EA_ESI": monthly(np.full(12, 95.0) + np.random.randn(12) * 2),
        "EA_INDUSTRY_CONF": monthly(np.full(12, -5.0) + np.random.randn(12)),
        "EA_CONSTRUCTION_CONF": monthly(np.full(12, -5.0) + np.random.randn(12)),
        "EA_RETAIL_CONF": monthly(np.full(12, -3.0) + np.random.randn(12)),
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
def augmented_snapshot(sample_snapshot):
    return augment_snapshot_with_derived(sample_snapshot)


@pytest.fixture
def lens_reports(augmented_snapshot):
    return {lens: compute_lens_breadth(lens, augmented_snapshot) for lens in ALLOWED_LENSES}


@pytest.fixture
def cross_report(augmented_snapshot):
    return compute_cross_lens_divergence(augmented_snapshot)


@pytest.fixture
def anomaly_report(augmented_snapshot):
    return compute_anomalies(augmented_snapshot, z_threshold=2.0, top_n=10)


# ── Augmentation ──────────────────────────────────────────────

def test_augment_snapshot_adds_btp_oat_spreads(sample_snapshot):
    aug = augment_snapshot_with_derived(sample_snapshot)
    assert "EA_BTP_BUND_SPREAD" in aug
    assert "EA_OAT_BUND_SPREAD" in aug
    # Latest BTP = IT.last - DE.last = 4.5 - 2.5 = 2.0
    assert aug["EA_BTP_BUND_SPREAD"].iloc[-1] == pytest.approx(2.0, abs=0.01)


def test_augment_snapshot_no_de_returns_unchanged():
    snap = {"IT_10Y": monthly([5.0])}
    aug = augment_snapshot_with_derived(snap)
    assert "EA_BTP_BUND_SPREAD" not in aug


# ── Section renderers ─────────────────────────────────────────

def test_render_header_includes_required_metadata(sample_snapshot, lens_reports, cross_report, anomaly_report):
    text = _render_header(date(2026, 4, 30), lens_reports, cross_report, anomaly_report)
    assert "Briefing Context" in text
    assert "2026-04-30" in text
    assert "Eurozone" in text
    assert "Брой теми:" in text
    assert "Cross-lens двойки:" in text
    assert "Аномалии" in text


def test_render_executive_no_scores(lens_reports, anomaly_report):
    """Executive Summary трябва да показва direction + breadth %, БЕЗ composite scores."""
    text = _render_executive_summary(lens_reports, anomaly_report)
    assert "Executive Summary" in text
    assert "| Тема |" in text
    assert "Посока" in text
    assert "Breadth" in text
    # Не трябва да има composite score numbers (X.X / X.X format)
    assert "Composite" not in text
    assert "regime" not in text.lower()


def test_render_themes_uses_peer_group_tables(lens_reports):
    text = _render_themes(lens_reports)
    assert "Темите по peer group" in text
    # Trябва да има peer_group rows за всяка lens
    assert "Peer group" in text
    assert "breadth ↑" in text
    # И петте теми
    for label in ["Пазар на труда", "Инфлация", "Растеж", "Финансови условия", "ЕЦБ"]:
        assert label in text


def test_render_cross_lens_lists_all_5_states(cross_report):
    text = _render_cross_lens(cross_report)
    assert "Cross-Lens Divergence" in text
    # Всички 6 pair names
    for pair_name in ["Стагфлационен тест", "Трансмисия на ЕЦБ", "Фрагментационен риск",
                       "Закотвеност", "Pipeline", "Очаквания срещу твърди"]:
        assert pair_name in text
    # 5-state interpretations присъстват
    assert "Всички възможни състояния" in text
    assert "both_up" in text
    assert "both_down" in text
    assert "a_up_b_down" in text
    assert "a_down_b_up" in text
    assert "transition" in text


def test_render_cross_lens_marks_active_state(cross_report):
    text = _render_cross_lens(cross_report)
    # Поне един pair трябва да има "← АКТИВНО" marker
    assert "АКТИВНО" in text


def test_render_cross_spreads_includes_real_dfr(augmented_snapshot):
    text = _render_cross_spreads(augmented_snapshot, date(2026, 4, 30), 5)
    assert "Cross-spreads" in text
    assert "Real DFR" in text
    assert "DFR" in text and "SPF" in text


def test_render_cross_spreads_includes_real_wages(augmented_snapshot):
    text = _render_cross_spreads(augmented_snapshot, date(2026, 4, 30), 5)
    assert "Real wages" in text


def test_render_cross_spreads_includes_real_lending(augmented_snapshot):
    text = _render_cross_spreads(augmented_snapshot, date(2026, 4, 30), 5)
    assert "Real bank lending" in text


def test_render_cross_spreads_includes_yield_curve(augmented_snapshot):
    text = _render_cross_spreads(augmented_snapshot, date(2026, 4, 30), 5)
    assert "Yield curve" in text
    assert "Bund 10Y-2Y" in text


def test_render_cross_spreads_includes_sovereign_spreads(augmented_snapshot):
    text = _render_cross_spreads(augmented_snapshot, date(2026, 4, 30), 5)
    assert "BTP-Bund" in text
    assert "OAT-Bund" in text
    assert "fragmentation" in text.lower()
    assert "TPI" in text


def test_render_cross_spreads_includes_anchored_band(augmented_snapshot):
    text = _render_cross_spreads(augmented_snapshot, date(2026, 4, 30), 5)
    assert "Anchored band" in text
    assert "EA_SPF_HICP_LT" in text
    assert "stable era 2003-2019" in text


def test_render_cross_spreads_includes_pipeline(augmented_snapshot):
    text = _render_cross_spreads(augmented_snapshot, date(2026, 4, 30), 5)
    assert "PPI Intermediate" in text
    assert "HICP Core" in text


def test_render_anomalies_with_extreme(augmented_snapshot, anomaly_report):
    text = _render_anomalies(anomaly_report, augmented_snapshot, date(2026, 4, 30), 5)
    assert "Top Anomalies" in text


def test_render_methodology_has_required_sections():
    text = _render_methodology_compact()
    assert "Методология" in text
    assert "Breadth" in text
    assert "z-score" in text
    assert "Anchored band" in text


# ── Helpers ───────────────────────────────────────────────────

def test_yoy_pct_with_monthly_data():
    s = monthly(np.linspace(100, 110, 24))  # 10% growth over 24 months
    yoy = _yoy_pct(s)
    assert yoy is not None
    assert yoy > 0  # positive growth


def test_yoy_pct_returns_none_for_short_series():
    s = monthly([100.0, 101.0])
    yoy = _yoy_pct(s)
    assert yoy is None


def test_percentile_5y(augmented_snapshot):
    pct = _percentile_5y(augmented_snapshot["EA_HICP_CORE"])
    assert pct is not None
    assert 0 <= pct <= 100


# ── End-to-end ────────────────────────────────────────────────

def test_generate_briefing_context_writes_file(
    tmp_path, augmented_snapshot, lens_reports, cross_report, anomaly_report,
):
    output = tmp_path / "test_brief_ctx.md"
    text = generate_briefing_context(
        snapshot=augmented_snapshot,
        lens_reports=lens_reports,
        cross_report=cross_report,
        anomaly_report=anomaly_report,
        today=date(2026, 4, 30),
        output_path=output,
    )
    assert Path(text).exists()
    written = Path(text).read_text(encoding="utf-8")
    assert len(written) > 2000  # substantive content

    # Sanity-check sections present
    assert "## 1. Executive Summary" in written
    assert "## 1.5 Cross-spreads" in written
    assert "## 2. Темите по peer group" in written
    assert "## 3. Cross-Lens Divergence" in written
    assert "## 4. Top Anomalies" in written
    assert "## 5. Методология" in written


def test_generate_briefing_context_creates_parent_dir(
    tmp_path, augmented_snapshot, lens_reports, cross_report, anomaly_report,
):
    nested = tmp_path / "subdir" / "ctx.md"
    generate_briefing_context(
        snapshot=augmented_snapshot,
        lens_reports=lens_reports,
        cross_report=cross_report,
        anomaly_report=anomaly_report,
        today=date(2026, 4, 30),
        output_path=nested,
    )
    assert nested.exists()


def test_generate_briefing_context_no_composite_scores_in_output(
    tmp_path, augmented_snapshot, lens_reports, cross_report, anomaly_report,
):
    """User feedback: composite scores са излишни. Output не трябва да ги съдържа."""
    output = tmp_path / "ctx.md"
    text = generate_briefing_context(
        snapshot=augmented_snapshot,
        lens_reports=lens_reports,
        cross_report=cross_report,
        anomaly_report=anomaly_report,
        today=date(2026, 4, 30),
        output_path=output,
    )
    # NO composite score values като "75.0", "Composite", "regime"
    assert "Composite Macro Score" not in text
    assert "| Composite |" not in text  # старата таблица header
