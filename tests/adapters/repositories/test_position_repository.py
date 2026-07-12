"""Tests für `SqlAlchemyPositionRepository` (Story S-015).

Covers (depot): AC10

Deckt die Bestandsermittlung, auf der `app.domain.portfolio.fill_booking
.pruefe_fill` die AC10-Prüfung "keine resultierende negative Menge"
aufbaut: `aktuelle_menge()` liefert 0 ohne offene Position, die Menge einer
einzelnen offenen Position, die Summe mehrerer offener Positionen und
ignoriert geschlossene Positionen.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.adapters.repositories.position_repository import SqlAlchemyPositionRepository
from app.db.base import Base
from app.db.models import AssetClass, Instrument, Position, Strategy, TimeHorizon


def _make_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _seed_stammdaten(session: Session) -> tuple[uuid.UUID, uuid.UUID]:
    # `id`-Spalten (UUID) tragen `server_default=gen_random_uuid()` (nur
    # unter Postgres verfügbar) — unter SQLite (In-Memory) daher explizit.
    session.add(AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True, retail_driven=True))
    session.add(TimeHorizon(id=8, name="Buy-and-Hold"))
    strategy = Strategy(id=uuid.uuid4(), name="Index")
    session.add(strategy)
    instrument = Instrument(
        id=uuid.uuid4(), symbol="ACME", name="Acme Corp", asset_class_id=1, currency="CHF"
    )
    session.add(instrument)
    session.commit()
    return instrument.id, strategy.id


def _make_position(instrument_id, strategy_id, *, menge: Decimal, status: str) -> Position:
    return Position(
        id=uuid.uuid4(),
        instrument_id=instrument_id,
        asset_class_id=1,
        strategy_id=strategy_id,
        time_horizon_id=8,
        these="These.",
        menge=menge,
        einstand_preis=Decimal("100"),
        mode="simuliert",
        status=status,
    )


def test_aktuelle_menge_ist_null_ohne_offene_position() -> None:
    """@trace depot#AC10 — kein Bestand für einen Titel ohne (offene)
    Position ergibt 0, nicht einen Fehler."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, _strategy_id = _seed_stammdaten(session)
        repository = SqlAlchemyPositionRepository(session)
        assert repository.aktuelle_menge(str(instrument_id)) == Decimal("0")


def test_aktuelle_menge_liefert_menge_der_offenen_position() -> None:
    """@trace depot#AC10 — Bestand einer einzelnen offenen Position."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, strategy_id = _seed_stammdaten(session)
        session.add(_make_position(instrument_id, strategy_id, menge=Decimal("42"), status="offen"))
        session.commit()

        repository = SqlAlchemyPositionRepository(session)
        assert repository.aktuelle_menge(str(instrument_id)) == Decimal("42")


def test_aktuelle_menge_ignoriert_geschlossene_positionen() -> None:
    """@trace depot#AC10 — eine geschlossene Position (Menge 0, aber
    historisch mit einem Wert denkbar) zählt nicht zum aktuellen Bestand."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, strategy_id = _seed_stammdaten(session)
        session.add(
            _make_position(instrument_id, strategy_id, menge=Decimal("0"), status="geschlossen")
        )
        session.commit()

        repository = SqlAlchemyPositionRepository(session)
        assert repository.aktuelle_menge(str(instrument_id)) == Decimal("0")


def test_aktuelle_menge_summiert_mehrere_offene_positionen() -> None:
    """@trace depot#AC10 — mehrere offene Positionen desselben Titels
    (vom Modell nicht ausgeschlossen) werden summiert statt nur die erste
    zu liefern."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, strategy_id = _seed_stammdaten(session)
        session.add(_make_position(instrument_id, strategy_id, menge=Decimal("10"), status="offen"))
        session.add(_make_position(instrument_id, strategy_id, menge=Decimal("5"), status="offen"))
        session.commit()

        repository = SqlAlchemyPositionRepository(session)
        assert repository.aktuelle_menge(str(instrument_id)) == Decimal("15")
