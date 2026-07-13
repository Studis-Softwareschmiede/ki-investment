"""Tests für den Querschnitt-Filter der Kandidatensuche (Story S-029).

Covers (kandidatensuche): AC1, AC6

`app.domain.kandidatensuche.querschnitt_filter.erfuellt_querschnitt_filter`
deckt AC6 (Liquiditäts-Mindestschwelle + Volatilitäts-Fenster, auf jeden
Kandidaten angewandt); `baue_filterkriterien` deckt den Output-Vertrag
"Filterkriterien" (Main-Success-Scenario Schritt 4, kombiniert mit AC1)."""

from __future__ import annotations

from decimal import Decimal

from app.contracts.dateneingang import SignalBuendel
from app.contracts.kandidatensuche import QuerschnittFilter, Suchprofil, VolatilitaetsFenster
from app.domain.kandidatensuche.querschnitt_filter import (
    baue_filterkriterien,
    erfuellt_querschnitt_filter,
)

FILTER = QuerschnittFilter(
    liquiditaets_mindestschwelle=Decimal("2"),
    volatilitaets_fenster=VolatilitaetsFenster(min=Decimal("0.1"), max=Decimal("5")),
)


def _buendel(liquiditaet: Decimal | None, volatilitaet: Decimal | None) -> SignalBuendel:
    return SignalBuendel(
        titel="AAPL",
        anlageklasse=1,
        signale=[],
        liquiditaet=liquiditaet,
        volatilitaet=volatilitaet,
        quellen_metadaten=[],
    )


def test_kandidat_innerhalb_beider_schwellen_erfuellt_den_filter() -> None:
    """@trace kandidatensuche#AC6 — Liquidität >= Mindestschwelle UND
    Volatilität innerhalb des Fensters (inkl. Grenzen) → erfüllt."""
    assert erfuellt_querschnitt_filter(_buendel(Decimal("2"), Decimal("0.1")), FILTER) is True
    assert erfuellt_querschnitt_filter(_buendel(Decimal("3"), Decimal("5")), FILTER) is True


def test_kandidat_unter_liquiditaets_mindestschwelle_wird_ausgeschlossen() -> None:
    """@trace kandidatensuche#AC6 — "ein Titel, der die Liquiditäts-
    Mindestschwelle unterschreitet ... wird ausgeschlossen"."""
    assert erfuellt_querschnitt_filter(_buendel(Decimal("1.99"), Decimal("1")), FILTER) is False


def test_kandidat_ausserhalb_volatilitaets_fenster_wird_ausgeschlossen() -> None:
    """@trace kandidatensuche#AC6 — "... oder ausserhalb des Volatilitäts-
    Fensters liegt, wird ausgeschlossen" (zu tot UND zu wild)."""
    assert erfuellt_querschnitt_filter(_buendel(Decimal("5"), Decimal("0.05")), FILTER) is False
    assert erfuellt_querschnitt_filter(_buendel(Decimal("5"), Decimal("5.01")), FILTER) is False


def test_kandidat_ohne_liquiditaets_oder_volatilitaets_wert_wird_ausgeschlossen() -> None:
    """@trace kandidatensuche#AC6 — fehlt einer der beiden Werte (keine
    aggregierbare Quelle), gilt der Kandidat als NICHT erfüllt (Fail-Closed,
    kein Schätzen, siehe Edge-Cases-Präzisierung der Spec)."""
    assert erfuellt_querschnitt_filter(_buendel(None, Decimal("1")), FILTER) is False
    assert erfuellt_querschnitt_filter(_buendel(Decimal("5"), None), FILTER) is False
    assert erfuellt_querschnitt_filter(_buendel(None, None), FILTER) is False


def test_baue_filterkriterien_kombiniert_profil_signale_und_beide_schwellen_quellen() -> None:
    """@trace kandidatensuche#AC1,AC6 — `signale` = pflicht_bedingungen +
    optionale_signale; `schwellen` vereinigt Querschnitt-Filter- mit
    Profil-Schwellen (Main-Success-Scenario Schritt 4)."""
    profil = Suchprofil(
        anlageklasse=1,
        pflicht_bedingungen=["rvol_ueber_2x"],
        optionale_signale=["gap_up"],
        schwellen={"rvol_faktor": Decimal("2")},
    )

    kriterien = baue_filterkriterien(profil, FILTER)

    assert kriterien.anlageklasse == 1
    assert kriterien.signale == ["rvol_ueber_2x", "gap_up"]
    assert kriterien.schwellen == {
        "liquiditaets_mindestschwelle": Decimal("2"),
        "volatilitaets_fenster_min": Decimal("0.1"),
        "volatilitaets_fenster_max": Decimal("5"),
        "rvol_faktor": Decimal("2"),
    }


def test_baue_filterkriterien_profil_schwellen_haben_vorrang_bei_namenskollision() -> None:
    """@trace kandidatensuche#AC6 — kollidiert ein Profil-Schwellen-Key
    ausnahmsweise mit einem reservierten Querschnitt-Filter-Key, gewinnt
    die Profil-Schwelle (dokumentiertes Verhalten von `baue_filterkriterien`)."""
    profil = Suchprofil(
        anlageklasse=1,
        schwellen={"liquiditaets_mindestschwelle": Decimal("99")},
    )

    kriterien = baue_filterkriterien(profil, FILTER)

    assert kriterien.schwellen["liquiditaets_mindestschwelle"] == Decimal("99")
