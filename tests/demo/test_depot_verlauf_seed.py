"""Tests für `app.demo.depot_verlauf.seed_depot_verlauf` (Story S-081,
`docs/specs/frontend-cockpit.md` AC22/AC32/AC33).

Covers (frontend-cockpit): AC22, AC32, AC33

SQLite (in-memory) reicht aus — reiner SQLAlchemy-/App-Layer-Code (analog
`tests/demo/test_entscheide_seed.py`). Belegt: 60 Tage deterministische
Historie, `mode="simuliert"` (AC22), Aufwärtstrend (Endwert > Anfangswert),
idempotent (zweiter Lauf dupliziert nicht), keine Order-/Sizing-/Risiko-
/Execution-Aufrufe (generischer Scan
`tests/demo/test_seed.py::test_demo_modul_importiert_keinen_order_pfad`
deckt dieses Modul bereits automatisch mit ab, glob über `app/demo/**`)."""

from __future__ import annotations

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import PortfolioSnapshot
from app.demo.depot_verlauf import seed_depot_verlauf


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_seed_depot_verlauf_befuellt_60_tage_mode_simuliert() -> None:
    """@trace frontend-cockpit#AC22,AC32,AC33 — 60 Tage, ausschliesslich
    `mode="simuliert"`."""
    session = _session()

    seed_depot_verlauf(session)

    zeilen = session.execute(select(PortfolioSnapshot)).scalars().all()
    assert len(zeilen) == 60
    assert all(zeile.mode == "simuliert" for zeile in zeilen)


def test_seed_depot_verlauf_zeigt_aufwaertstrend() -> None:
    """@trace frontend-cockpit#AC33 — "leichte Auf-und-Ab-Bewegung mit
    Aufwärtstrend" (Task-Vorgabe): Endwert > Anfangswert."""
    session = _session()

    seed_depot_verlauf(session)

    zeilen = (
        session.execute(select(PortfolioSnapshot).order_by(PortfolioSnapshot.snapshot_at.asc()))
        .scalars()
        .all()
    )
    assert zeilen[-1].total_value_chf > zeilen[0].total_value_chf


def test_seed_depot_verlauf_ist_deterministisch() -> None:
    """@trace frontend-cockpit#AC33 — kein `random` ohne Seed: zwei
    unabhängige Läufe (verschiedene Sessions) liefern identische Werte."""
    session_a = _session()
    session_b = _session()

    seed_depot_verlauf(session_a)
    seed_depot_verlauf(session_b)

    werte_a = [
        z.total_value_chf
        for z in session_a.execute(
            select(PortfolioSnapshot).order_by(PortfolioSnapshot.snapshot_at.asc())
        )
        .scalars()
        .all()
    ]
    werte_b = [
        z.total_value_chf
        for z in session_b.execute(
            select(PortfolioSnapshot).order_by(PortfolioSnapshot.snapshot_at.asc())
        )
        .scalars()
        .all()
    ]
    assert werte_a == werte_b


def test_seed_depot_verlauf_ist_idempotent() -> None:
    """@trace frontend-cockpit#AC32 — → BR-142: ein wiederholter Aufruf
    dupliziert keine Zeilen (DB-UNIQUE (mode, snapshot_datum))."""
    session = _session()

    seed_depot_verlauf(session)
    seed_depot_verlauf(session)

    anzahl = session.execute(select(func.count()).select_from(PortfolioSnapshot)).scalar_one()
    assert anzahl == 60
