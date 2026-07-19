"""Tests für `app.demo.entscheide.seed_entscheide` (Story S-080,
`docs/specs/frontend-cockpit.md` AC31).

Covers (frontend-cockpit): AC31

SQLite (in-memory) reicht aus — reiner SQLAlchemy-/App-Layer-Code (analog
`tests/demo/test_seed.py`). Belegt: **No-Op**, solange
`HYBRID_BESTAETIGUNG_AKTIV` nicht gesetzt ist (Default aus, AC31 "Bei
aktivem Flag kann der Demo-Seed ... füllen" impliziert: bei inaktivem
Flag füllt er NICHT); befüllt `hybrid_entscheid` deterministisch +
order-frei bei aktivem Flag; idempotent (zweiter Lauf dupliziert nicht);
`mode="simuliert"` (BR-141) für jede geseedete Zeile. Der generische
Order-Pfad-Import-Scan (`tests/demo/test_seed.py::test_demo_modul_
importiert_keinen_order_pfad`) deckt `app/demo/entscheide.py` bereits
automatisch mit ab (glob über `app/demo/**`)."""

from __future__ import annotations

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import Base
from app.db.models import HybridEntscheid
from app.demo.entscheide import seed_entscheide
from app.demo.instrumente import seed_instrumente


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_seed_entscheide_ist_no_op_wenn_feature_flag_aus(monkeypatch) -> None:
    """@trace frontend-cockpit#AC31 — Default aus: `seed_entscheide` legt
    KEINE Zeile an, solange `HYBRID_BESTAETIGUNG_AKTIV` nicht gesetzt ist."""
    monkeypatch.delenv("HYBRID_BESTAETIGUNG_AKTIV", raising=False)
    get_settings.cache_clear()
    session = _session()
    seed_instrumente(session)

    seed_entscheide(session)

    anzahl = session.execute(select(func.count()).select_from(HybridEntscheid)).scalar_one()
    assert anzahl == 0
    get_settings.cache_clear()


def test_seed_entscheide_befuellt_deterministisch_bei_aktivem_flag(monkeypatch) -> None:
    """@trace frontend-cockpit#AC31 — bei aktivem Flag füllt der Seed
    deterministische, order-freie offene Entscheide (`mode="simuliert"`)."""
    monkeypatch.setenv("HYBRID_BESTAETIGUNG_AKTIV", "true")
    get_settings.cache_clear()
    session = _session()
    seed_instrumente(session)

    seed_entscheide(session)

    zeilen = session.execute(select(HybridEntscheid)).scalars().all()
    assert len(zeilen) == 2
    assert all(zeile.status == "offen" for zeile in zeilen)
    assert all(zeile.mode == "simuliert" for zeile in zeilen)
    get_settings.cache_clear()


def test_seed_entscheide_ist_idempotent(monkeypatch) -> None:
    """@trace frontend-cockpit#AC31 — ein wiederholter Aufruf dupliziert
    keine Zeilen."""
    monkeypatch.setenv("HYBRID_BESTAETIGUNG_AKTIV", "true")
    get_settings.cache_clear()
    session = _session()
    seed_instrumente(session)

    seed_entscheide(session)
    seed_entscheide(session)

    anzahl = session.execute(select(func.count()).select_from(HybridEntscheid)).scalar_one()
    assert anzahl == 2
    get_settings.cache_clear()
