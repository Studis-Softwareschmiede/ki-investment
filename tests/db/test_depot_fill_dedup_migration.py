"""Tests für die `depot_fill_dedup`-Migration (S-016 DBA-Zweit-Review,
ADR-011/P8, data-model.md §4).

Covers (depot): AC2, AC3

`depot_fill_dedup` ist der Idempotenz-Ledger, gegen den
`app.adapters.repositories.position_repository.SqlAlchemyPositionRepository
.markiere_fill_verbucht` prüft/schreibt (siehe
`tests/adapters/repositories/test_position_repository.py` für die
funktionalen Dedup-Tests). Diese Datei prüft — analog zur bestehenden
Konvention aus `tests/db/test_position_migration.py` — nur die
strukturellen DB-Constraints (PK-Eindeutigkeit, CHECK `richtung`) gegen
eine SQLite-In-Memory-DB; der reale `alembic upgrade head`-Lauf gegen eine
lokale Compose-Postgres-Instanz (inkl. `alembic check` ohne Model-Drift)
ist Teil des Coder-Self-Tests (siehe Handoff).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import AssetClass, DepotFillDedup, Instrument


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _seed_instrument(session: Session) -> uuid.UUID:
    session.add(AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True, retail_driven=True))
    instrument = Instrument(
        id=uuid.uuid4(), symbol="ACME", name="Acme Corp", asset_class_id=1, currency="CHF"
    )
    session.add(instrument)
    session.commit()
    return instrument.id


def test_depot_fill_dedup_client_order_id_ist_eindeutig() -> None:
    """@trace depot#AC2 — `client_order_id` ist Primärschlüssel (ADR-011):
    ein zweiter Insert mit demselben Wert verletzt den PK-Constraint."""
    engine = _engine()
    with Session(engine) as session:
        instrument_id = _seed_instrument(session)
        session.add(
            DepotFillDedup(client_order_id="order-1", instrument_id=instrument_id, richtung="kauf")
        )
        session.commit()

        session.add(
            DepotFillDedup(
                client_order_id="order-1", instrument_id=instrument_id, richtung="verkauf"
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_depot_fill_dedup_rejects_invalid_richtung() -> None:
    """@trace depot#AC3 — nur `kauf`/`verkauf` sind gültige Werte für
    `richtung` (CHECK-Constraint)."""
    engine = _engine()
    with Session(engine) as session:
        instrument_id = _seed_instrument(session)
        session.add(
            DepotFillDedup(
                client_order_id="order-2", instrument_id=instrument_id, richtung="ungueltig"
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_depot_fill_dedup_verbucht_at_wird_automatisch_gesetzt() -> None:
    """@trace depot#AC2 — `verbucht_at` erhält bei Nicht-Angabe einen
    Server-Default (Audit-Zeitstempel, Konvention `created_at`/
    `opened_at`)."""
    engine = _engine()
    with Session(engine) as session:
        instrument_id = _seed_instrument(session)
        eintrag = DepotFillDedup(
            client_order_id="order-3", instrument_id=instrument_id, richtung="kauf"
        )
        session.add(eintrag)
        session.commit()
        session.refresh(eintrag)

        assert eintrag.verbucht_at is not None
