"""Tests für den Anlageklassen-Lese-/Schreibpfad `app/db/asset_classes.py`
(Story S-069, `docs/specs/frontend-cockpit.md` AC9; Story S-074, AC20;
Story S-076, AC18).

Covers (frontend-cockpit): AC9, AC20, AC18

`lade_alle_anlageklassen()` liest die seed-gepflegten `AssetClass`-Zeilen
(Toggle-Zustand `aktiv` + `prio_stufe`) direkt als
`AnlageklasseEintrag`-Vertrag, sortiert nach `id`. `setze_toggle()` (S-074)
ist der Konfig-Schreibpfad hinter `POST /api/control/anlageklassen/
{id}/toggle` — schreibt dieselbe `aktiv`-Spalte, die `lade_alle_
anlageklassen()` liest.

S-076 (AC18, → BR-018) ergänzt: beide Funktionen liefern zusätzlich
`hat_offene_positionen`, ermittelt über eine `Position.status == "offen"`-
Abfrage (modus-übergreifend)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.contracts.anlageklassen_config import AnlageklasseEintrag
from app.db.asset_classes import lade_alle_anlageklassen, setze_toggle
from app.db.base import Base
from app.db.models import AssetClass, Instrument, Position, Strategy, TimeHorizon


def _session_mit_anlageklassen(*eintraege: AssetClass) -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    for eintrag in eintraege:
        session.add(eintrag)
    session.commit()
    return session


def _seed_offene_position(session: Session, *, asset_class_id: int, status: str = "offen") -> None:
    """Legt eine minimale, valide Positions-Zeile (+ die dafür nötigen
    Stammdaten-Zeilen: `Instrument`/`Strategy`/`TimeHorizon`) für
    `asset_class_id` an (analog `tests/adapters/repositories
    /test_position_repository.py::_seed_stammdaten`/`_make_position`)."""
    session.add(
        TimeHorizon(
            id=8,
            name="Buy-and-Hold",
            transaktionskosten_relevanz="MINIMAL",
            break_even_anforderung="Jahresrendite nach Kosten",
        )
    )
    strategy = Strategy(id=uuid.uuid4(), name="Index", cluster="passiv_regelbasiert", stufe="MVP")
    session.add(strategy)
    instrument = Instrument(
        id=uuid.uuid4(),
        symbol="ACME",
        name="Acme Corp",
        asset_class_id=asset_class_id,
        currency="CHF",
    )
    session.add(instrument)
    session.add(
        Position(
            id=uuid.uuid4(),
            instrument_id=instrument.id,
            asset_class_id=asset_class_id,
            strategy_id=strategy.id,
            time_horizon_id=8,
            these="These.",
            menge=Decimal("10"),
            einstand_preis=Decimal("100"),
            mode="simuliert",
            status=status,
        )
    )
    session.commit()


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


def test_lade_alle_anlageklassen_markiert_klasse_mit_offener_position() -> None:
    """@trace frontend-cockpit#AC18,BR-018 — eine Klasse mit mindestens
    einer offenen Position liefert `hat_offene_positionen=True`."""
    session = _session_mit_anlageklassen(
        AssetClass(id=7, name="Kryptowährungen", prio_stufe="MVP", aktiv=True),
    )
    _seed_offene_position(session, asset_class_id=7)

    ergebnis = lade_alle_anlageklassen(session)

    assert ergebnis[0].hat_offene_positionen is True


def test_lade_alle_anlageklassen_ignoriert_geschlossene_position() -> None:
    """@trace frontend-cockpit#AC18,BR-018 — nur `status="offen"` zählt,
    eine vollständig geschlossene Position löst kein Warn-Band aus."""
    session = _session_mit_anlageklassen(
        AssetClass(id=7, name="Kryptowährungen", prio_stufe="MVP", aktiv=True),
    )
    _seed_offene_position(session, asset_class_id=7, status="geschlossen")

    ergebnis = lade_alle_anlageklassen(session)

    assert ergebnis[0].hat_offene_positionen is False


def test_lade_alle_anlageklassen_ohne_position_liefert_hat_offene_positionen_false() -> None:
    """@trace frontend-cockpit#AC18,BR-018 — Default-/Cold-Start-Fall ohne
    jede Positions-Zeile."""
    session = _session_mit_anlageklassen(
        AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True),
    )

    ergebnis = lade_alle_anlageklassen(session)

    assert ergebnis[0].hat_offene_positionen is False


def test_setze_toggle_deaktivierung_mit_offener_position_bleibt_erlaubt_und_meldet_flag() -> None:
    """@trace frontend-cockpit#AC18,BR-018 — BR-018 ist keine Schreib-
    Sperre: die Deaktivierung einer Klasse mit offener Position gelingt,
    der zurückgelieferte Eintrag markiert `hat_offene_positionen=True`
    (Grundlage des Konfigurations-View-Warn-Bands)."""
    session = _session_mit_anlageklassen(
        AssetClass(id=7, name="Kryptowährungen", prio_stufe="MVP", aktiv=True),
    )
    _seed_offene_position(session, asset_class_id=7)

    ergebnis = setze_toggle(session, 7, False)

    assert ergebnis == AnlageklasseEintrag(
        id=7,
        name="Kryptowährungen",
        aktiv=False,
        prio_stufe="MVP",
        hat_offene_positionen=True,
    )
