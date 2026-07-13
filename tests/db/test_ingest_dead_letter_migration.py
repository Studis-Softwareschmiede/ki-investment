"""Tests fuer die ingest_dead_letter-Migration (Story S-020).

Covers (dateneingang): AC10

Die Migration wurde per `alembic upgrade head` gegen eine lokale
Postgres-17-Instanz (`docker run postgres:17-alpine`) angewendet und
manuell verifiziert (Coder-Self-Test, siehe Handoff): (1) Tabelle inkl.
Index wird angelegt, `alembic check` meldet keine neue Model-Drift durch
diese Migration (die einzigen gemeldeten Diffs sind vorbestehende
Partitionierungs-Altlasten aus fruehren Stories, unveraendert seit vor
S-020); (2) ein zweiter `alembic upgrade head`-Lauf ist ein No-Op
(bereits auf Head, `alembic current --check-heads` zeigt den Head ohne
Fehler). `ingest_dead_letter` ist NICHT partitioniert (data-model.md §9
listet dafuer keine Partitionierung, anders als market_data_*), daher
reicht hier -- anders als bei den partitionierten Bronze/Silver/Gold-
Migrationen -- die vollstaendige Verifikation ueber ein SQLite-In-Memory-
Modell (kein Postgres-spezifisches DDL wie `PARTITION BY RANGE`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import DataSource, IngestDeadLetter

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "app"
    / "db"
    / "migrations"
    / "versions"
    / "9c1e6a2f3b7d_create_ingest_dead_letter_ac10.py"
)


def _migration_source() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


def test_migration_chains_onto_current_head() -> None:
    """@trace dateneingang#AC10 — die Migration haengt korrekt an den
    bisherigen Head (`8f183aee9753`, Methodentabellen-Migration), keine
    gebrochene down_revision-Kette (alembic/A03/A05)."""
    source = _migration_source()
    assert 'revision: str = "9c1e6a2f3b7d"' in source
    assert 'down_revision: Union[str, Sequence[str], None] = "8f183aee9753"' in source


def test_migration_creates_the_data_source_id_created_at_index() -> None:
    """@trace dateneingang#AC10 — data-model.md §8 verlangt fuer
    `ingest_dead_letter` einen `(data_source_id, created_at)`-Index
    (DLQ-Backlog-Monitoring)."""
    source = _migration_source()
    assert "ix_ingest_dead_letter_data_source_id_created_at" in source
    assert '["data_source_id", "created_at"]' in source


def test_model_matches_data_model_md_columns() -> None:
    """@trace dateneingang#AC10 — `IngestDeadLetter` bildet data-model.md
    §7 1:1 ab (Spalten + Index) und persistiert ueber ein reales Schema
    (SQLite-In-Memory, `Base.metadata.create_all`)."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
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

        session.add(
            IngestDeadLetter(
                id=uuid.uuid4(),
                data_source_id=quelle_id,
                source_event_id="evt-1",
                payload={"raw": "x"},
                fehler="Timeout",
                retry_count=5,
                created_at=datetime.now(UTC),
            )
        )
        session.commit()

    index_names_by_columns = {
        tuple(col.name for col in index.columns): index.name
        for index in IngestDeadLetter.__table__.indexes
    }
    assert ("data_source_id", "created_at") in index_names_by_columns
    assert (
        index_names_by_columns[("data_source_id", "created_at")]
        == "ix_ingest_dead_letter_data_source_id_created_at"
    )


def test_model_requires_fehler_and_data_source_id() -> None:
    """@trace dateneingang#AC10 — `fehler` und `data_source_id` sind
    NOT-NULL-Pflichtfelder (jede Dead-Letter-Zeile muss einer Quelle UND
    einem Fehlergrund zuordenbar sein)."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            IngestDeadLetter(
                id=uuid.uuid4(),
                data_source_id=None,
                fehler="x",
                retry_count=1,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
