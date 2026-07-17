"""Tests für die `trial_registry`-Migration (Story S-059, append-only
Trial-Registry, → BR-118).

Covers (lernschleife): AC3

Analog zur bestehenden Konvention (`tests/db/test_transaction_migration.py`,
`tests/db/test_ingest_dead_letter_migration.py`): prüft nur die
strukturellen DB-Constraints (`UNIQUE (hypothesis_id, variant_hash)`,
`archived`-Default, Zeitstempel-Default) gegen eine SQLite-In-Memory-DB.
Der Postgres-spezifische `BEFORE DELETE`-Trigger (BR-118, DB-seitige
Durchsetzung von „nie gelöscht") ist unter SQLite nicht abbildbar (die
Migration legt ihn bewusst nur unter `dialect.name == "postgresql"` an) —
der reale `alembic upgrade head`-Lauf inkl. Trigger gegen eine lokale
Postgres-Instanz ist Teil des Coder-Self-Tests (siehe Handoff).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import TrialRegistry


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_trial_registry_traegt_alle_ac3_felder() -> None:
    """@trace lernschleife#AC3 — ein Eintrag führt Hypothese, Varianten-
    Identität, Parameter, Archiv-Flag und Zeitstempel."""
    engine = _engine()
    with Session(engine) as session:
        hypothesis_id = uuid.uuid4()
        session.add(
            TrialRegistry(
                id=uuid.uuid4(),
                hypothesis_id=hypothesis_id,
                variant_hash="hash-1",
                params={"schwelle": 0.5},
            )
        )
        session.commit()

        eintrag = session.query(TrialRegistry).one()
        assert eintrag.hypothesis_id == hypothesis_id
        assert eintrag.variant_hash == "hash-1"
        assert eintrag.params == {"schwelle": 0.5}
        assert eintrag.archived is False
        assert eintrag.tested_at is not None


def test_trial_registry_rejects_duplicate_hypothesis_variant() -> None:
    """@trace lernschleife#AC3 — `UNIQUE (hypothesis_id, variant_hash)`
    (data-model.md §6/§8) verhindert, dass dieselbe Variante zweimal als
    eigenständige Zeile registriert wird."""
    engine = _engine()
    hypothesis_id = uuid.uuid4()
    with Session(engine) as session:
        session.add(
            TrialRegistry(
                id=uuid.uuid4(),
                hypothesis_id=hypothesis_id,
                variant_hash="hash-1",
                params={},
            )
        )
        session.commit()

    with Session(engine) as session:
        session.add(
            TrialRegistry(
                id=uuid.uuid4(),
                hypothesis_id=hypothesis_id,
                variant_hash="hash-1",
                params={},
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_trial_registry_archived_default_ist_false() -> None:
    """@trace lernschleife#AC3 — eine frisch registrierte Variante ist
    nicht archiviert (Default `false`, Server-Default für Postgres-Inserts
    ausserhalb des ORM-Pfads)."""
    engine = _engine()
    with Session(engine) as session:
        eintrag = TrialRegistry(
            id=uuid.uuid4(),
            hypothesis_id=uuid.uuid4(),
            variant_hash="hash-1",
            params={},
        )
        session.add(eintrag)
        session.commit()
        session.refresh(eintrag)

        assert eintrag.archived is False


def test_trial_registry_tested_at_erhaelt_default_ohne_angabe() -> None:
    """@trace lernschleife#AC3 — `tested_at` erhält bei Nicht-Angabe einen
    Server-Default (Konvention `booked_at`/`created_at`)."""
    engine = _engine()
    with Session(engine) as session:
        eintrag = TrialRegistry(
            id=uuid.uuid4(),
            hypothesis_id=uuid.uuid4(),
            variant_hash="hash-1",
            params={},
        )
        session.add(eintrag)
        session.commit()
        session.refresh(eintrag)

        assert eintrag.tested_at is not None
