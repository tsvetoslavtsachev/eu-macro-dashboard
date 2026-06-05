"""Tests за sources/sdmx_csv_adapter.parse_sdmx_csv — OECD + NBB SDMX-CSV."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sources.sdmx_csv_adapter import parse_sdmx_csv, SdmxCsvAdapter


# ── Реални проби (копирани от live response-ите 2026-06-05) ──────────────

OECD_CSV = (
    "DATAFLOW,REF_AREA,FREQ,MEASURE,UNIT_MEASURE,ACTIVITY,ADJUSTMENT,TRANSFORMATION,"
    "TIME_HORIZ,METHODOLOGY,TIME_PERIOD,OBS_VALUE,OBS_STATUS,UNIT_MULT,DECIMALS,BASE_PER\n"
    "OECD.SDD.STES:DSD_STES@DF_CLI(4.1),DEU,M,BCICP,IX,_Z,AA,IX,_Z,H,2026-03,99.14655,A,0,2,\n"
    "OECD.SDD.STES:DSD_STES@DF_CLI(4.1),DEU,M,BCICP,IX,_Z,AA,IX,_Z,H,2026-04,99.23952,A,0,2,\n"
    "OECD.SDD.STES:DSD_STES@DF_CLI(4.1),DEU,M,BCICP,IX,_Z,AA,IX,_Z,H,1990-07,102.1031,A,0,2,\n"
)

# NBB носи balance-of-opinion (може да е отрицателна) + по-малко колони
NBB_CSV = (
    "DATAFLOW,FREQ,BUSSURVM_INDICATOR,BE_AREA,BUSSURV_SECTOR,BUSSURVM_ADJ,"
    "TIME_PERIOD,OBS_VALUE,OBS_STATUS,DECIMALS\n"
    "BE2:DF_BUSSURVM(1.0),M,SYNC,BE,A999,S,1980-01,-7.9,A,1\n"
    "BE2:DF_BUSSURVM(1.0),M,SYNC,BE,A999,S,1980-02,-8.3,A,1\n"
    "BE2:DF_BUSSURVM(1.0),M,SYNC,BE,A999,S,2026-05,-13.3,A,1\n"
)


def test_parse_oecd_sorted_and_typed():
    s = parse_sdmx_csv(OECD_CSV, "OECD_BCI_DE")
    assert isinstance(s, pd.Series)
    assert len(s) == 3
    # Сортирано възходящо независимо от реда в CSV
    assert list(s.index) == [pd.Timestamp("1990-07-01"),
                             pd.Timestamp("2026-03-01"),
                             pd.Timestamp("2026-04-01")]
    assert s.iloc[-1] == pytest.approx(99.23952)
    assert s.iloc[0] == pytest.approx(102.1031)


def test_parse_nbb_negative_balance():
    s = parse_sdmx_csv(NBB_CSV, "NBB_BCI")
    assert len(s) == 3
    assert s.loc[pd.Timestamp("1980-01-01")] == pytest.approx(-7.9)
    assert s.loc[pd.Timestamp("2026-05-01")] == pytest.approx(-13.3)
    # Monthly → period-start timestamps
    assert isinstance(s.index, pd.DatetimeIndex)


def test_parse_bom_prefix_handled():
    """OECD CSV идва с UTF-8 BOM пред първата колона — не бива да чупи parsing-а."""
    s = parse_sdmx_csv("﻿" + OECD_CSV, "OECD_BCI_DE")
    assert len(s) == 3


def test_parse_skips_blank_values():
    csv_blank = (
        "TIME_PERIOD,OBS_VALUE,OBS_STATUS\n"
        "2026-01,,M\n"          # липсваща стойност → skip
        "2026-02,101.5,A\n"
    )
    s = parse_sdmx_csv(csv_blank, "X")
    assert len(s) == 1
    assert s.iloc[0] == pytest.approx(101.5)


def test_parse_missing_columns_raises():
    with pytest.raises(ValueError):
        parse_sdmx_csv("FOO,BAR\n1,2\n", "X")


def test_parse_empty_returns_empty_series():
    s = parse_sdmx_csv("TIME_PERIOD,OBS_VALUE\n", "X")
    assert s.empty


def test_parse_duplicate_period_raises():
    """>1 серия в един response (дублиран период) → грешка, не тихо сливане."""
    dup = (
        "TIME_PERIOD,OBS_VALUE\n"
        "2026-01,100.0\n"
        "2026-01,50.0\n"
    )
    with pytest.raises(ValueError):
        parse_sdmx_csv(dup, "X")


def test_adapter_rejects_non_url_source_id():
    adapter = SdmxCsvAdapter("data/_test_oecd_cache.json", source_name="oecd")
    with pytest.raises(ValueError):
        adapter._fetch_remote("OECD_BCI_DE", "DEU.M.BCICP")  # не е URL
