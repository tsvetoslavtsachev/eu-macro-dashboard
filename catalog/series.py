"""
catalog/series.py
=================
Декларативен каталог на Eurozone макро серии.

Това е единственото място, където една серия се описва: източник, ID,
регион, имена (BG/EN), лещи, peer_group за breadth, tags, трансформация,
исторически старт, release schedule, narrative hint.

Всички останали модули (analytics, modules, briefing) четат оттук, без да
дублират metadata.

Phase 0 (текущ): празен каталог с фиксирани whitelist-и. Phase 1 ще го
напълни с реални EA серии (ECB SDW + Eurostat + DG ECFIN).

Поддържани източници:
  - "ecb"       — ECB Statistical Data Warehouse (data-api.ecb.europa.eu)
  - "eurostat"  — Eurostat REST API (ec.europa.eu/eurostat)
  - "oecd"      — OECD Data API (Phase 2 candidate)
  - "pending"   — placeholder, чака implementation на adapter

Региони:
  - "EA"   — Euro Area aggregate (default scope за v1)
  - "EU"   — EU-27 (някои Eurostat серии са само EU-27)
  - "DE", "FR", "IT", "ES" — country drill-down (Phase 2)
  - "GLOBAL" — non-region (oil, FX и др.)

Лещи (5):
  - "labor"     — заетост, безработица, заплати
  - "inflation" — HICP, очаквания
  - "growth"    — IP, retail, GDP, sentiment
  - "credit"    — CISS, sovereign spreads, M3, банков лeverage
  - "ecb"       — ECB rates, balance sheet, TLTRO (нов lens, без US аналог)
"""
from __future__ import annotations
from typing import Any


# ============================================================
# WHITELISTS
# ============================================================

ALLOWED_SOURCES = {"ecb", "eurostat", "oecd", "pending"}
ALLOWED_REGIONS = {"EA", "EU", "DE", "FR", "IT", "ES", "GLOBAL"}
ALLOWED_LENSES = {"labor", "inflation", "growth", "credit", "ecb"}
ALLOWED_TRANSFORMS = {"level", "yoy_pct", "mom_pct", "qoq_pct", "z_score", "first_diff"}
ALLOWED_TAGS = {"non_consensus", "structural", "sovereign_stress"}
ALLOWED_SCHEDULES = {"weekly", "monthly", "quarterly", "annually"}


# ============================================================
# CATALOG (Phase 1 ще го напълни)
# ============================================================

SERIES_CATALOG: dict[str, dict[str, Any]] = {
    # TODO Phase 1: добави EA серии. Шаблон:
    #
    # "EA_UNRATE": {
    #     "source": "eurostat",
    #     "id": "une_rt_m",          # Eurostat dataset/series код
    #     "region": "EA",
    #     "name_bg": "Безработица (EA-19, headline)",
    #     "name_en": "Unemployment Rate (EA-19)",
    #     "lens": ["labor"],
    #     "peer_group": "unemployment",
    #     "tags": [],
    #     "transform": "level",
    #     "historical_start": "1998-01-01",
    #     "release_schedule": "monthly",
    #     "typical_release": "first_week",
    #     "revision_prone": False,
    #     "narrative_hint": "Headline unemployment rate за EA-19; lagging indicator.",
    # },
}


# ============================================================
# QUERY HELPERS (1:1 от US)
# ============================================================

def get_series(key: str) -> dict[str, Any]:
    """Връща конкретна серия по ключ. Хвърля KeyError ако липсва."""
    if key not in SERIES_CATALOG:
        raise KeyError(f"Серия '{key}' не съществува в catalog.")
    return SERIES_CATALOG[key]


def series_by_lens(lens: str) -> list[dict[str, Any]]:
    """Всички серии, принадлежащи към дадена леща (вкл. multi-lens)."""
    return [
        {**meta, "_key": k}
        for k, meta in SERIES_CATALOG.items()
        if lens in meta.get("lens", [])
    ]


def series_by_peer_group(group: str) -> list[dict[str, Any]]:
    """Всички серии в конкретна peer group."""
    return [
        {**meta, "_key": k}
        for k, meta in SERIES_CATALOG.items()
        if meta.get("peer_group") == group
    ]


def series_by_tag(tag: str) -> list[dict[str, Any]]:
    """Всички серии със специфичен tag (напр. 'non_consensus')."""
    return [
        {**meta, "_key": k}
        for k, meta in SERIES_CATALOG.items()
        if tag in meta.get("tags", [])
    ]


def all_series_ids() -> list[str]:
    """Всички каталожни ключове."""
    return list(SERIES_CATALOG.keys())


def series_by_source(source: str) -> list[dict[str, Any]]:
    """Всички серии от конкретен източник ('ecb', 'eurostat', 'oecd', 'pending')."""
    return [
        {**meta, "_key": k}
        for k, meta in SERIES_CATALOG.items()
        if meta.get("source") == source
    ]


# ============================================================
# VALIDATION
# ============================================================

def validate_catalog() -> list[str]:
    """Проверява, че всички записи имат задължителните полета с валидни стойности.

    Returns:
        list of error messages (празен = всичко е наред).
    """
    required_fields = {
        "source", "id", "region", "name_bg", "name_en",
        "lens", "peer_group", "tags", "transform",
        "historical_start", "release_schedule", "typical_release",
        "revision_prone", "narrative_hint",
    }

    errors: list[str] = []

    for key, meta in SERIES_CATALOG.items():
        missing = required_fields - set(meta.keys())
        if missing:
            errors.append(f"{key}: липсват полета {missing}")
            continue

        if meta["source"] not in ALLOWED_SOURCES:
            errors.append(f"{key}: невалиден source '{meta['source']}'")
        if meta["region"] not in ALLOWED_REGIONS:
            errors.append(f"{key}: невалиден region '{meta['region']}'")
        if meta["transform"] not in ALLOWED_TRANSFORMS:
            errors.append(f"{key}: невалиден transform '{meta['transform']}'")
        if meta["release_schedule"] not in ALLOWED_SCHEDULES:
            errors.append(f"{key}: невалиден release_schedule '{meta['release_schedule']}'")
        for lens in meta["lens"]:
            if lens not in ALLOWED_LENSES:
                errors.append(f"{key}: невалидна lens '{lens}'")
        for tag in meta["tags"]:
            if tag not in ALLOWED_TAGS:
                errors.append(f"{key}: невалиден tag '{tag}'")
        if not isinstance(meta["revision_prone"], bool):
            errors.append(f"{key}: revision_prone трябва да е bool")

    return errors


# ============================================================
# MODULE LOAD-TIME VALIDATION
# ============================================================

_validation_errors = validate_catalog()
if _validation_errors:
    import warnings
    warnings.warn(
        "Catalog validation failed:\n  " + "\n  ".join(_validation_errors),
        UserWarning,
        stacklevel=2,
    )
