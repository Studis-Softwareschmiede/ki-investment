"""Tests für die `transaction`-Migration (Story S-035, append-only
Transaktionshistorie & TCA).

Covers (depot): AC4, AC7

Analog zur bestehenden Konvention (`tests/db/test_position_migration.py`,
`tests/db/test_depot_fill_dedup_migration.py`): prüft nur die
strukturellen DB-Constraints (CHECK `typ`/`mode`/`waehrung`, `position_id`
NULLable, Default-Zeitstempel) gegen eine SQLite-In-Memory-DB. Der
Postgres-spezifische `BEFORE UPDATE OR DELETE`-Trigger (BR-115,
App-unabhängige DB-Durchsetzung des Append-only-Gebots) ist unter SQLite
nicht abbildbar (die Migration legt ihn bewusst nur unter `dialect.name ==
"postgresql"` an) — der reale `alembic upgrade head`-Lauf inkl. Trigger
gegen eine lokale Compose-Postgres-Instanz (inkl. `alembic check` ohne
Model-Drift) ist Teil des Coder-Self-Tests (siehe Handoff). Die
funktionalen Schreib-/Lese-Tests (`schreibe_transaktion`/
`historie_je_titel`) liegen in
`tests/adapters/repositories/test_position_repository.py`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import AssetClass, Instrument, Transaction


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


def _valid_transaction(instrument_id: uuid.UUID, **overrides: object) -> Transaction:
    kwargs = {
        "id": uuid.uuid4(),
        "position_id": None,
        "instrument_id": instrument_id,
        "typ": "buy",
        "menge": Decimal("10"),
        "preis": Decimal("100.50"),
        "kosten_chf": Decimal("10"),
        "waehrung": "CHF",
        "arrival_price": Decimal("100"),
        "slippage_abs": Decimal("0.50"),
        "mode": "simuliert",
        "booked_at": datetime(2026, 7, 12, 10, 0, tzinfo=UTC),
    }
    kwargs.update(overrides)
    return Transaction(**kwargs)


def test_transaction_traegt_alle_ac4_und_ac7_felder() -> None:
    """@trace depot#AC4,AC7 — ein Eintrag führt Titel, Richtung (`typ`),
    Menge, Fill-Preis, Kosten, Zeitstempel, Währung (AC4) sowie
    Arrival-Price + Slippage (AC7)."""
    engine = _engine()
    with Session(engine) as session:
        instrument_id = _seed_instrument(session)
        session.add(_valid_transaction(instrument_id))
        session.commit()

        eintrag = session.query(Transaction).one()
        assert eintrag.instrument_id == instrument_id
        assert eintrag.typ == "buy"
        assert eintrag.menge == Decimal("10")
        assert eintrag.preis == Decimal("100.50")
        assert eintrag.kosten_chf == Decimal("10")
        assert eintrag.waehrung == "CHF"
        assert eintrag.arrival_price == Decimal("100")
        assert eintrag.slippage_abs == Decimal("0.50")
        # SQLite (Struktur-Test, In-Memory) rundet `DateTime(timezone=True)`
        # beim Roundtrip auf naive Werte ab (bekannte SQLAlchemy/SQLite-
        # Einschränkung) — Vergleich daher gegen den entkernten Wert.
        assert eintrag.booked_at == datetime(2026, 7, 12, 10, 0)


def test_transaction_position_id_ist_nullable() -> None:
    """@trace depot#AC4 — ein Verkauf-Fill, der mehrere Lots verbraucht
    (FIFO, A2), ist keinem einzelnen Lot eindeutig zuordenbar;
    `position_id` muss daher `NULL` sein dürfen."""
    engine = _engine()
    with Session(engine) as session:
        instrument_id = _seed_instrument(session)
        session.add(_valid_transaction(instrument_id, position_id=None))
        session.commit()

        eintrag = session.query(Transaction).one()
        assert eintrag.position_id is None


def test_transaction_rejects_invalid_typ() -> None:
    """@trace depot#AC4 — nur die 5 definierten Typen sind gültig
    (CHECK-Constraint)."""
    engine = _engine()
    with Session(engine) as session:
        instrument_id = _seed_instrument(session)
        session.add(_valid_transaction(instrument_id, typ="ungueltig"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_transaction_rejects_invalid_mode() -> None:
    """@trace depot#AC4 — `mode` nur `echt`/`simuliert` (→ BR-130)."""
    engine = _engine()
    with Session(engine) as session:
        instrument_id = _seed_instrument(session)
        session.add(_valid_transaction(instrument_id, mode="ungueltig"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_transaction_rejects_waehrung_not_3_chars() -> None:
    """@trace depot#AC4 — `waehrung` muss ein 3-stelliger ISO-Code sein
    (AC4 "Währung")."""
    engine = _engine()
    with Session(engine) as session:
        instrument_id = _seed_instrument(session)
        session.add(_valid_transaction(instrument_id, waehrung="CH"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_transaction_booked_at_erhaelt_default_ohne_angabe() -> None:
    """@trace depot#AC4 — `booked_at` erhält bei Nicht-Angabe (Attribut gar
    nicht gesetzt) einen Server-Default (Konvention `verbucht_at`/
    `opened_at`); im normalen Schreibpfad (`schreibe_transaktion`) wird
    stattdessen immer `fill.zeitstempel` explizit gesetzt (siehe
    `tests/adapters/repositories/test_position_repository.py`)."""
    engine = _engine()
    with Session(engine) as session:
        instrument_id = _seed_instrument(session)
        eintrag = Transaction(
            id=uuid.uuid4(),
            instrument_id=instrument_id,
            typ="buy",
            menge=Decimal("10"),
            preis=Decimal("100"),
            kosten_chf=Decimal("10"),
            waehrung="CHF",
            arrival_price=Decimal("100"),
            slippage_abs=Decimal("0"),
            mode="simuliert",
        )
        session.add(eintrag)
        session.commit()
        session.refresh(eintrag)

        assert eintrag.booked_at is not None
