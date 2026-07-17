"""Tests für die Alert-Fatigue-Leitplanke (Story S-033).

Covers (depot-ueberwachung): AC7

`app.core.monitoring_kennzahlen` zählt die je Tag registrierten
Überwachungs-Ereignisse und markiert `zu_sensibel=True`, sobald der
konfigurierte Tages-Schwellwert (Default 10) STRIKT überschritten wird."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.config import get_settings
from app.core import monitoring_kennzahlen


@pytest.fixture(autouse=True)
def _isolieren():
    monitoring_kennzahlen.reset_fuer_tests()
    get_settings.cache_clear()
    yield
    monitoring_kennzahlen.reset_fuer_tests()
    get_settings.cache_clear()


_JETZT = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


def test_ohne_registrierte_ereignisse_ist_die_kennzahl_null_und_nicht_zu_sensibel() -> None:
    """@trace depot-ueberwachung#AC7 — keine registrierten Ereignisse ->
    `ereignisse_pro_tag=0`, `zu_sensibel=False`."""
    kennzahl = monitoring_kennzahlen.berechne_tageskennzahl(tag=_JETZT.date())
    assert kennzahl.ereignisse_pro_tag == 0
    assert kennzahl.zu_sensibel is False
    assert kennzahl.schwellwert == 10


def test_registrierte_ereignisse_unter_der_schwelle_bleiben_unauffaellig() -> None:
    """@trace depot-ueberwachung#AC7 — 5 Ereignisse an einem Tag (Default-
    Schwelle 10) -> nicht zu sensibel."""
    monitoring_kennzahlen.registriere_ereignisse(5, zeitpunkt=_JETZT)
    kennzahl = monitoring_kennzahlen.berechne_tageskennzahl(tag=_JETZT.date())
    assert kennzahl.ereignisse_pro_tag == 5
    assert kennzahl.zu_sensibel is False


def test_genau_an_der_schwelle_wird_nicht_als_zu_sensibel_signalisiert() -> None:
    """@trace depot-ueberwachung#AC7 — Grenzfall: genau 10 Ereignisse
    (Default-Schwelle) lösen KEIN "zu sensibel" aus (STRIKT `>`)."""
    monitoring_kennzahlen.registriere_ereignisse(10, zeitpunkt=_JETZT)
    kennzahl = monitoring_kennzahlen.berechne_tageskennzahl(tag=_JETZT.date())
    assert kennzahl.ereignisse_pro_tag == 10
    assert kennzahl.zu_sensibel is False


def test_ueberschreitung_der_schwelle_signalisiert_zu_sensibel() -> None:
    """@trace depot-ueberwachung#AC7 — 11 Ereignisse (> Default-Schwelle
    10) -> `zu_sensibel=True`."""
    monitoring_kennzahlen.registriere_ereignisse(11, zeitpunkt=_JETZT)
    kennzahl = monitoring_kennzahlen.berechne_tageskennzahl(tag=_JETZT.date())
    assert kennzahl.zu_sensibel is True


def test_ereignisse_eines_anderen_tages_zaehlen_nicht_mit() -> None:
    """@trace depot-ueberwachung#AC7 — die Tageskennzahl zählt nur
    Ereignisse DES angefragten Kalendertags, nicht kumulativ über alle
    Tage."""
    gestern = _JETZT - timedelta(days=1)
    monitoring_kennzahlen.registriere_ereignisse(11, zeitpunkt=gestern)
    monitoring_kennzahlen.registriere_ereignisse(2, zeitpunkt=_JETZT)
    kennzahl_heute = monitoring_kennzahlen.berechne_tageskennzahl(tag=_JETZT.date())
    kennzahl_gestern = monitoring_kennzahlen.berechne_tageskennzahl(tag=gestern.date())
    assert kennzahl_heute.ereignisse_pro_tag == 2
    assert kennzahl_heute.zu_sensibel is False
    assert kennzahl_gestern.ereignisse_pro_tag == 11
    assert kennzahl_gestern.zu_sensibel is True


def test_ohne_tag_wird_das_heutige_datum_verwendet() -> None:
    """@trace depot-ueberwachung#AC7 — `tag=None` (Default) wertet den
    heutigen Kalendertag (UTC) aus."""
    kennzahl = monitoring_kennzahlen.berechne_tageskennzahl()
    assert kennzahl.datum == datetime.now(UTC).date()


def test_schwellwert_ist_ohne_codeaenderung_konfigurierbar(monkeypatch: pytest.MonkeyPatch) -> None:
    """@trace depot-ueberwachung#AC7 — der Tages-Schwellwert ist
    konfigurierbar (`DEPOT_UEBERWACHUNG_EREIGNISSE_PRO_TAG_SCHWELLWERT`)."""
    monkeypatch.setenv("DEPOT_UEBERWACHUNG_EREIGNISSE_PRO_TAG_SCHWELLWERT", "2")
    get_settings.cache_clear()
    monitoring_kennzahlen.registriere_ereignisse(3, zeitpunkt=_JETZT)
    kennzahl = monitoring_kennzahlen.berechne_tageskennzahl(tag=_JETZT.date())
    assert kennzahl.schwellwert == 2
    assert kennzahl.zu_sensibel is True


def test_nulleintraege_registrieren_nichts() -> None:
    """@trace depot-ueberwachung#AC7 — `registriere_ereignisse(0)` ist ein
    No-Op (kein künstlicher Eintrag ohne tatsächliches Ereignis)."""
    monitoring_kennzahlen.registriere_ereignisse(0, zeitpunkt=_JETZT)
    kennzahl = monitoring_kennzahlen.berechne_tageskennzahl(tag=_JETZT.date())
    assert kennzahl.ereignisse_pro_tag == 0


def test_datum_typ() -> None:
    """@trace depot-ueberwachung#AC7 — `datum` ist ein `date`, kein
    `datetime` (reiner Kalendertag)."""
    kennzahl = monitoring_kennzahlen.berechne_tageskennzahl(tag=_JETZT.date())
    assert isinstance(kennzahl.datum, date)
