"""Tests за export/briefing_context.py — Phase 9 markdown export."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from export.briefing_context import (
    generate_briefing_context,
    render_header,
    render_executive,
    render_themes,
    render_cross_lens,
    render_cross_spreads,
    render_anomalies,
    render_series_fact_cards,
    render_methodology,
    _augment_snapshot_with_derived,
    _peer_group_direction,
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
    return {
        "EA_UNRATE": monthly(np.linspace(8.0, 6.5, 60)),
        "EA_HICP_HEADLINE": monthly(np.linspace(0.5, 2.5, 60)),
        "EA_HICP_CORE": monthly(np.linspace(0.8, 2.8, 60)),
        "EA_HICP_SERVICES": monthly(np.linspace(1.0, 3.5, 60)),
        "EA_HICP_ENERGY": monthly(np.linspace(-1.0, 2.0, 60)),
        "EA_HICP_FOOD": monthly(np.linspace(0.5, 3.0, 60)),
        "EA_IP": monthly(np.linspace(95, 105, 60)),
        "EA_RETAIL_VOL": monthly(np.linspace(95, 110, 60)),
        "EA_BUILDING_PRODUCTION": monthly(np.linspace(95, 100, 60)),
        "EA_GDP_QOQ": quarterly(np.linspace(40000, 42000, 20)),
        "EA_ESI": monthly([95.0] * 60),
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
        "ECB_BALANCE_SHEET": monthly(np.linspace(2_000_000, 7_000_000, 60)),
        "EA_SPF_HICP_LT": quarterly([2.0] * 20),
        "EA_PPI_INTERMEDIATE": monthly(np.linspace(100, 130, 60)),
        "EA_COMP_PER_EMPLOYEE": quarterly(np.linspace(400_000, 500_000, 20)),
    }


@pytest.fixture
def sample_modules_results():
    return [
        {"module": "labor",     "label": "Пазар на труда", "icon": "👷",
         "composite": 75.0, "regime": "ЗДРАВ", "indicators": {
             "EA_UNRATE": {"score": 80.0, "z_score": 1.7, "name": "UNRATE"},
         }},
        {"module": "inflation", "label": "Инфлация", "icon": "🔥",
         "composite": 65.0, "regime": "ЕЛЕВИРАНА", "indicators": {
             "EA_HICP_CORE": {"score": 70.0, "z_score": 1.6, "name": "Core"},
         }},
        {"module": "growth",    "label": "Растеж и активност", "icon": "📈",
         "composite": 50.0, "regime": "СТАГНАЦИЯ", "indicators": {}},
        {"module": "credit",    "label": "Финансови условия и кредит", "icon": "🏛",
         "composite": 45.0, "regime": "НЕУТРАЛНИ", "indicators": {}},
        {"module": "ecb",       "label": "ЕЦБ парична политика", "icon": "🏦",
         "composite": 60.0, "regime": "НЕУТРАЛНА", "indicators": {}},
    ]


# ── Section renderers ─────────────────────────────────────────

def test_render_header_includes_required_metadata(sample_snapshot):
    text = render_header(sample_snapshot)
    assert "Briefing Context" in text
    assert "Catalog:" in text
    assert "Snapshot:" in text
    assert str(len(sample_snapshot)) in text


def test_render_executive_has_table(sample_modules_results):
    text = render_executive(sample_modules_results)
    assert "Композитен Macro Score" in text
    assert "| Тема |" in text  # markdown table header (Phase 10 rename)
    assert "Пазар на труда" in text
    assert "Инфлация" in text
    assert "75.0" in text or "75" in text  # composite


def test_render_executive_handles_empty():
    text = render_executive([])
    assert "Executive Summary" in text


def test_render_themes_synthesizes_from_modules(sample_modules_results):
    text = render_themes(sample_modules_results, {})
    assert "ЗДРАВ" in text or "ЕЛЕВИРАНА" in text


def test_render_cross_lens_processes_all_pairs(sample_snapshot):
    augmented = _augment_snapshot_with_derived(sample_snapshot)
    text = render_cross_lens(augmented)
    # All 6 pair names трябва да присъстват
    assert "Стагфлационен тест" in text
    assert "Трансмисия на ЕЦБ" in text
    assert "Фрагментационен риск" in text
    assert "Закотвеност" in text
    assert "Pipeline" in text
    assert "Очаквания срещу твърди" in text


def test_render_cross_spreads_includes_real_dfr(sample_snapshot):
    text = render_cross_spreads(sample_snapshot)
    assert "Реална policy rate" in text
    assert "Yield curve" in text


def test_render_cross_spreads_includes_anchored_band(sample_snapshot):
    text = render_cross_spreads(sample_snapshot)
    assert "anchoring" in text.lower() or "anchored" in text.lower()


def test_render_anomalies_lists_extreme(sample_modules_results):
    text = render_anomalies(sample_modules_results, {})
    # Z=1.7 е > 1.5 → трябва да се появи
    assert "EA_UNRATE" in text or "EA_HICP_CORE" in text


def test_render_anomalies_handles_no_extremes():
    text = render_anomalies([{"module": "labor", "indicators": {}}], {})
    assert "Аномалии" in text


def test_render_series_fact_cards_groups_by_lens(sample_snapshot):
    text = render_series_fact_cards(sample_snapshot)
    # Лещите трябва да са секции
    assert "Пазар на труда" in text
    assert "Инфлация" in text
    assert "Финансови условия" in text


def test_render_series_fact_cards_includes_metadata(sample_snapshot):
    text = render_series_fact_cards(sample_snapshot)
    assert "Source:" in text
    assert "Peer group:" in text
    assert "Transform:" in text
    assert "is_rate:" in text


def test_render_series_fact_cards_flags_nominal_series(sample_snapshot):
    text = render_series_fact_cards(sample_snapshot)
    # EA_COMP_PER_EMPLOYEE е в NOMINAL_SERIES_NEED_DEFLATION
    assert "Nominal series" in text or "deflation" in text


def test_render_methodology_has_required_sections():
    text = render_methodology()
    assert "Methodology" in text
    assert "Score" in text
    assert "is_rate" in text
    assert "anchored" in text or "Anchored" in text
    assert "Limitations" in text


# ── End-to-end ────────────────────────────────────────────────

def test_generate_briefing_context_writes_file(tmp_path, sample_snapshot, sample_modules_results):
    output = tmp_path / "test_brief_ctx.md"
    text = generate_briefing_context(
        snapshot=sample_snapshot,
        modules_results=sample_modules_results,
        output_path=output,
    )
    assert output.exists()
    assert len(text) > 1000  # минимум substantive content
    written = output.read_text(encoding="utf-8")
    assert written == text


def test_generate_briefing_context_creates_parent_dir(tmp_path, sample_snapshot, sample_modules_results):
    nested = tmp_path / "subdir" / "ctx.md"
    generate_briefing_context(
        snapshot=sample_snapshot,
        modules_results=sample_modules_results,
        output_path=nested,
    )
    assert nested.exists()


# ── Helpers ───────────────────────────────────────────────────

def test_augment_snapshot_adds_btp_oat_spreads(sample_snapshot):
    augmented = _augment_snapshot_with_derived(sample_snapshot)
    assert "EA_BTP_BUND_SPREAD" in augmented
    assert "EA_OAT_BUND_SPREAD" in augmented
    # Latest BTP spread = IT.last - DE.last = 4.5 - 2.5 = 2.0
    assert augmented["EA_BTP_BUND_SPREAD"].iloc[-1] == pytest.approx(2.0, abs=0.01)


def test_augment_snapshot_no_de_returns_unchanged():
    snap = {"IT_10Y": monthly([5.0])}
    augmented = _augment_snapshot_with_derived(snap)
    assert "EA_BTP_BUND_SPREAD" not in augmented


def test_peer_group_direction_up_when_all_rising(sample_snapshot):
    # core_measures = HICP_CORE, HICP_SERVICES — и двете растат
    direction = _peer_group_direction(sample_snapshot, "core_measures")
    assert direction in ("up", "mostly_up")


def test_peer_group_direction_returns_none_if_no_data():
    assert _peer_group_direction({}, "core_measures") is None
