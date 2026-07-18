"""Tests für den Anlageklassen-Lesepfad `app/db/asset_classes.py` (Story
S-069, `docs/specs/frontend-cockpit.md` AC9).

Covers (frontend-cockpit): AC9

`lade_alle_anlageklassen()` liest die seed-gepflegten `AssetClass`-Zeilen
(Toggle-Zustand `aktiv` + `prio_stufe`) direkt als
`AnlageklasseEintrag`-Vertrag, sortiert nach `id`."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.contracts.anlageklassen_config import AnlageklasseEintrag
from app.db.asset_classes import lade_alle_anlageklassen
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
