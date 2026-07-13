"""Tests für die Dateneingang-Verträge: Socket-Datenpunkt (Story S-005) +
geteilte Datenquellen-Abfrage (Story S-021).

Covers (dateneingang): AC1, AC2, AC7

`app.contracts.dateneingang.Datenpunkt` ist der Modul-Vertrag Socket →
Datenquellen-Abfrage (architecture.md §2 P2). Diese Tests decken AC1 (ein
einheitliches, unveränderliches Schema über alle Quellen) und AC2
(Pflicht-Metadaten `quelle`/`timestamp`/`anlageklassen_tag`/
`qualitaetsindikator`; fehlt eine oder liegt `anlageklassen_tag` ausserhalb
1..11, verweigert pydantic die Instanziierung — der Datenpunkt gilt als
ungültig und wird nicht gebaut).

`SignalBuendelAnfrage`/`TitelAnfrage`/`SignalBuendel` sind die Verträge der
geteilten Datenquellen-Abfrage (AC7, "eine Schnittstelle, drei
Konsumenten"): diese Tests decken die Eingabe-Validierung (ungültige
Anlageklasse, leere Titel-Liste, unbekannter Konsumenten-Kontext werden von
pydantic verweigert) — die Aggregationslogik selbst (AC8) wird in
`tests/orchestration/test_datasource_query.py` getestet.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.contracts.dateneingang import (
    Datenpunkt,
    SignalBuendelAnfrage,
    TitelAnfrage,
)

VALID_KWARGS = {
    "wert": 42.0,
    "quelle": "fred",
    "timestamp": datetime(2026, 7, 1, tzinfo=UTC),
    "anlageklassen_tag": 9,
    "qualitaetsindikator": "roh",
}


def test_accepts_datenpunkt_with_all_pflicht_metadaten() -> None:
    """@trace dateneingang#AC1,AC2 — ein Datenpunkt mit allen vier
    Pflicht-Metadaten (quelle, timestamp, anlageklassen_tag,
    qualitaetsindikator) wird gebaut und behält exakt diese Felder."""
    punkt = Datenpunkt(**VALID_KWARGS)
    assert punkt.quelle == "fred"
    assert punkt.anlageklassen_tag == 9
    assert punkt.qualitaetsindikator == "roh"
    assert punkt.timestamp == VALID_KWARGS["timestamp"]


@pytest.mark.parametrize(
    "missing_field", ["quelle", "timestamp", "anlageklassen_tag", "qualitaetsindikator"]
)
def test_rejects_datenpunkt_missing_pflicht_metadatum(missing_field: str) -> None:
    """@trace dateneingang#AC2 — fehlt eine Pflicht-Metadatum, verweigert
    pydantic die Instanziierung (Datenpunkt gilt als ungültig und wird nicht
    weitergereicht)."""
    kwargs = dict(VALID_KWARGS)
    del kwargs[missing_field]
    with pytest.raises(ValidationError):
        Datenpunkt(**kwargs)


@pytest.mark.parametrize("invalid_tag", [0, -1, 12, 100])
def test_rejects_anlageklassen_tag_outside_1_to_11(invalid_tag: int) -> None:
    """@trace dateneingang#AC2 — anlageklassen_tag ausserhalb des
    gültigen Bereichs 1..11 ist ungültig."""
    kwargs = dict(VALID_KWARGS, anlageklassen_tag=invalid_tag)
    with pytest.raises(ValidationError):
        Datenpunkt(**kwargs)


def test_rejects_empty_quelle_and_qualitaetsindikator() -> None:
    """@trace dateneingang#AC2 — leere Strings zählen als fehlendes
    Metadatum (nicht nur `None`/Schlüssel-Abwesenheit)."""
    with pytest.raises(ValidationError):
        Datenpunkt(**dict(VALID_KWARGS, quelle=""))
    with pytest.raises(ValidationError):
        Datenpunkt(**dict(VALID_KWARGS, qualitaetsindikator=""))


def test_datenpunkt_is_immutable() -> None:
    """@trace dateneingang#AC1 — Datenpunkt ist frozen (unveränderliches
    DTO, passend zum Modul-Vertrag P2) — nachträgliches Mutieren eines
    Feldes schlägt fehl."""
    punkt = Datenpunkt(**VALID_KWARGS)
    with pytest.raises(ValidationError):
        punkt.quelle = "andere-quelle"


def test_signal_buendel_anfrage_accepts_valid_titel_anfragen_je_konsumenten_kontext() -> None:
    """@trace dateneingang#AC7 — die geteilte Datenquellen-Abfrage akzeptiert
    denselben Anfrage-DTO für alle drei laut Spec genannten
    Konsumenten-Kontexte (neu/bestehend/research)."""
    for kontext in ("neu", "bestehend", "research"):
        anfrage = SignalBuendelAnfrage(
            titel_anfragen=[TitelAnfrage(titel="AAPL", anlageklasse=1)],
            konsumenten_kontext=kontext,
        )
        assert anfrage.konsumenten_kontext == kontext
        assert anfrage.titel_anfragen[0].titel == "AAPL"


def test_signal_buendel_anfrage_rejects_unbekannten_konsumenten_kontext() -> None:
    """@trace dateneingang#AC7 — ein vierter, nicht in der Spec genannter
    Konsumenten-Kontext wird von pydantic verweigert (kein stillschweigend
    akzeptierter Fremd-Konsument)."""
    with pytest.raises(ValidationError):
        SignalBuendelAnfrage(
            titel_anfragen=[TitelAnfrage(titel="AAPL", anlageklasse=1)],
            konsumenten_kontext="sonstwas",
        )


def test_signal_buendel_anfrage_rejects_leere_titel_anfragen() -> None:
    """@trace dateneingang#AC7 — eine Anfrage ohne mindestens eine
    Titel-Anfrage ist ungültig."""
    with pytest.raises(ValidationError):
        SignalBuendelAnfrage(titel_anfragen=[], konsumenten_kontext="neu")


@pytest.mark.parametrize("invalid_anlageklasse", [0, -1, 12, 100])
def test_titel_anfrage_rejects_anlageklasse_outside_1_to_11(invalid_anlageklasse: int) -> None:
    """@trace dateneingang#AC7,AC8 — die Anlageklasse einer Titel-Anfrage
    steuert die Registry-Auswahl (AC8) und muss daher im gültigen
    Wertebereich 1..11 liegen (analog `Datenpunkt.anlageklassen_tag`, AC2)."""
    with pytest.raises(ValidationError):
        TitelAnfrage(titel="AAPL", anlageklasse=invalid_anlageklasse)
