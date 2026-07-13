"""Tests für die Kandidatensuche-Verträge (Story S-029).

Covers (kandidatensuche): AC1, AC6, AC7, AC10

`app.contracts.kandidatensuche.Suchprofil`/`QuerschnittFilter`/
`SuchprofilOverride`/`Filterkriterien` sind die Modul-Verträge des
Suchprofil-Frameworks (architecture.md §2 P2). Diese Tests decken die
strukturelle Validierung (Anlageklassen-Wertebereich AC1, Immutabilität,
`extra="forbid"`) — die eigentliche Auswahl-/Filterlogik wird in
`tests/domain/kandidatensuche/` getestet.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.contracts.kandidatensuche import (
    Filterkriterien,
    QuerschnittFilter,
    Suchprofil,
    SuchprofilOverride,
    VolatilitaetsFenster,
)


def test_suchprofil_default_modus_ist_eventbasiert() -> None:
    """@trace kandidatensuche#AC7 — ohne explizite Angabe ist `eventbasiert`
    der bevorzugte, provisorische Default-Suchmodus."""
    profil = Suchprofil(anlageklasse=1)
    assert profil.modus == "eventbasiert"


@pytest.mark.parametrize("invalid_anlageklasse", [0, -1, 12, 100])
def test_suchprofil_rejects_anlageklasse_outside_1_to_11(invalid_anlageklasse: int) -> None:
    """@trace kandidatensuche#AC1 — die Anlageklasse eines Suchprofils
    steuert die Registry-Zuordnung und muss im gültigen Wertebereich 1..11
    liegen (analog `Datenpunkt.anlageklassen_tag`, dateneingang#AC2)."""
    with pytest.raises(ValidationError):
        Suchprofil(anlageklasse=invalid_anlageklasse)


def test_suchprofil_rejects_unbekannten_suchmodus() -> None:
    """@trace kandidatensuche#AC7 — ein dritter, nicht in der Spec genannter
    Suchmodus (nur eventbasiert|periodisch) wird von pydantic verweigert."""
    with pytest.raises(ValidationError):
        Suchprofil(anlageklasse=1, modus="taeglich")


def test_suchprofil_is_immutable() -> None:
    """@trace kandidatensuche#AC1 — Suchprofil ist frozen (unveränderliches
    DTO, passend zum Modul-Vertrag P2)."""
    profil = Suchprofil(anlageklasse=1)
    with pytest.raises(ValidationError):
        profil.anlageklasse = 2  # type: ignore[misc]


def test_suchprofil_rejects_unbekanntes_feld() -> None:
    """@trace kandidatensuche#AC1 — `extra="forbid"`: ein unbekanntes Feld
    (z.B. Tippfehler) wird von pydantic verweigert statt stillschweigend
    ignoriert."""
    with pytest.raises(ValidationError):
        Suchprofil(anlageklasse=1, unbekanntes_feld="x")  # type: ignore[call-arg]


def test_suchprofil_override_default_hat_kein_modus_und_leere_schwellen() -> None:
    """@trace kandidatensuche#AC7,AC10 — ein Override ohne Angaben ändert
    (per Konvention der konsumierenden Domain-Funktion) nichts am Profil."""
    override = SuchprofilOverride()
    assert override.modus is None
    assert override.schwellen == {}


def test_querschnitt_filter_traegt_liquiditaet_und_volatilitaets_fenster() -> None:
    """@trace kandidatensuche#AC6 — der Querschnitt-Filter-Vertrag trägt
    exakt die zwei laut Spec genannten Schwellen."""
    filter_ = QuerschnittFilter(
        liquiditaets_mindestschwelle=Decimal("2"),
        volatilitaets_fenster=VolatilitaetsFenster(min=Decimal("0.1"), max=Decimal("5")),
    )
    assert filter_.liquiditaets_mindestschwelle == Decimal("2")
    assert filter_.volatilitaets_fenster.min == Decimal("0.1")
    assert filter_.volatilitaets_fenster.max == Decimal("5")


def test_querschnitt_filter_is_immutable() -> None:
    """@trace kandidatensuche#AC6 — QuerschnittFilter ist frozen."""
    filter_ = QuerschnittFilter(
        liquiditaets_mindestschwelle=Decimal("1"),
        volatilitaets_fenster=VolatilitaetsFenster(min=Decimal("0"), max=Decimal("1")),
    )
    with pytest.raises(ValidationError):
        filter_.liquiditaets_mindestschwelle = Decimal("99")  # type: ignore[misc]


def test_filterkriterien_traegt_anlageklasse_signale_und_schwellen() -> None:
    """@trace kandidatensuche#AC1,AC6 — der Output-Vertrag an die
    Datenquellen-Abfrage trägt exakt `{anlageklasse, signale, schwellen}`
    (Verträge "Output an Datenquellen-Abfrage")."""
    kriterien = Filterkriterien(
        anlageklasse=7,
        signale=["rvol", "funding_rate"],
        schwellen={"rvol_faktor": Decimal("2")},
    )
    assert kriterien.anlageklasse == 7
    assert kriterien.signale == ["rvol", "funding_rate"]
    assert kriterien.schwellen == {"rvol_faktor": Decimal("2")}
