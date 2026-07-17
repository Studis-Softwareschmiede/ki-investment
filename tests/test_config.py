"""Tests für die Toleranz-Konfiguration des Cross-Checks (Story S-013) und
die Einstand-Methode-Default-Konfiguration (Story S-016).

Covers (llm-grounding): AC5
Covers (depot): AC5
Covers (kandidatensuche): AC6, AC7, AC10
Covers (depot-ueberwachung): AC4, AC6, AC7

`app.config.Settings.toleranz_config` trägt die konfigurierbaren
Toleranzschwellen je Kennzahl-Typ (absolut/relativ) — provisorische
Defaults ohne jede Env-Variable, aber per Env-Variable (`TOLERANZ_CONFIG`,
JSON-codiert) **ohne Codeänderung** überschreibbar. `get_settings()` ist
die Dependency-Factory (fastapi/A06); `cache_clear()` erlaubt Tests,
zwischen unterschiedlichen Env-Zuständen neu zu laden.

`app.config.Settings.einstand_methode_default` (S-016, AC5, BR-112) trägt
die systemweite Default-Einstand-Methode für den allerersten Kauf eines
Titels — Default `gleitender_durchschnitt` (CH-Kontext), per
`EINSTAND_METHODE_DEFAULT` ohne Codeänderung auf `fifo` umstellbar.

`app.config.Settings.kandidatensuche_liquiditaets_mindestschwelle`/
`kandidatensuche_volatilitaets_fenster_min`/`_max` (S-029, AC6/AC10) tragen
die Querschnitt-Filter-Schwellen; `kandidatensuche_profil_overrides` (S-029,
AC7/AC10) trägt die je Anlageklasse gemergten Suchprofil-Overrides — alle
ohne Codeänderung per Env-Variable überschreibbar.

`app.config.Settings.depot_ueberwachung_ereignis_keywords` (S-033, AC4)
trägt die Keyword-/Ereignis-Filter-Stichwortliste,
`depot_ueberwachung_ereignis_schwellen` (S-033, AC6-Nachbar-Konfiguration)
die je Ereignistyp konfigurierten Schwellen und
`depot_ueberwachung_ereignisse_pro_tag_schwellwert` (S-033, AC7) den
Alert-Fatigue-Tages-Schwellwert — alle drei ohne Codeänderung per
Env-Variable überschreibbar.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.config import DEFAULT_TOLERANZEN, Settings, get_settings, lade_querschnitt_filter
from app.contracts.depot_ueberwachung import DEFAULT_EREIGNIS_KEYWORDS, DEFAULT_EREIGNIS_SCHWELLEN


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


def test_settings_liefert_gleitenden_durchschnitt_als_einstand_methode_default() -> None:
    """@trace depot#AC5 — ohne Env-Override ist `gleitender_durchschnitt`
    die Default-Einstand-Methode (BR-112, CH-Kontext)."""
    settings = Settings(_env_file=None)

    assert settings.einstand_methode_default == "gleitender_durchschnitt"


def test_settings_ueberschreibt_einstand_methode_default_ohne_codeaenderung(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """@trace depot#AC5 — `EINSTAND_METHODE_DEFAULT=fifo` schaltet die
    Default-Einstand-Methode ohne Codeänderung um."""
    monkeypatch.setenv("EINSTAND_METHODE_DEFAULT", "fifo")

    settings = Settings(_env_file=None)

    assert settings.einstand_methode_default == "fifo"


def test_settings_liefert_provisorische_querschnitt_filter_defaults_ohne_env() -> None:
    """@trace kandidatensuche#AC6,AC10 — ohne Env-Override liefert
    `Settings` die provisorischen, unkalibrierten Querschnitt-Filter-
    Defaults."""
    settings = Settings(_env_file=None)

    assert settings.kandidatensuche_liquiditaets_mindestschwelle == Decimal("1")
    assert settings.kandidatensuche_volatilitaets_fenster_min == Decimal("0")
    assert settings.kandidatensuche_volatilitaets_fenster_max == Decimal("1000000")


def test_settings_ueberschreibt_querschnitt_filter_schwellen_ohne_codeaenderung(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """@trace kandidatensuche#AC6,AC10 — die drei Querschnitt-Filter-
    Schwellen sind je einzeln über eigene Umgebungsvariablen ersetzbar."""
    monkeypatch.setenv("KANDIDATENSUCHE_LIQUIDITAETS_MINDESTSCHWELLE", "3")
    monkeypatch.setenv("KANDIDATENSUCHE_VOLATILITAETS_FENSTER_MIN", "0.5")
    monkeypatch.setenv("KANDIDATENSUCHE_VOLATILITAETS_FENSTER_MAX", "50")

    settings = Settings(_env_file=None)

    assert settings.kandidatensuche_liquiditaets_mindestschwelle == Decimal("3")
    assert settings.kandidatensuche_volatilitaets_fenster_min == Decimal("0.5")
    assert settings.kandidatensuche_volatilitaets_fenster_max == Decimal("50")


def test_lade_querschnitt_filter_baut_vertrag_aus_settings() -> None:
    """@trace kandidatensuche#AC6,AC10 — `lade_querschnitt_filter` liefert
    den `QuerschnittFilter`-Vertrag, befüllt aus den `Settings`-Schwellen."""
    get_settings.cache_clear()
    filter_ = lade_querschnitt_filter(Settings(_env_file=None))

    assert filter_.liquiditaets_mindestschwelle == Decimal("1")
    assert filter_.volatilitaets_fenster.min == Decimal("0")
    assert filter_.volatilitaets_fenster.max == Decimal("1000000")


def test_settings_liefert_leere_suchprofil_overrides_ohne_env() -> None:
    """@trace kandidatensuche#AC7,AC10 — ohne Env-Override ist
    `kandidatensuche_profil_overrides` leer (kein Profil wird
    verändert)."""
    settings = Settings(_env_file=None)

    assert settings.kandidatensuche_profil_overrides == {}


def test_settings_ueberschreibt_suchprofil_overrides_ohne_codeaenderung(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """@trace kandidatensuche#AC7,AC10 — `KANDIDATENSUCHE_PROFIL_OVERRIDES`
    (JSON, Anlageklasse als String-Key) befüllt je Klasse einen Modus-
    und/oder Schwellen-Override, ohne Codeänderung."""
    monkeypatch.setenv(
        "KANDIDATENSUCHE_PROFIL_OVERRIDES",
        '{"1": {"modus": "periodisch", "schwellen": {"rvol_faktor": 2.5}}}',
    )

    settings = Settings(_env_file=None)

    override = settings.kandidatensuche_profil_overrides[1]
    assert override.modus == "periodisch"
    assert override.schwellen == {"rvol_faktor": Decimal("2.5")}


def test_settings_liefert_default_ereignis_keywords_und_schwellen_ohne_env() -> None:
    """@trace depot-ueberwachung#AC4,AC6 — ohne Env-Override liefert
    `Settings` die Default-Auslöser-Menge (AC4) und die Default-
    Ereignistyp-Schwellen."""
    settings = Settings(_env_file=None)

    assert list(settings.depot_ueberwachung_ereignis_keywords) == list(DEFAULT_EREIGNIS_KEYWORDS)
    assert settings.depot_ueberwachung_ereignis_schwellen == DEFAULT_EREIGNIS_SCHWELLEN


def test_settings_ueberschreibt_ereignis_keywords_ohne_codeaenderung(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """@trace depot-ueberwachung#AC4 — die Filter-Stichwortliste ist über
    `DEPOT_UEBERWACHUNG_EREIGNIS_KEYWORDS` (JSON-Array) ersetzbar."""
    monkeypatch.setenv("DEPOT_UEBERWACHUNG_EREIGNIS_KEYWORDS", '["Bussgeld"]')

    settings = Settings(_env_file=None)

    assert settings.depot_ueberwachung_ereignis_keywords == ["Bussgeld"]


def test_settings_ueberschreibt_ereignis_schwellen_ohne_codeaenderung(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """@trace depot-ueberwachung#AC6 — die Ereignistyp-Schwellen sind über
    `DEPOT_UEBERWACHUNG_EREIGNIS_SCHWELLEN` (JSON-Mapping) ersetzbar."""
    monkeypatch.setenv("DEPOT_UEBERWACHUNG_EREIGNIS_SCHWELLEN", '{"relativer_kurssturz": 0.03}')

    settings = Settings(_env_file=None)

    assert settings.depot_ueberwachung_ereignis_schwellen == {
        "relativer_kurssturz": Decimal("0.03")
    }


def test_settings_liefert_default_alert_fatigue_schwellwert_ohne_env() -> None:
    """@trace depot-ueberwachung#AC7 — ohne Env-Override ist der
    Alert-Fatigue-Tages-Schwellwert 10 (provisorischer Spec-Default)."""
    settings = Settings(_env_file=None)

    assert settings.depot_ueberwachung_ereignisse_pro_tag_schwellwert == 10


def test_settings_ueberschreibt_alert_fatigue_schwellwert_ohne_codeaenderung(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """@trace depot-ueberwachung#AC7 — der Alert-Fatigue-Tages-Schwellwert
    ist über `DEPOT_UEBERWACHUNG_EREIGNISSE_PRO_TAG_SCHWELLWERT`
    ersetzbar."""
    monkeypatch.setenv("DEPOT_UEBERWACHUNG_EREIGNISSE_PRO_TAG_SCHWELLWERT", "3")

    settings = Settings(_env_file=None)

    assert settings.depot_ueberwachung_ereignisse_pro_tag_schwellwert == 3
