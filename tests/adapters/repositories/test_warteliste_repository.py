"""Tests für `SqlAlchemyWartelisteRepository` (Story S-079,
`docs/specs/frontend-cockpit.md` AC26).

Covers (frontend-cockpit): AC26

Prüft `app.adapters.repositories.warteliste_repository
.SqlAlchemyWartelisteRepository` gegen eine SQLite-In-Memory-DB: Titel-
Auflösung über `instrument` (analog `SqlAlchemyKandidatenRepository`,
coder-Lesson S-073), Mode-Isolation (→ BR-130), Sortierung
(`blockiert_am` absteigend, neueste zuerst)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.adapters.repositories.warteliste_repository import SqlAlchemyWartelisteRepository
from app.db.base import Base
from app.db.models import AssetClass, Instrument
from app.db.models import WartelisteEintrag as WartelisteEintragModell


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _instrument(
    session: Session, *, symbol: str = "CHSPI", name: str = "iShares Swiss Dividend ETF"
):
    asset_class = session.get(AssetClass, 2)
    if asset_class is None:
        session.add(AssetClass(id=2, name="ETFs", prio_stufe="MVP", aktiv=True))
        session.commit()
    instrument = Instrument(
        id=uuid.uuid4(), symbol=symbol, name=name, asset_class_id=2, currency="CHF"
    )
    session.add(instrument)
    session.commit()
    return instrument


def _eintrag(
    session: Session,
    instrument: Instrument,
    *,
    mode: str = "simuliert",
    blockade_grund: str = "klumpenrisiko",
    geplante_groesse: Decimal = Decimal("1000"),
    blockiert_am: datetime,
) -> WartelisteEintragModell:
    eintrag = WartelisteEintragModell(
        id=uuid.uuid4(),
        instrument_id=instrument.id,
        asset_class_id=instrument.asset_class_id,
        geplante_groesse=geplante_groesse,
        blockade_grund=blockade_grund,
        mode=mode,
        blockiert_am=blockiert_am,
    )
    session.add(eintrag)
    session.commit()
    return eintrag


def test_liste_warteliste_liefert_titel_symbol_und_name_aus_instrument() -> None:
    """@trace frontend-cockpit#AC26 — der menschenlesbare Titel (`symbol`/
    `name` aus `instrument`), nicht nur die rohe `instrument_id`."""
    session = _session()
    instrument = _instrument(session)
    _eintrag(session, instrument, blockiert_am=datetime(2026, 6, 10, tzinfo=UTC))
    repository = SqlAlchemyWartelisteRepository(session)

    eintraege = repository.liste_warteliste(mode="simuliert")

    assert len(eintraege) == 1
    assert eintraege[0].titel_id == str(instrument.id)
    assert eintraege[0].titel == "CHSPI"
    assert eintraege[0].name == "iShares Swiss Dividend ETF"
    assert eintraege[0].asset_class_id == 2
    assert eintraege[0].geplante_groesse == Decimal("1000")
    assert eintraege[0].blockade_grund == "klumpenrisiko"


def test_liste_warteliste_ist_mode_isoliert() -> None:
    """@trace frontend-cockpit#AC26 — → BR-130: `echt`- und
    `simuliert`-Einträge werden nie vermischt."""
    session = _session()
    instrument = _instrument(session)
    _eintrag(session, instrument, mode="simuliert", blockiert_am=datetime(2026, 6, 10, tzinfo=UTC))
    _eintrag(session, instrument, mode="echt", blockiert_am=datetime(2026, 6, 11, tzinfo=UTC))
    repository = SqlAlchemyWartelisteRepository(session)

    assert len(repository.liste_warteliste(mode="simuliert")) == 1
    assert len(repository.liste_warteliste(mode="echt")) == 1


def test_liste_warteliste_sortiert_neueste_zuerst() -> None:
    """@trace frontend-cockpit#AC26 — `blockiert_am` absteigend."""
    session = _session()
    instrument = _instrument(session)
    aeltere = _eintrag(session, instrument, blockiert_am=datetime(2026, 1, 1, tzinfo=UTC))
    neuere = _eintrag(session, instrument, blockiert_am=datetime(2026, 6, 1, tzinfo=UTC))
    repository = SqlAlchemyWartelisteRepository(session)

    eintraege = repository.liste_warteliste(mode="simuliert")

    assert [e.id for e in eintraege] == [str(neuere.id), str(aeltere.id)]


def test_liste_warteliste_liefert_leere_liste_ohne_eintraege() -> None:
    """@trace frontend-cockpit#AC26,AC27 — Grundlage des definierten
    Empty-States (E2-Muster)."""
    session = _session()
    repository = SqlAlchemyWartelisteRepository(session)

    assert repository.liste_warteliste(mode="simuliert") == []
