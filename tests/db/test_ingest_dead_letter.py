"""Tests für `app.db.ingest_dead_letter` (Story S-020).

Covers (dateneingang): AC10

`record_dead_letter()` ist die durable Ablage, in die
`app.scheduler.worker.Worker` nach erschöpften Exponential-Backoff-
Versuchen schreibt (AC10 "... wird das Arbeitselement in eine
Dead-Letter-Queue verschoben und protokolliert").
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.ingest_dead_letter import dead_letters_for_source, record_dead_letter
from app.db.models import DataSource


def _session_mit_quelle() -> tuple[Session, uuid.UUID]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    quelle_id = uuid.uuid4()
    session.add(
        DataSource(
            id=quelle_id,
            name="Testquelle",
            kategorie="makro_anleihen",
            frequenz_sekunden=3600,
            aktiv=True,
        )
    )
    session.commit()
    return session, quelle_id


def test_record_dead_letter_persists_a_row() -> None:
    """@trace dateneingang#AC10 — ein endgültig aufgegebenes Arbeitselement
    wird als abfragbare Zeile persistiert (Backlog-Monitoring,
    data-model.md §8)."""
    session, quelle_id = _session_mit_quelle()

    eintrag = record_dead_letter(
        session,
        data_source_id=quelle_id,
        fehler="Timeout nach 5 Versuchen",
        retry_count=5,
        source_event_id="evt-1",
        payload={"raw": "x"},
    )

    assert eintrag.id is not None
    assert eintrag.fehler == "Timeout nach 5 Versuchen"
    assert eintrag.retry_count == 5


def test_dead_letters_for_source_returns_newest_first() -> None:
    """@trace dateneingang#AC10 — DLQ-Backlog-Monitoring je Quelle
    (data-model.md §8-Index `(data_source_id, created_at)`)."""
    session, quelle_id = _session_mit_quelle()
    andere_quelle_id = uuid.uuid4()
    session.add(
        DataSource(
            id=andere_quelle_id,
            name="Andere Quelle",
            kategorie="makro_anleihen",
            frequenz_sekunden=3600,
            aktiv=True,
        )
    )
    session.commit()

    erster = record_dead_letter(
        session,
        data_source_id=quelle_id,
        fehler="a",
        retry_count=1,
        erstellt_am=datetime(2026, 1, 1, tzinfo=UTC),
    )
    zweiter = record_dead_letter(
        session,
        data_source_id=quelle_id,
        fehler="b",
        retry_count=2,
        erstellt_am=datetime(2026, 1, 2, tzinfo=UTC),
    )
    record_dead_letter(session, data_source_id=andere_quelle_id, fehler="c", retry_count=1)

    ergebnis = dead_letters_for_source(session, data_source_id=quelle_id)

    assert [eintrag.id for eintrag in ergebnis] == [zweiter.id, erster.id]
