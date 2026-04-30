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
import webbrowser
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
    from catalog.series import SERIES_CATALOG, series_by_source

    print(f"📊 Catalog: {len(SERIES_CATALOG)} series")

    if not SERIES_CATALOG:
        print("   ⚠ Catalog is empty.")
        return 0

    adapters = {
        "ecb": EcbAdapter(),
        "eurostat": EurostatAdapter(),
    }

    if args.refresh:
        print("\n🔄 --refresh: fetching all catalog series...")
        for source_name, adapter in adapters.items():
            specs = [
                {"key": s["_key"], "source_id": s["id"], "release_schedule": s["release_schedule"]}
                for s in series_by_source(source_name)
            ]
            if specs:
                print(f"   {source_name}: fetching {len(specs)} series...")
                adapter.fetch_many(specs, force=True)
                fails = adapter.last_fetch_failures()
                if fails:
                    print(f"   {source_name}: {len(fails)} failed: {', '.join(fails)}")

    generate_status_report(SERIES_CATALOG, adapters)
    return 0


def _build_snapshot(adapters: dict, force: bool = False) -> dict:
    """Сглобява {series_key: pd.Series} от всички adapter-и (cache-only ако force=False)."""
    from catalog.series import series_by_source

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


def _auto_refresh_stale(adapters: dict, verbose: bool = True) -> int:
    """Smart auto-refresh: fetch-ва само stale серии (TTL изтекъл).

    Mirror на US pattern. Влиза в briefing flow без --refresh флаг — ако
    има stale серии, smart refresh ги прицелва. Force refresh е separate.

    Returns: брой stale серии, които са били refresh-нати.
    """
    from catalog.series import series_by_source

    total_stale = 0
    total_specs = 0
    for source_name, adapter in adapters.items():
        all_specs = [
            {"key": s["_key"], "source_id": s["id"], "release_schedule": s["release_schedule"]}
            for s in series_by_source(source_name)
        ]
        total_specs += len(all_specs)
        stale_specs = adapter.find_stale_specs(all_specs)
        if stale_specs:
            total_stale += len(stale_specs)
            if verbose:
                print(f"   {source_name}: {len(stale_specs)}/{len(all_specs)} stale — fetching...")
            adapter.fetch_many(stale_specs, force=False)
            adapter.save_cache()
            fails = adapter.last_fetch_failures()
            if fails and verbose:
                print(f"   ⚠ {source_name}: {len(fails)} failed — {', '.join(fails[:5])}")

    if verbose:
        n_fresh = total_specs - total_stale
        if total_stale == 0:
            print(f"📦 Cache: {n_fresh}/{total_specs} fresh — всичко up-to-date.")
        else:
            print(f"📦 Cache: {n_fresh}/{total_specs} fresh; {total_stale} stale — auto-refresh complete.")
    return total_stale


def cmd_modules(args) -> int:
    """Модулен summary: оценява всеки lens (Phase 2). Console output."""
    from sources.ecb_adapter import EcbAdapter
    from sources.eurostat_adapter import EurostatAdapter
    import modules.labor as labor_mod
    import modules.inflation as inflation_mod
    import modules.growth as growth_mod
    import modules.credit as credit_mod
    import modules.ecb as ecb_mod
    from config import MODULE_WEIGHTS

    adapters = {"ecb": EcbAdapter(), "eurostat": EurostatAdapter()}
    snapshot = _build_snapshot(adapters, force=args.refresh)

    if not snapshot:
        print("⚠ Snapshot е празен. Стартирай `python run.py --status --refresh` първо.")
        return 1

    print(f"\n📦 Snapshot: {len(snapshot)} серии заредени")
    print()

    modules_to_run = [
        ("labor",     labor_mod),
        ("inflation", inflation_mod),
        ("growth",    growth_mod),
        ("credit",    credit_mod),
        ("ecb",       ecb_mod),
    ]

    results: list[dict] = []
    for name, mod in modules_to_run:
        try:
            result = mod.run(snapshot)
        except Exception as e:
            print(f"  ❌ {name}: грешка — {e}")
            continue
        results.append(result)
        score = result["composite"]
        regime = result["regime"]
        n_indic = len(result.get("indicators", {}))
        print(f"  {result['icon']} {result['label']:25}  score={score:5.1f}  {regime:25}  ({n_indic} серии)")

    # Composite macro score
    weighted = sum(
        r["composite"] * MODULE_WEIGHTS.get(r["module"], 0)
        for r in results
    )
    total_weight = sum(MODULE_WEIGHTS.get(r["module"], 0) for r in results)
    overall = round(weighted / total_weight, 1) if total_weight else 50.0
    print()
    print(f"  📊 Композитен Macro Score: {overall:.1f}")

    return 0


