"""Tests für `SqlAlchemyHybridEntscheidungRepository` (Story S-080,
`docs/specs/frontend-cockpit.md` AC29/AC30).

Covers (frontend-cockpit): AC29, AC30

SQLite (in-memory) reicht aus — reiner SQLAlchemy-Select/Join-Code, keine
Postgres-spezifischen Konstrukte im Pfad (analog `tests/adapters/
repositories/test_position_repository.py`). Belegt: nur `status="offen"`
UND `mode="simuliert"` werden geliefert (BR-141/AC30-MVP-Live-Sperre —
`bestaetigt`/`abgelehnt` fallen raus), sortiert nach `frist` aufsteigend,
`Instrument`-Join löst `titel`/`name` auf (S-066/S-071-Lehre)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.adapters.repositories.hybrid_entscheid_repository import (
    SqlAlchemyHybridEntscheidungRepository,
)
from app.db.base import Base
from app.db.models import HybridEntscheid, Instrument


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _instrument(session: Session, *, id_, symbol: str, name: str) -> None:
    session.add(
        Instrument(
            id=id_,
            symbol=symbol,
            name=name,
            asset_class_id=1,
            currency="CHF",
        )
    )


def test_offene_entscheide_liefert_nur_offen_und_simuliert_sortiert_nach_frist():
    """@trace frontend-cockpit#AC29,AC30 — `bestaetigt`/`abgelehnt`
    Zeilen fallen raus (nur `status="offen"`), Sortierung aufsteigend nach
    `frist`."""
    session = _session()
    # SQLite-Falle: eine rein numerische Hex-Zeichenkette bekommt unter
    # SQLite NUMERIC-Spalten-Affinität zugewiesen und wird beim Lesen
    # stillschweigend zu einem Float konvertiert — deshalb `uuid.uuid4()`
    # statt lesbarer Literale (siehe `tests/api/test_control_route.py`).
    titel_1 = uuid.uuid4()
    titel_2 = uuid.uuid4()
    entscheid_1 = uuid.uuid4()
    entscheid_2 = uuid.uuid4()
    entscheid_3 = uuid.uuid4()
    _instrument(session, id_=titel_1, symbol="ROG", name="Roche Holding AG")
    _instrument(session, id_=titel_2, symbol="NOVN", name="Novartis AG")
    session.add_all(
        [
            HybridEntscheid(
                id=entscheid_1,
                instrument_id=titel_1,
                richtung="kauf",
                groesse=Decimal("5"),
                vorgeschlagene_order="Market-Buy 5 Stk. Roche Holding AG",
                frist=datetime(2026, 7, 22, 16, 0, tzinfo=UTC),
                begruendung="Begründung ROG",
                status="offen",
                mode="simuliert",
            ),
            HybridEntscheid(
                id=entscheid_2,
                instrument_id=titel_2,
                richtung="verkauf",
                groesse=Decimal("4"),
                vorgeschlagene_order="Market-Sell 4 Stk. Novartis AG",
                frist=datetime(2026, 7, 20, 16, 0, tzinfo=UTC),
                begruendung="Begründung NOVN",
                status="offen",
                mode="simuliert",
            ),
            HybridEntscheid(
                id=entscheid_3,
                instrument_id=titel_1,
                richtung="kauf",
                groesse=Decimal("2"),
                vorgeschlagene_order="bereits entschieden",
                frist=datetime(2026, 7, 21, 16, 0, tzinfo=UTC),
                begruendung="bereits entschieden",
                status="bestaetigt",
                mode="simuliert",
            ),
        ]
    )
    session.commit()

    repository = SqlAlchemyHybridEntscheidungRepository(session)
    ergebnis = repository.offene_entscheide()

    assert [e.entscheid_id for e in ergebnis] == [str(entscheid_2), str(entscheid_1)]
    assert ergebnis[0].titel == "NOVN"
    assert ergebnis[0].name == "Novartis AG"
    assert ergebnis[0].richtung == "verkauf"
    assert ergebnis[1].titel == "ROG"


def test_offene_entscheide_leer_ohne_zeilen():
    """@trace frontend-cockpit#AC29 — keine Zeile → leere Liste, kein
    Fehler."""
    session = _session()

    repository = SqlAlchemyHybridEntscheidungRepository(session)

    assert repository.offene_entscheide() == []
