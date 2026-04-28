"""
eu_macro_dashboard — Entry Point
================================
Три workflow-а (по образец на US Macro_Intelligence/econ_v2):

    python run.py --status     # Phase 1: Data Status Screen
    python run.py --briefing   # Phase 3: Weekly Briefing
    python run.py --briefing --with-analogs   # Phase 4
    python run.py --briefing --with-journal   # Phase 5

Глобални опции:
    --refresh        Force-fetch всички серии преди генериране
    --no-browser     Не отваря HTML в браузъра (CI / headless)

Phase 0 (текущ): skeleton. Всички handler-и raise NotImplementedError с
указание коя Phase ги имплементира. След като Phase 1+ се build-нат,
сменяме body-тата.
"""
import argparse
import sys
import logging
from pathlib import Path
from datetime import datetime

# Windows: гарантираме UTF-8 stdout/stderr за да не падне на кирилица
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

logging.basicConfig(level=logging.INFO, format="%(message)s")

# Shared config (лек import — няма network)
from config import (
    ECB_API_BASE,
    EUROSTAT_API_BASE,
    MODULE_WEIGHTS,
    MACRO_REGIMES,
    OUTPUT_DIR,
)


def cmd_status(args) -> int:
    """Data Status Screen workflow. Phase 1."""
    from sources.ecb_adapter import EcbAdapter
    from sources.eurostat_adapter import EurostatAdapter
    from export.data_status import generate_status_report
    from catalog.series import SERIES_CATALOG

    print("📡 Status: catalog has", len(SERIES_CATALOG), "series")
    if not SERIES_CATALOG:
        print("   ⚠ Catalog is empty (Phase 1 will populate it).")
        return 0

    ecb = EcbAdapter()
    es = EurostatAdapter()
    generate_status_report(SERIES_CATALOG, ecb, es)
    return 0


def cmd_briefing(args) -> int:
    """Weekly Briefing workflow. Phase 3 (analogs Phase 4, journal Phase 5)."""
    from export.weekly_briefing import generate_weekly_briefing

    snapshot: dict = {}  # TODO Phase 1: fetch from adapters
    output_path = f"{OUTPUT_DIR}/briefing_{datetime.now().strftime('%Y-%m-%d')}.html"
    generate_weekly_briefing(
        snapshot=snapshot,
        output_path=output_path,
        analog_bundle=None if not args.with_analogs else None,
        journal_entries=None if not args.with_journal else None,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Eurozone Macro Dashboard — седмичен briefing на български.",
    )
    parser.add_argument("--status", action="store_true",
                        help="Data Status Screen (Phase 1)")
    parser.add_argument("--briefing", action="store_true",
                        help="Weekly Briefing (Phase 3)")
    parser.add_argument("--with-analogs", action="store_true",
                        help="Включи historical analogs секция (Phase 4)")
    parser.add_argument("--with-journal", action="store_true",
                        help="Включи свързани journal entries (Phase 5)")
    parser.add_argument("--refresh", action="store_true",
                        help="Force-fetch всички серии преди генериране")
    parser.add_argument("--no-browser", action="store_true",
                        help="Не отваря HTML в браузър")
    args = parser.parse_args()

    print("\n" + "═" * 60)
    print("  ⚡  Eurozone Macro Dashboard")
    print("═" * 60)
    print(f"  {datetime.now().strftime('%A, %d %B %Y · %H:%M')}")
    print(f"  ECB:      {ECB_API_BASE}")
    print(f"  Eurostat: {EUROSTAT_API_BASE}")
    print("═" * 60 + "\n")

    if args.status:
        return cmd_status(args)
    if args.briefing:
        return cmd_briefing(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
