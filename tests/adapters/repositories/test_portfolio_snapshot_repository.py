"""Tests für `SqlAlchemyPortfolioSnapshotRepository` (Story S-081,
`docs/specs/frontend-cockpit.md` AC32).

Covers (frontend-cockpit): AC32

Prüft `app.adapters.repositories.portfolio_snapshot_repository
.SqlAlchemyPortfolioSnapshotRepository` gegen eine SQLite-In-Memory-DB:
Mode-Isolation (→ BR-130), Zeitraum-Filter (`von`/`bis`), aufsteigende
Sortierung, leere Liste ohne Historie (E2-Muster) sowie das Schreiben
selbst inkl. Idempotenz (→ BR-142, Insert-Then-Catch statt
Read-then-Write-Dedupe, `.claude/lessons/coder.md`)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.adapters.repositories.portfolio_snapshot_repository import (
    SqlAlchemyPortfolioSnapshotRepository,
)
from app.db.base import Base


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_schreibe_snapshot_liefert_true_bei_erstem_lauf() -> None:
    session = _session()
    repository = SqlAlchemyPortfolioSnapshotRepository(session)

    geschrieben = repository.schreibe_snapshot(
        mode="simuliert",
        zeitpunkt=datetime(2026, 7, 1, 22, 0, tzinfo=UTC),
        portfolio_wert=Decimal("5000.00"),
        cash_quote=Decimal("9.500"),
    )

    assert geschrieben is True
    assert len(repository.verlauf(mode="simuliert")) == 1


def test_schreibe_snapshot_ist_idempotent_je_tag_und_modus() -> None:
    """@trace frontend-cockpit#AC32 — → BR-142: ein zweiter Lauf am selben
    Kalendertag/Modus schreibt keine Duplikat-Zeile, liefert `False`."""
    session = _session()
    repository = SqlAlchemyPortfolioSnapshotRepository(session)
    repository.schreibe_snapshot(
        mode="simuliert",
        zeitpunkt=datetime(2026, 7, 1, 22, 0, tzinfo=UTC),
        portfolio_wert=Decimal("5000.00"),
        cash_quote=Decimal("9.500"),
    )

    geschrieben = repository.schreibe_snapshot(
        mode="simuliert",
        zeitpunkt=datetime(2026, 7, 1, 23, 30, tzinfo=UTC),
        portfolio_wert=Decimal("9999.00"),
        cash_quote=Decimal("1.000"),
    )

    assert geschrieben is False
    eintraege = repository.verlauf(mode="simuliert")
    assert len(eintraege) == 1
    assert eintraege[0].portfolio_wert == Decimal("5000.00")


def test_verlauf_ist_mode_isoliert() -> None:
    """@trace frontend-cockpit#AC32 — → BR-130."""
    session = _session()
    repository = SqlAlchemyPortfolioSnapshotRepository(session)
    repository.schreibe_snapshot(
        mode="simuliert",
        zeitpunkt=datetime(2026, 7, 1, 22, 0, tzinfo=UTC),
        portfolio_wert=Decimal("5000.00"),
        cash_quote=Decimal("9.500"),
    )
    repository.schreibe_snapshot(
        mode="echt",
        zeitpunkt=datetime(2026, 7, 1, 22, 0, tzinfo=UTC),
        portfolio_wert=Decimal("1000.00"),
        cash_quote=Decimal("5.000"),
    )

    assert len(repository.verlauf(mode="simuliert")) == 1
    assert len(repository.verlauf(mode="echt")) == 1


def test_verlauf_sortiert_aufsteigend_und_filtert_zeitraum() -> None:
    session = _session()
    repository = SqlAlchemyPortfolioSnapshotRepository(session)
    for tag, wert in ((1, "5000.00"), (2, "5100.00"), (3, "5050.00")):
        repository.schreibe_snapshot(
            mode="simuliert",
            zeitpunkt=datetime(2026, 7, tag, 22, 0, tzinfo=UTC),
            portfolio_wert=Decimal(wert),
            cash_quote=Decimal("9.500"),
        )

    voller_verlauf = repository.verlauf(mode="simuliert")
    assert [e.portfolio_wert for e in voller_verlauf] == [
        Decimal("5000.00"),
        Decimal("5100.00"),
        Decimal("5050.00"),
    ]

    gefiltert = repository.verlauf(
        mode="simuliert",
        von=datetime(2026, 7, 2, 0, 0, tzinfo=UTC),
        bis=datetime(2026, 7, 2, 23, 59, tzinfo=UTC),
    )
    assert [e.portfolio_wert for e in gefiltert] == [Decimal("5100.00")]


def test_verlauf_liefert_leere_liste_ohne_historie() -> None:
    """@trace frontend-cockpit#AC32 — Grundlage des definierten
    Empty-States (E2-Muster)."""
    session = _session()
    repository = SqlAlchemyPortfolioSnapshotRepository(session)

    assert repository.verlauf(mode="simuliert") == []
