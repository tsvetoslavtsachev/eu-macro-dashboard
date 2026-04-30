"""
export/data_status.py
=====================
Data Status Screen — кои серии са свежи, кои са stale, кои липсват.

Phase 1: console output. Phase 3 ще добави HTML render.

Pattern (от US `export/data_status.py`):
  generate_status_report(catalog, adapters, output_path=None) → dict | str

Multi-source: за разлика от US (само FRED), EU има няколко adapter-а.
Status report групира по source за яснота и подкарва force-refresh флоу.

Statuses:
  - FRESH       — cache exists и е по-млад от TTL за schedule
  - STALE       — cache exists но > TTL (има данни, но е препоръчително refresh)
  - MISSING     — няма cache entry (никога не е fetch-вано или invalidate-нато)
  - PENDING     — source="pending" (catalog знае за серията, adapter липсва)
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, date
from typing import Any, Optional

from sources._base import CACHE_TTL_DAYS


# Period-aware data staleness thresholds (Phase 8d).
# data_stale = last_observation е по-старо от (period_length + release_lag).
# EU statistics са по-бавни от US: quarterly release_lag = 50d (US е 35d).
PERIOD_LENGTH_DAYS = {
    "weekly":     7,
    "monthly":    30,
    "quarterly":  90,
    "annually":   365,
}
RELEASE_LAG_DAYS = {
    "weekly":     5,    # CISS petak releases
    "monthly":    30,   # HICP, IP — usually 1mo lag
    "quarterly":  50,   # EU GDP, LFS, compensation — slower
    "annually":   90,   # annual stats often available 3mo after year-end
}


@dataclass
class SeriesStatus:
    key: str
    source: str
    source_id: str
    schedule: str
    name_bg: str
    is_cached: bool
    last_fetched: Optional[str]
    last_observation: Optional[str]
    n_observations: int
    freshness: str        # "FRESH" | "STALE" | "MISSING" | "PENDING"
    age_days: Optional[float]
    data_staleness: str = "UNKNOWN"  # "FRESH" | "EXPECTED" | "DATA_STALE" | "UNKNOWN"
    data_age_days: Optional[float] = None  # дни от last_observation до today


def assess_data_staleness(
    last_observation: Optional[str],
    schedule: str,
    today: Optional[date] = None,
) -> tuple[str, Optional[float]]:
    """Period-aware data staleness — отделно от cache TTL.

    Cache TTL казва "кога да re-fetch-ваме"; data_staleness казва
    "кога данните били публикувани последно vs. кога очакваме нов release".

    Threshold = period_length + release_lag (е.g., quarterly EU = 90+50 = 140d).

    Returns:
        (status, age_in_days). status ∈ {"FRESH", "EXPECTED", "DATA_STALE", "UNKNOWN"}.
        FRESH    = last_obs е в текущия period (e.g., monthly: <30d ago)
        EXPECTED = в release lag window (period < age < period + release_lag)
        DATA_STALE = просрочен release (age > period + release_lag) — flag-ва за investigation
    """
    if not last_observation:
        return "UNKNOWN", None

    today = today or date.today()

    try:
        if isinstance(last_observation, str):
            last = datetime.fromisoformat(last_observation).date()
        else:
            last = last_observation
    except ValueError:
        return "UNKNOWN", None

    age = (today - last).days
    if age < 0:
        return "FRESH", float(age)

    period = PERIOD_LENGTH_DAYS.get(schedule, 30)
    lag = RELEASE_LAG_DAYS.get(schedule, 30)

    if age <= period:
        return "FRESH", float(age)
    if age <= period + lag:
        return "EXPECTED", float(age)
    return "DATA_STALE", float(age)


def _classify(status: dict, schedule: str, source: str) -> tuple[str, Optional[float]]:
    """Връща (freshness_label, age_in_days)."""
    if source == "pending":
        return "PENDING", None
    if not status.get("is_cached"):
        return "MISSING", None
    last_str = status.get("last_fetched")
    if not last_str:
        return "MISSING", None
    try:
        last = datetime.fromisoformat(last_str)
    except ValueError:
        return "MISSING", None
    age = (datetime.now() - last).total_seconds() / 86400.0
    ttl = CACHE_TTL_DAYS.get(schedule, 10)
    return ("FRESH" if age < ttl else "STALE"), age


def gather_status(
    catalog: dict[str, dict[str, Any]],
    adapters: dict[str, Any],  # {"ecb": EcbAdapter, "eurostat": EurostatAdapter, ...}
) -> list[SeriesStatus]:
    """Събира status за всяка серия в катaлога. Не прави мрежови calls."""
    out: list[SeriesStatus] = []
    for key, meta in catalog.items():
        source = meta.get("source", "pending")
        adapter = adapters.get(source)
        if adapter is None:
            status = {"is_cached": False, "last_fetched": None, "last_observation": None, "n_observations": 0}
        else:
            status = adapter.get_cache_status(key)

        schedule = meta.get("release_schedule", "monthly")
        freshness, age = _classify(status, schedule, source)
        data_staleness, data_age = assess_data_staleness(
            status.get("last_observation"), schedule,
        )

        out.append(SeriesStatus(
            key=key,
            source=source,
            source_id=meta.get("id", ""),
            schedule=schedule,
            name_bg=meta.get("name_bg", key),
            is_cached=status.get("is_cached", False),
            last_fetched=status.get("last_fetched"),
            last_observation=status.get("last_observation"),
            n_observations=status.get("n_observations", 0),
            freshness=freshness,
            age_days=age,
            data_staleness=data_staleness,
            data_age_days=data_age,
        ))
    return out


def render_console(statuses: list[SeriesStatus]) -> str:
    """Renderer като text за console output."""
    if not statuses:
        return "  (catalog е празен)"

    lines: list[str] = []

    # Group by source
    by_source: dict[str, list[SeriesStatus]] = {}
    for s in statuses:
        by_source.setdefault(s.source, []).append(s)

    # Counters
    total = len(statuses)
    fresh = sum(1 for s in statuses if s.freshness == "FRESH")
    stale = sum(1 for s in statuses if s.freshness == "STALE")
    missing = sum(1 for s in statuses if s.freshness == "MISSING")
    pending = sum(1 for s in statuses if s.freshness == "PENDING")

    lines.append("")
    lines.append(f"  📊 {total} серии · ✓ {fresh} fresh · ⚠ {stale} stale · ✗ {missing} missing · ⏳ {pending} pending")
    lines.append("")

    icons = {"FRESH": "✓", "STALE": "⚠", "MISSING": "✗", "PENDING": "⏳"}

    # Data-stale alerts (период-aware) — separate banner ако има late releases
    data_stale_count = sum(1 for s in statuses if s.data_staleness == "DATA_STALE")
    if data_stale_count:
        lines.append(f"  ⏰ {data_stale_count} серии с просрочен release (period + release_lag exceeded):")
        for s in statuses:
            if s.data_staleness == "DATA_STALE":
                age_str = f"{s.data_age_days:.0f}d" if s.data_age_days is not None else "—"
                lines.append(f"     - {s.key:24} last_obs={s.last_observation}  ({age_str} ago)")
        lines.append("")

    for source in sorted(by_source.keys()):
        lines.append(f"  ── {source.upper()} ({len(by_source[source])} серии) " + "─" * (50 - len(source)))
        for s in sorted(by_source[source], key=lambda x: x.key):
            icon = icons.get(s.freshness, "?")
            age_str = f"{s.age_days:.0f}d" if s.age_days is not None else "—"
            data_age_str = f"{s.data_age_days:.0f}d" if s.data_age_days is not None else "—"
            last_obs = s.last_observation or "—"
            stale_marker = " ⏰" if s.data_staleness == "DATA_STALE" else ""
            lines.append(
                f"    {icon} {s.key:24}  {s.freshness:8}  age={age_str:>6}  obs={s.n_observations:>5}  last_obs={last_obs} ({data_age_str} ago){stale_marker}"
            )
        lines.append("")

    return "\n".join(lines)


def generate_status_report(
    catalog: dict[str, dict[str, Any]],
    adapters: dict[str, Any],
    output_path: Optional[str] = None,
) -> str:
    """Главна entry — gathering + console render."""
    statuses = gather_status(catalog, adapters)
    text = render_console(statuses)
    print(text)
    if output_path:
        # Phase 3 ще добави HTML output
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)
    return text
