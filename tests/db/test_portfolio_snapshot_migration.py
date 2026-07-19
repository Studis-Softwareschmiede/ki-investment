"""Schema-/Constraint-Tests für `portfolio_snapshot` (Story S-081,
`docs/specs/frontend-cockpit.md` AC32; Migration `1f4a9c6e0b2d`; → BR-142).

Covers (frontend-cockpit): AC32

Prüft die Constraints direkt gegen SQLAlchemys `Base.metadata` (SQLite
in-memory — `CHECK`/`UNIQUE` werden identisch zu Postgres erzwungen,
anders als `FOREIGN KEY`, siehe `tests/db/test_hybrid_entscheid_migration
.py`-Vorbild): `mode`-CHECK, `UNIQUE (mode, snapshot_datum)` (→ BR-142,
Job-Idempotenz-Grundlage)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import PortfolioSnapshot


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _werte(**overrides: object) -> dict[str, object]:
    basis: dict[str, object] = {
        "id": uuid.uuid4(),
        "snapshot_at": datetime(2026, 7, 1, 22, 0, tzinfo=UTC),
        "snapshot_datum": date(2026, 7, 1),
        "total_value_chf": Decimal("5000.00"),
        "cash_quote_pct": Decimal("9.500"),
        "mode": "simuliert",
    }
    basis.update(overrides)
    return basis


def test_mode_ausserhalb_echt_simuliert_wird_abgelehnt() -> None:
    """@trace frontend-cockpit#AC32 — `ck_portfolio_snapshot_mode`."""
    session = _session()

    with pytest.raises(IntegrityError):
        session.execute(insert(PortfolioSnapshot).values(**_werte(mode="papier")))
        session.commit()


def test_mode_echt_und_simuliert_werden_akzeptiert() -> None:
    session = _session()
    session.execute(
        insert(PortfolioSnapshot).values(
            **_werte(id=uuid.uuid4(), mode="echt", snapshot_datum=date(2026, 7, 1))
        )
    )
    session.execute(
        insert(PortfolioSnapshot).values(
            **_werte(id=uuid.uuid4(), mode="simuliert", snapshot_datum=date(2026, 7, 1))
        )
    )
    session.commit()

    assert session.query(PortfolioSnapshot).count() == 2


def test_zweiter_snapshot_desselben_tages_und_modus_verletzt_unique_constraint() -> None:
    """@trace frontend-cockpit#AC32 — → BR-142: `UNIQUE (mode,
    snapshot_datum)` ist die DB-seitige Idempotenz-Grundlage des
    periodischen Snapshot-Jobs (Insert-Then-Catch statt Read-then-Write)."""
    session = _session()
    session.execute(insert(PortfolioSnapshot).values(**_werte(id=uuid.uuid4())))
    session.commit()

    with pytest.raises(IntegrityError):
        session.execute(
            insert(PortfolioSnapshot).values(
                **_werte(id=uuid.uuid4(), total_value_chf=Decimal("6000.00"))
            )
        )
        session.commit()


def test_gleicher_tag_anderer_modus_ist_erlaubt() -> None:
    """@trace frontend-cockpit#AC32 — → BR-130: `echt`/`simuliert` sind
    getrennte Aggregate, der UNIQUE-Constraint trennt sie mit."""
    session = _session()
    session.execute(insert(PortfolioSnapshot).values(**_werte(id=uuid.uuid4(), mode="echt")))
    session.execute(insert(PortfolioSnapshot).values(**_werte(id=uuid.uuid4(), mode="simuliert")))
    session.commit()

    assert session.query(PortfolioSnapshot).count() == 2


def test_gleicher_modus_anderer_tag_ist_erlaubt() -> None:
    session = _session()
    session.execute(insert(PortfolioSnapshot).values(**_werte(id=uuid.uuid4())))
    session.execute(
        insert(PortfolioSnapshot).values(**_werte(id=uuid.uuid4(), snapshot_datum=date(2026, 7, 2)))
    )
    session.commit()

    assert session.query(PortfolioSnapshot).count() == 2
