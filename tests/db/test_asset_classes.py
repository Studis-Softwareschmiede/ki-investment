"""Tests für den Anlageklassen-Lese-/Schreibpfad `app/db/asset_classes.py`
(Story S-069, `docs/specs/frontend-cockpit.md` AC9; Story S-074, AC20).

Covers (frontend-cockpit): AC9, AC20

`lade_alle_anlageklassen()` liest die seed-gepflegten `AssetClass`-Zeilen
(Toggle-Zustand `aktiv` + `prio_stufe`) direkt als
`AnlageklasseEintrag`-Vertrag, sortiert nach `id`. `setze_toggle()` (S-074)
ist der Konfig-Schreibpfad hinter `POST /api/control/anlageklassen/
{id}/toggle` — schreibt dieselbe `aktiv`-Spalte, die `lade_alle_
anlageklassen()` liest."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.contracts.anlageklassen_config import AnlageklasseEintrag
from app.db.asset_classes import lade_alle_anlageklassen, setze_toggle
from app.db.base import Base
from app.db.models import AssetClass


def _session_mit_anlageklassen(*eintraege: AssetClass) -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    for eintrag in eintraege:
        session.add(eintrag)
    session.commit()
    return session


def test_lade_alle_anlageklassen_liefert_leere_liste_ohne_seed_daten() -> None:
    session = _session_mit_anlageklassen()

    ergebnis = lade_alle_anlageklassen(session)

    assert ergebnis == []


def test_lade_alle_anlageklassen_liefert_toggle_zustand_und_prio_sortiert_nach_id() -> None:
    session = _session_mit_anlageklassen(
        AssetClass(id=2, name="ETFs", prio_stufe="MVP", aktiv=True),
        AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True),
        AssetClass(id=10, name="FX", prio_stufe="Stufe3", aktiv=False),
    )

    ergebnis = lade_alle_anlageklassen(session)

    assert ergebnis == [
        AnlageklasseEintrag(id=1, name="Aktien", aktiv=True, prio_stufe="MVP"),
        AnlageklasseEintrag(id=2, name="ETFs", aktiv=True, prio_stufe="MVP"),
        AnlageklasseEintrag(id=10, name="FX", aktiv=False, prio_stufe="Stufe3"),
    ]


def test_lade_alle_anlageklassen_bildet_deaktivierte_klasse_korrekt_ab() -> None:
    session = _session_mit_anlageklassen(
        AssetClass(id=10, name="FX", prio_stufe="Stufe3", aktiv=False),
    )

    ergebnis = lade_alle_anlageklassen(session)

    assert ergebnis[0].aktiv is False


def test_setze_toggle_deaktiviert_eine_aktive_anlageklasse() -> None:
    """@trace frontend-cockpit#AC20 — `setze_toggle` schreibt `aktiv=False`
    und liefert den aktualisierten Cockpit-Eintrag zurück."""
    session = _session_mit_anlageklassen(
        AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True),
    )

    ergebnis = setze_toggle(session, 1, False)

    assert ergebnis == AnlageklasseEintrag(id=1, name="Aktien", aktiv=False, prio_stufe="MVP")


def test_setze_toggle_aktiviert_eine_inaktive_anlageklasse_und_persistiert() -> None:
    """@trace frontend-cockpit#AC20 — die Änderung ist committed: ein
    nachfolgendes `lade_alle_anlageklassen` sieht denselben Zustand."""
    session = _session_mit_anlageklassen(
        AssetClass(id=10, name="FX", prio_stufe="Stufe3", aktiv=False),
    )

    setze_toggle(session, 10, True)

    ergebnis = lade_alle_anlageklassen(session)
    assert ergebnis[0].aktiv is True


def test_setze_toggle_liefert_none_fuer_unbekannte_anlageklasse() -> None:
    """@trace frontend-cockpit#AC20 — eine nicht existierende
    `asset_class_id` liefert `None` (der Router meldet das als 404), statt
    stillschweigend eine Zeile anzulegen."""
    session = _session_mit_anlageklassen()

    ergebnis = setze_toggle(session, 5, True)

    assert ergebnis is None