def cmd_refresh_only(args) -> int:
    """Pure data refresh без HTML output. Phase 7."""
    from sources.ecb_adapter import EcbAdapter
    from sources.eurostat_adapter import EurostatAdapter

    adapters = {"ecb": EcbAdapter(), "eurostat": EurostatAdapter()}

    if args.refresh:
        print("🔄 --refresh-only --refresh: force fetch на всички серии...")
        from catalog.series import series_by_source
        for source_name, adapter in adapters.items():
            specs = [
                {"key": s["_key"], "source_id": s["id"], "release_schedule": s["release_schedule"]}
                for s in series_by_source(source_name)
            ]
            print(f"   {source_name}: fetching {len(specs)} series...")
            adapter.fetch_many(specs, force=True)
            adapter.save_cache()
            fails = adapter.last_fetch_failures()
            if fails:
                print(f"   ⚠ {source_name}: {len(fails)} failed: {', '.join(fails)}")
        print("✓ Force refresh complete.")
    else:
        print("🔄 --refresh-only: smart refresh на stale серии...")
        n_stale = _auto_refresh_stale(adapters, verbose=True)
        if n_stale == 0:
            print("✓ Никаква серия не е stale; cache е up-to-date.")
        else:
            print(f"✓ Smart refresh complete ({n_stale} stale серии fetch-нати).")
    return 0


def cmd_briefing(args) -> int:
    """Weekly Briefing workflow. Phase 3 (analogs Phase 4, journal Phase 5).

    Phase 7: auto-refresh kicks in без --refresh флаг — fetch-ва само stale.
    --refresh флагът все още прави force-refresh на всички.
    """
    from sources.ecb_adapter import EcbAdapter
    from sources.eurostat_adapter import EurostatAdapter
    from export.weekly_briefing import generate_weekly_briefing
    import modules.labor as labor_mod
    import modules.inflation as inflation_mod
    import modules.growth as growth_mod
    import modules.credit as credit_mod
    import modules.ecb as ecb_mod

    adapters = {"ecb": EcbAdapter(), "eurostat": EurostatAdapter()}

    # Phase 7: auto-refresh stale серии преди briefing (без force flag)
    if not args.refresh:
        _auto_refresh_stale(adapters, verbose=True)

    snapshot = _build_snapshot(adapters, force=args.refresh)

    if not snapshot:
        print("⚠ Snapshot е празен. Стартирай `python run.py --status --refresh` първо.")
        return 1

    print(f"\n📦 Snapshot: {len(snapshot)} серии заредени")
    print("🔬 Изчисляване на модули...")

    modules_results = []
    for name, mod in [("labor", labor_mod), ("inflation", inflation_mod),
                      ("growth", growth_mod), ("credit", credit_mod),
                      ("ecb", ecb_mod)]:
        try:
            modules_results.append(mod.run(snapshot))
        except Exception as e:
            print(f"   ⚠ {name}: грешка — {e}")

    analog_bundle = None
    if args.with_analogs:
        from analysis.analog_pipeline import compute_analog_bundle
        print("🔭 Изчисляване на исторически аналози...")
        try:
            analog_bundle = compute_analog_bundle(snapshot, k=3)
            if analog_bundle is None:
                print("   ⚠ Недостатъчно история за аналози (необходими 7 dim complete)")
            else:
                print(f"   ✓ Top analog: {analog_bundle.analogs[0].date.strftime('%Y-%m')} "
                      f"(similarity {analog_bundle.analogs[0].similarity:.2f})")
        except Exception as e:
            print(f"   ❌ Грешка: {e}")

    journal_entries = None
    if args.with_journal:
        from scripts._utils import load_journal_entries
        print("📓 Зареждане на journal entries...")
        try:
            journal_entries = load_journal_entries()
            print(f"   ✓ {len(journal_entries)} entries намерени")
        except Exception as e:
            print(f"   ❌ Грешка: {e}")

    output_path = f"{OUTPUT_DIR}/briefing_{datetime.now().strftime('%Y-%m-%d')}.html"
    print(f"📝 Генериране на HTML → {output_path}")

    generate_weekly_briefing(
        snapshot=snapshot,
        modules_results=modules_results,
        output_path=output_path,
        analog_bundle=analog_bundle,
        journal_entries=journal_entries,
    )

    print(f"✓ Briefing готов: {output_path}")
    if not args.no_browser:
        try:
            webbrowser.open(f"file://{Path(output_path).resolve()}")
        except Exception:
            pass
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Eurozone Macro Dashboard — седмичен briefing на български.",
    )
    parser.add_argument("--status", action="store_true",
                        help="Data Status Screen (Phase 1)")
    parser.add_argument("--modules", action="store_true",
                        help="Modules summary — labor/inflation/growth/ecb (Phase 2)")
    parser.add_argument("--refresh-only", action="store_true",
                        help="Refresh данни без да генерира briefing (Phase 7)")
    parser.add_argument("--briefing", action="store_true",
                        help="Weekly Briefing (Phase 3) — auto-refresh stale series без --refresh")
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
    if args.refresh_only:
        return cmd_refresh_only(args)
    if args.modules:
        return cmd_modules(args)
    if args.briefing:
        return cmd_briefing(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
