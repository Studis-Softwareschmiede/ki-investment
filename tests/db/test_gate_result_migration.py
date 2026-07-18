"""Tests für die `gate_result`-Migration (Story S-062, Ampel + Metriken,
→ BR-119/BR-120).

Covers (lernschleife): AC10, AC11, AC12

Analog zur bestehenden Konvention (`tests/db/test_trial_registry_migration.py`,
`tests/db/test_rule_hypothesis_migration.py`): prüft nur die strukturellen
DB-Constraints (Pflichtfelder, Ampel-Wertebereich) gegen eine SQLite-
In-Memory-DB. Der reale `alembic upgrade head`-Lauf gegen eine lokale
Postgres-Instanz (inkl. der beiden CHECK-Constraints und der FK auf
`trial_registry.id`) ist Teil des Coder-Self-Tests (siehe Handoff)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import GateResult


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_gate_result_traegt_alle_ac10_ac11_ac12_felder() -> None:
    """@trace lernschleife#AC10 — eine Zeile führt Trial-Referenz, Stufe,
    Ampel, alle Metriken und eine Begründung."""
    engine = _engine()
    with Session(engine) as session:
        trial_id = uuid.uuid4()
        session.add(
            GateResult(
                id=uuid.uuid4(),
                trial_id=trial_id,
                stufe="B_paper",
                ampel="gruen",
                sample_size=150,
                wfe=None,
                dsr=None,
                psr=None,
                min_trl=None,
                begruendung="Test",
            )
        )
        session.commit()

        eintrag = session.query(GateResult).one()
        assert eintrag.trial_id == trial_id
        assert eintrag.stufe == "B_paper"
        assert eintrag.ampel == "gruen"
        assert eintrag.sample_size == 150


def test_gate_result_created_at_erhaelt_default_ohne_angabe() -> None:
    """@trace lernschleife#AC10 — `created_at` erhält bei Nicht-Angabe einen
    Server-Default (Konvention `tested_at`/`created_at`)."""
    engine = _engine()
    with Session(engine) as session:
        eintrag = GateResult(
            id=uuid.uuid4(),
            trial_id=uuid.uuid4(),
            stufe="A_historisch",
            ampel="gelb",
        )
        session.add(eintrag)
        session.commit()
        session.refresh(eintrag)

        assert eintrag.created_at is not None


def test_gate_result_metriken_sind_optional() -> None:
    """@trace lernschleife#AC10 — `sample_size`/`wfe`/`dsr`/`psr`/`min_trl`/
    `begruendung` sind alle NULL-fähig (data-model.md §6 nennt für diese
    Spalten kein NOT NULL; nur `trial_id`/`stufe`/`ampel` sind Pflicht)."""
    engine = _engine()
    with Session(engine) as session:
        eintrag = GateResult(
            id=uuid.uuid4(),
            trial_id=uuid.uuid4(),
            stufe="A_historisch",
            ampel="rot",
        )
        session.add(eintrag)
        session.commit()
        session.refresh(eintrag)

        assert eintrag.sample_size is None
        assert eintrag.wfe is None
        assert eintrag.dsr is None
        assert eintrag.psr is None
        assert eintrag.min_trl is None
        assert eintrag.begruendung is None


def test_gate_result_rejects_unbekannten_ampel_wert() -> None:
    """@trace lernschleife#AC10 — `ck_gate_result_ampel` erzwingt
    `ampel ∈ {gruen, gelb, rot}` DB-seitig (BR-119, zweite Sicherungsebene
    neben der Pydantic-`Ampel`-Literal-Domäne)."""
    engine = _engine()
    with Session(engine) as session:
        session.add(
            GateResult(
                id=uuid.uuid4(),
                trial_id=uuid.uuid4(),
                stufe="A_historisch",
                ampel="orange",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_gate_result_rejects_unbekannten_stufe_wert() -> None:
    """@trace lernschleife#AC10 — `ck_gate_result_stufe` erzwingt
    `stufe ∈ {A_historisch, B_paper}` DB-seitig."""
    engine = _engine()
    with Session(engine) as session:
        session.add(
            GateResult(
                id=uuid.uuid4(),
                trial_id=uuid.uuid4(),
                stufe="C_unbekannt",
                ampel="rot",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
