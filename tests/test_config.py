"""Tests für die Toleranz-Konfiguration des Cross-Checks (Story S-013).

Covers (llm-grounding): AC5

`app.config.Settings.toleranz_config` trägt die konfigurierbaren
Toleranzschwellen je Kennzahl-Typ (absolut/relativ) — provisorische
Defaults ohne jede Env-Variable, aber per Env-Variable (`TOLERANZ_CONFIG`,
JSON-codiert) **ohne Codeänderung** überschreibbar. `get_settings()` ist
die Dependency-Factory (fastapi/A06); `cache_clear()` erlaubt Tests,
zwischen unterschiedlichen Env-Zuständen neu zu laden.
"""

from __future__ import annotations

import pytest

from app.config import DEFAULT_TOLERANZEN, Settings, get_settings


@pytest.fixture(autouse=True)
def _settings_cache_isolieren():
    """Isoliert den `lru_cache`-Singleton zwischen Testfällen."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_settings_liefert_provisorische_default_toleranzen_ohne_env() -> None:
    """@trace llm-grounding#AC5 — ohne Env-Override liefert `Settings` die
    provisorischen Defaults aus `DEFAULT_TOLERANZEN` (AC5: "konkrete
    Festlegung ist offen/provisorisch")."""
    settings = Settings(_env_file=None)

    assert settings.toleranz_config == DEFAULT_TOLERANZEN
    assert settings.toleranz_config["kgv"].typ == "relativ"


def test_settings_ueberschreibt_toleranz_config_ohne_codeaenderung(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """@trace llm-grounding#AC5 — die Toleranzschwelle je Kennzahl-Typ ist
    über die Umgebungsvariable `TOLERANZ_CONFIG` (JSON) ersetzbar, ohne
    dass `app/config.py` geändert werden muss."""
    monkeypatch.setenv(
        "TOLERANZ_CONFIG",
        '{"kgv": {"kennzahl_typ": "kgv", "typ": "absolut", "schwelle": 1.5}}',
    )

    settings = Settings(_env_file=None)

    assert settings.toleranz_config["kgv"].typ == "absolut"
    assert settings.toleranz_config["kgv"].schwelle == 1.5


def test_get_settings_ist_gecachter_singleton() -> None:
    """@trace llm-grounding#AC5 — `get_settings()` liefert innerhalb eines
    Prozesses dieselbe Instanz (fastapi/A06 Dependency-Factory-Muster)."""
    erste = get_settings()
    zweite = get_settings()

    assert erste is zweite
