"""
tests/conftest.py — тестова хигиена (P3-fix-C, REVIEW-03).

„Индикиран/потвърден" вратата (D1) чете последния ПУБЛИКУВАН macro_state.json —
реален repo файл, чието съдържание мърда с всеки export commit. За херметичност
тестовете винаги виждат None (= indicated). Тестове за confirmed подават
previous_regime_key изрично на compute_executive_summary.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


@pytest.fixture(autouse=True)
def _no_published_regime_in_tests(monkeypatch):
    for mod_name in ("export_api", "export.quick_briefing"):
        try:
            mod = importlib.import_module(mod_name)
        except Exception:
            continue
        if hasattr(mod, "load_previous_published_regime"):
            monkeypatch.setattr(
                mod, "load_previous_published_regime", lambda *a, **k: None
            )
