"""Tests für den Einstiegspunkt des Kandidatensuche-Frameworks (Story
S-029) — zusammengeführte AC1+AC6+AC9+AC10-Pipeline.

Covers (kandidatensuche): AC1, AC6, AC9, AC10

`app.domain.kandidatensuche.kandidatensuche.erstelle_filterkriterien`
kombiniert Toggle-Disziplin (AC9), Suchprofil-Auswahl (AC1, inkl.
AC7/AC10-Overrides) und Querschnitt-Filter (AC6) zum Output-Vertrag
`Filterkriterien`."""

from __future__ import annotations

from decimal import Decimal

from app.contracts.anlageklassen_config import ToggleZustand
from app.contracts.kandidatensuche import (
    QuerschnittFilter,
    Suchprofil,
    SuchprofilOverride,
    VolatilitaetsFenster,
)
from app.domain.kandidatensuche.kandidatensuche import erstelle_filterkriterien

FILTER = QuerschnittFilter(
    liquiditaets_mindestschwelle=Decimal("1"),
    volatilitaets_fenster=VolatilitaetsFenster(min=Decimal("0"), max=Decimal("100")),
)
PROFIL_KLASSE_1 = Suchprofil(
    anlageklasse=1, pflicht_bedingungen=["rvol_ueber_2x"], schwellen={"rvol_faktor": Decimal("2")}
)


def test_aktive_klasse_mit_registriertem_profil_liefert_filterkriterien() -> None:
    """@trace kandidatensuche#AC1,AC6,AC9 — Normalbetrieb: aktive Klasse +
    registriertes Profil → vollständige Filterkriterien inkl.
    Querschnitt-Filter-Schwellen."""
    kriterien = erstelle_filterkriterien(
        registry={1: PROFIL_KLASSE_1},
        anlageklasse=1,
        zustand=ToggleZustand(aktiv=True),
        querschnitt_filter=FILTER,
    )

    assert kriterien is not None
    assert kriterien.anlageklasse == 1
    assert kriterien.signale == ["rvol_ueber_2x"]
    assert kriterien.schwellen["rvol_faktor"] == Decimal("2")
    assert kriterien.schwellen["liquiditaets_mindestschwelle"] == Decimal("1")


def test_inaktive_klasse_liefert_keine_filterkriterien() -> None:
    """@trace kandidatensuche#AC9 — deckt A1: für eine per Toggle
    deaktivierte Anlageklasse werden keine Filterkriterien gebildet (kein
    Suchprofil geladen, keine Datenquellen-Abfrage ausgelöst)."""
    kriterien = erstelle_filterkriterien(
        registry={1: PROFIL_KLASSE_1},
        anlageklasse=1,
        zustand=ToggleZustand(aktiv=False),
        querschnitt_filter=FILTER,
    )

    assert kriterien is None


def test_aktive_klasse_ohne_registriertes_profil_liefert_keine_filterkriterien() -> None:
    """@trace kandidatensuche#AC1 — kein einheitlicher Filter: ist für die
    angefragte Klasse kein Profil registriert, gibt es KEIN Ausweichen auf
    ein anderes Profil."""
    kriterien = erstelle_filterkriterien(
        registry={7: Suchprofil(anlageklasse=7)},
        anlageklasse=1,
        zustand=ToggleZustand(aktiv=True),
        querschnitt_filter=FILTER,
    )

    assert kriterien is None


def test_override_wirkt_bis_in_die_finalen_filterkriterien_durch() -> None:
    """@trace kandidatensuche#AC10 — ein AC10-Schwellen-Override (ohne
    Codeänderung) wirkt bis in die an die Datenquellen-Abfrage übergebenen
    Filterkriterien durch."""
    kriterien = erstelle_filterkriterien(
        registry={1: PROFIL_KLASSE_1},
        anlageklasse=1,
        zustand=ToggleZustand(aktiv=True),
        querschnitt_filter=FILTER,
        overrides={1: SuchprofilOverride(schwellen={"rvol_faktor": Decimal("2.5")})},
    )

    assert kriterien is not None
    assert kriterien.schwellen["rvol_faktor"] == Decimal("2.5")
