"""Tests für die `rule_hypothesis`-Migration (Story S-058, Spec
`docs/specs/lernschleife.md` AC1/AC2, → BR-136).

Covers (lernschleife): AC1, AC2

Analog zur bestehenden Konvention (`tests/db/test_trial_registry_migration.py`):
prüft nur die strukturellen DB-Constraints (NOT-NULL-Pflichtfelder des
Mindest-Evidenz-Protokolls, CHECK-Constraints) gegen eine SQLite-In-Memory-
DB. Der reale `alembic upgrade head`-Lauf (inkl. FK-Nachrüstung auf
`trial_registry.hypothesis_id`) gegen eine lokale Postgres-Instanz ist Teil
des Coder-Self-Tests (siehe Handoff).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import RuleHypothesis


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _zeile(**overrides: object) -> RuleHypothesis:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "beschreibung": "Muster-Beschreibung",
        "marktlogik": "Marktlogische Begründung",
        "anzahl_faelle": 42,
        "zeitraum_von": datetime(2026, 1, 1, tzinfo=UTC),
        "zeitraum_bis": datetime(2026, 6, 30, tzinfo=UTC),
        "signalquelle": "news-sentiment-feed",
        "asset_class_id": 1,
        "params": {},
        "free_param_count": 0,
    }
    defaults.update(overrides)
    return RuleHypothesis(**defaults)  # type: ignore[arg-type]


def test_rule_hypothesis_traegt_alle_ac1_ac2_felder() -> None:
    """@trace lernschleife#AC1,AC2 — eine Zeile führt Beschreibung,
    Marktlogik und das volle Mindest-Evidenz-Protokoll."""
    engine = _engine()
    with Session(engine) as session:
        session.add(_zeile())
        session.commit()

        eintrag = session.query(RuleHypothesis).one()
        assert eintrag.beschreibung == "Muster-Beschreibung"
        assert eintrag.marktlogik == "Marktlogische Begründung"
        assert eintrag.anzahl_faelle == 42
        assert eintrag.signalquelle == "news-sentiment-feed"
        assert eintrag.asset_class_id == 1
        assert eintrag.created_at is not None


def test_rule_hypothesis_rejects_anzahl_faelle_null_oder_negativ() -> None:
    """@trace lernschleife#AC1 — CHECK `anzahl_faelle > 0` (BR-136): 0/-1
    Fälle sind keine Evidenz."""
    engine = _engine()
    with Session(engine) as session:
        session.add(_zeile(anzahl_faelle=0))
        with pytest.raises(IntegrityError):
            session.commit()

    with Session(engine) as session:
        session.add(_zeile(anzahl_faelle=-1))
        with pytest.raises(IntegrityError):
            session.commit()


def test_rule_hypothesis_rejects_zeitraum_bis_vor_zeitraum_von() -> None:
    """@trace lernschleife#AC1 — CHECK `zeitraum_bis >= zeitraum_von`
    (BR-136): ein inverser Zeitraum ist kein gültiges Evidenzprotokoll."""
    engine = _engine()
    with Session(engine) as session:
        session.add(
            _zeile(
                zeitraum_von=datetime(2026, 6, 1, tzinfo=UTC),
                zeitraum_bis=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize("feld", ["beschreibung", "marktlogik", "signalquelle", "asset_class_id"])
def test_rule_hypothesis_pflichtfelder_sind_not_null(feld: str) -> None:
    """@trace lernschleife#AC1,AC2 — Mindest-Evidenz-Protokoll- und
    Marktlogik-Pflichtfelder sind NOT NULL (BR-136, DB-Schicht)."""
    engine = _engine()
    with Session(engine) as session:
        session.add(_zeile(**{feld: None}))
        with pytest.raises(IntegrityError):
            session.commit()


def test_rule_hypothesis_created_at_erhaelt_default_ohne_angabe() -> None:
    """@trace lernschleife#AC1 — `created_at` erhält bei Nicht-Angabe einen
    Server-Default (Konvention `tested_at`/`booked_at`)."""
    engine = _engine()
    with Session(engine) as session:
        eintrag = _zeile()
        session.add(eintrag)
        session.commit()
        session.refresh(eintrag)

        assert eintrag.created_at is not None
