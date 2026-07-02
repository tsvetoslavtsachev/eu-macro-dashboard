"""
tests/test_polarity_pin.py
===========================
Полярностен GOLDEN PIN (REVIEW-03 т.0.4, P3-fix-B, генериран 2026-07-02).

Полярността на всяка серия е изрично обсъдено решение — една тихо обърната
полярност обръща леща, без нито един тест да падне (инцидентът с housing
сериите, поправен 2026-06-05, мина незабелязан точно затова; REVIEW-03 R.6).
Този тест пинва ПЪЛНИЯ полярностен вектор.

При ЛЕГИТИМНА промяна на полярност: редактирай двата файла ЗАЕДНО (дефиницията
и този golden) в един commit, с обяснение защо посоката се сменя.
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from catalog.polarity import (  # noqa: E402
    POLARITY,
    POLARITY_BY_LENS,
    PEER_GROUP_WEIGHT,
    U_BAND,
)
from catalog.series import SERIES_CATALOG  # noqa: E402


def _diff(actual: dict, expected: dict) -> dict:
    """Кои ключове се различават — за четим failure."""
    keys = set(actual) | set(expected)
    return {
        k: {"expected": expected.get(k, "<ЛИПСВА>"), "actual": actual.get(k, "<ЛИПСВА>")}
        for k in sorted(keys, key=str)
        if actual.get(k, "<ЛИПСВА>") != expected.get(k, "<ЛИПСВА>")
    }


EXPECTED_POLARITY = {'DE_10Y': -1,
 'DE_CDS_5Y': -1,
 'EA_BANK_LOANS_HH': 1,
 'EA_BANK_LOANS_NFC': 1,
 'EA_BONO_BUND_SPREAD': -1,
 'EA_BTP_BUND_SPREAD': -1,
 'EA_BUILDING_PRODUCTION': 1,
 'EA_BUND_10Y': -1,
 'EA_BUND_2Y': -1,
 'EA_CAPACITY_UTIL': 1,
 'EA_CISS': -1,
 'EA_COMP_PER_EMPLOYEE': 1,
 'EA_CONSTRUCTION_CONF': 1,
 'EA_CONSUMER_CONF': 1,
 'EA_EMPLOYMENT_EXP': 1,
 'EA_EMPLOYMENT_PERSONS': 1,
 'EA_EMP_EXP_SERVICES': 1,
 'EA_ESI': 1,
 'EA_EXPORT_VOLUME': 1,
 'EA_GDP_QOQ': 1,
 'EA_GR_BUND_SPREAD': -1,
 'EA_HICP_CORE': ('U', 'target', 2.0),
 'EA_HICP_ENERGY': ('U', 'target', 2.0),
 'EA_HICP_FOOD': ('U', 'target', 2.0),
 'EA_HICP_HEADLINE': ('U', 'target', 2.0),
 'EA_HICP_SERVICES': ('U', 'target', 2.0),
 'EA_IMPORT_PRICE_ENERGY': -1,
 'EA_IMPORT_PRICE_INTERMED': -1,
 'EA_IMPORT_PRICE_TOTAL': -1,
 'EA_INDUSTRY_CONF': 1,
 'EA_INFL_SWAP_1Y': ('U', 'target', 2.0),
 'EA_INFL_SWAP_2Y': ('U', 'target', 2.0),
 'EA_INFL_SWAP_5Y': ('U', 'target', 2.0),
 'EA_INFL_SWAP_5Y5Y_FWD': ('U', 'target', 2.0),
 'EA_IP': 1,
 'EA_LFS_EMP': 1,
 'EA_M3_YOY': 1,
 'EA_MARGIN': 1,
 'EA_OAT_BUND_SPREAD': -1,
 'EA_PERMIT_DW': 1,
 'EA_PPI_INTERMEDIATE': ('U', 'target', 2.0),
 'EA_PRODUCTION_EXP': 1,
 'EA_PT_BUND_SPREAD': -1,
 'EA_REAL_DFR': -1,
 'EA_REER': -1,
 'EA_RETAIL_CONF': 1,
 'EA_RETAIL_VOL': 1,
 'EA_SELLING_PRICE_EXP': 1,
 'EA_SERVICES_CONF': 1,
 'EA_SPF_HICP_LT': ('U', 'target', 2.0),
 'EA_TOT_MONTHLY': 1,
 'EA_TRADE_BALANCE': 1,
 'EA_UNEMP_YOUTH': -1,
 'EA_UNRATE': -1,
 'EA_WAGES_SALARIES': 1,
 'ECB_BALANCE_SHEET': 1,
 'ES_10Y': -1,
 'ES_CDS_5Y': -1,
 'FR_10Y': -1,
 'FR_CDS_5Y': -1,
 'GR_10Y': -1,
 'IT_10Y': -1,
 'IT_CDS_5Y': -1,
 'NBB_BCI': 1,
 'OECD_BCI_DE': 1,
 'OECD_BCI_EA': 1,
 'PT_10Y': -1}

EXPECTED_POLARITY_BY_LENS = {('inflation', 'EA_SELLING_PRICE_EXP'): ('U', 'self')}

EXPECTED_PEER_GROUP_WEIGHT = {'monetary_aggregates': 0.5}

EXPECTED_U_BAND = 1.0


class TestPolarityPin:
    def test_polarity_vector_pinned(self):
        d = _diff(POLARITY, EXPECTED_POLARITY)
        assert not d, f"ПОЛЯРНОСТЕН ДРИФТ (изрична редакция на golden-а нужна): {d}"

    def test_polarity_overrides_pinned(self):
        d = _diff(POLARITY_BY_LENS, EXPECTED_POLARITY_BY_LENS)
        assert not d, f"Override дрифт: {d}"

    def test_peer_group_weights_pinned(self):
        d = _diff(PEER_GROUP_WEIGHT, EXPECTED_PEER_GROUP_WEIGHT)
        assert not d, f"Peer-group тегловен дрифт: {d}"

    def test_u_band_pinned(self):
        assert U_BAND == EXPECTED_U_BAND

    # lens=[] "_components" серии (строителни блокове за derived числа, извън
    # лещовата машина) са единственото позволено изключение — пиннати поименно,
    # за да падне тестът при ВСЯКА нова серия без полярност. Находка P3-fix-B:
    # тези 7 се score-ват в series_data с default +1 — отворен въпрос към
    # Цветослав дали да получат изрична полярност (EXEC-03B отчета).
    EXPECTED_UNPOLARIZED_COMPONENTS = {
        "EA_EXP_UV", "EA_IMP_UV", "EA_PPI_OUTPUT",
        "ECB_DFR", "ECB_ESTR", "ECB_MLF", "ECB_MRO",
    }

    def test_every_lens_series_has_explicit_polarity(self):
        missing = set(SERIES_CATALOG) - set(POLARITY)
        lens_bearing = sorted(k for k in missing if SERIES_CATALOG[k].get("lens"))
        assert not lens_bearing, (
            f"ЛЕЩОВИ серии без изрична полярност (падат тихо към default +1): {lens_bearing}"
        )
        unexpected = sorted(missing - self.EXPECTED_UNPOLARIZED_COMPONENTS)
        assert not unexpected, (
            f"Нови серии без полярност извън пиннатите _components: {unexpected}"
        )
