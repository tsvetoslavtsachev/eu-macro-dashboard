"""is_rate → дисплей „%" на лихва/процент серии (parity с US; item H1)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from export.quick_briefing import _fmt_reading
from catalog.series import SERIES_CATALOG as C


def test_rate_level_reading_gets_percent():
    assert _fmt_reading(5.23, is_pct=False, is_rate=True) == "5.23%"
    assert _fmt_reading(2.45, is_pct=False, is_rate=True) == "2.45%"


def test_pct_change_reading_unchanged_signed():
    assert _fmt_reading(0.66, is_pct=True) == "+0.7%"


def test_index_reading_stays_bare():
    assert _fmt_reading(101.3, is_pct=False, is_rate=False) == "101.30"


def test_eu_is_rate_flags_present():
    # EU вече носи is_rate на сериите — лихвите True, индексите/балансите False
    assert C["EA_UNRATE"]["is_rate"] is True
    assert C["EA_BUND_10Y"]["is_rate"] is True
    assert C["EA_ESI"]["is_rate"] is False           # sentiment index
    assert C["EA_TRADE_BALANCE"]["is_rate"] is False  # balance, не %
