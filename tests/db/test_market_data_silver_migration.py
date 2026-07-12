"""Tests fuer die market_data_silver-Migration (Story S-024).

Covers (datenqualitaet): AC3, AC6

- AC3 (Normalisierung, reproduzierbar aus Bronze): die Migration ist
  Postgres-spezifisches DDL (`PARTITION BY RANGE`) und daher nicht unter
  SQLite ausfuehrbar -- hier per Quelltext-Pruefung abgesichert
  (Regressionsschutz), die Verhaltenslogik selbst ist in
  `tests/db/test_silver.py` (`app.db.silver`) vollstaendig abgedeckt. Das
  ORM-Modell (`app.db.models.MarketDataSilver`) bildet die zusammengesetzte
  FK auf `market_data_bronze(id, ingested_at)` strukturell ab (SQLite mit
  aktivierten Foreign-Key-Pragmas).
- AC6 (Corporate-Actions-Adjustierung): die `adjustierungs_info`-Spalte
  (JSONB) ist Pflichtbestandteil des physischen Schemas -- hier per
  Quelltext-Pruefung der Migrationsdatei abgesichert.
- AC3 (Iteration 2, Reviewer-Befund, Critical): `test_migration_declares_
  data_source_id_and_unique_bronze_version_constraint` belegt, dass
  `data_source_id` (denormalisiert) + `uq_market_data_silver_bronze_version`
  Teil des physischen Schemas sind (Cross-Data-Source-Rebuild-Fix +
  Nebenlaeufigkeits-Haertung, siehe `app/db/silver.py`/
  `tests/db/test_silver.py`).

Die Migration selbst wurde per `alembic upgrade head` gegen eine lokale
Compose-Postgres-Instanz angewendet und manuell verifiziert (Coder-Self-Test,
siehe Handoff): (1) Tabelle inkl. Default-Partition wird angelegt; (2) ein
Insert mit gueltigem `bronze_id`/`bronze_ingested_at`-Paar gelingt; (3) ein
Insert mit einem `bronze_id`/`bronze_ingested_at`-Paar, das keiner
bestehenden Bronze-Zeile entspricht, scheitert an der zusammengesetzten FK;
(4) ein zweiter `alembic upgrade head`-Lauf ist ein No-Op (bereits auf Head).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import AssetClass, DataSource, MarketDataBronze, MarketDataSilver

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "app"
    / "db"
    / "migrations"
    / "versions"
    / "cf167d0a63f5_create_market_data_silver_silver_layer.py"
)


def _migration_source() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


def test_migration_chains_onto_current_head() -> None:
    """@trace datenqualitaet#AC3 — die Migration haengt korrekt an den
    bisherigen Head (`cfdd83ba9a2c`, Bronze-Migration), keine gebrochene
    down_revision-Kette (alembic/A03/A05)."""
    source = _migration_source()
    assert 'revision: str = "cf167d0a63f5"' in source
    assert 'down_revision: Union[str, Sequence[str], None] = "cfdd83ba9a2c"' in source


def test_migration_declares_range_partitioning_and_default_partition() -> None:
    """@trace datenqualitaet#AC3 — `observed_at` ist Partitionsschluessel
    (data-model.md §9), eine Default-Partition faengt jeden Wert
    strukturell auf (analog Bronze)."""
    source = _migration_source()
    assert "PARTITION BY RANGE (observed_at)" in source
    assert "PARTITION OF market_data_silver DEFAULT" in source


def test_migration_declares_foreign_key_to_bronze_composite_pk() -> None:
    """@trace datenqualitaet#AC3 — `abgeleitet_aus: bronze_version`
    (Spec-Vertrag) wird als zusammengesetzte FK auf `market_data_bronze(id,
    ingested_at)` erzwungen (Partitionsschluessel-Pflicht bei FK auf
    partitionierte Tabelle)."""
    source = _migration_source()
    assert "FOREIGN KEY (bronze_id, bronze_ingested_at)" in source
    assert "REFERENCES market_data_bronze (id, ingested_at)" in source


def test_migration_declares_adjustierungs_info_column() -> None:
    """@trace datenqualitaet#AC6 — die Spalte fuer die
    Corporate-Actions-Adjustierungs-Metadaten ist Teil des physischen
    Schemas."""
    source = _migration_source()
    assert "adjustierungs_info JSONB" in source
    assert "einheit TEXT NOT NULL" in source


def test_migration_declares_no_immutability_trigger() -> None:
    """@trace datenqualitaet#AC6 — anders als Bronze (BR-121) ist Silver
    NICHT append-only (Edge-Case "Corporate Action rueckwirkend gemeldet"
    verlangt eine neu abgeleitete Reihe) -- kein BEFORE-UPDATE/DELETE-
    Trigger vorhanden."""
    source = _migration_source()
    assert "BEFORE UPDATE OR DELETE" not in source


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        db_session.add(
            AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True, retail_driven=True)
        )
        db_session.add(
            DataSource(
                id=uuid.uuid4(),
                name="IBKR - Kursdaten",
                kategorie="equity_fundamentals",
                qualitaet="hoch",
                frequenz_sekunden=60,
                aktiv=True,
            )
        )
        db_session.commit()
        yield db_session


def test_model_requires_normalisierter_wert_and_einheit(session: Session) -> None:
    """@trace datenqualitaet#AC3 — `normalisierter_wert`/`einheit` sind
    Pflichtfelder des Silver-Vertrags; ein Datensatz ohne `einheit` wird
    zurueckgewiesen."""
    source_id = session.query(DataSource).one().id
    bronze_zeile = MarketDataBronze(
        data_source_id=source_id,
        source_event_id="ibkr:AAPL:2026-01-01",
        symbol="AAPL",
        payload={"preis": "400"},
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        asset_class_tag=1,
    )
    session.add(bronze_zeile)
    session.commit()

    session.add(
        MarketDataSilver(
            bronze_id=bronze_zeile.id,
            bronze_ingested_at=bronze_zeile.ingested_at,
            data_source_id=source_id,
            source_event_id=bronze_zeile.source_event_id,
            symbol="AAPL",
            normalisierter_wert=400,
            einheit=None,
            observed_at=bronze_zeile.observed_at,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_model_rejects_silver_row_without_matching_bronze_version(session: Session) -> None:
    """@trace datenqualitaet#AC3 — `bronze_id`/`bronze_ingested_at` muessen
    auf eine tatsaechlich existierende Bronze-Version verweisen
    (zusammengesetzte FK-Constraint, deckt `abgeleitet_aus: bronze_version`)."""
    source_id = session.query(DataSource).one().id
    session.add(
        MarketDataSilver(
            bronze_id=uuid.uuid4(),  # keine existierende Bronze-Zeile
            bronze_ingested_at=datetime(2026, 1, 1, tzinfo=UTC),
            data_source_id=source_id,
            source_event_id="ibkr:AAPL:2026-01-01",
            symbol="AAPL",
            normalisierter_wert=400,
            einheit="CHF",
            observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_migration_declares_data_source_id_and_unique_bronze_version_constraint() -> None:
    """@trace datenqualitaet#AC3 — Iteration-2-Reviewer-Befund (Critical):
    `data_source_id` (denormalisiert aus Bronze) ist Pflichtbestandteil des
    physischen Schemas, damit Rebuild-/Delete-Scoping nach der vollstaendigen
    Ereignis-Identitaet `(data_source_id, source_event_id)` filtern kann statt
    silent quellenuebergreifend zu loeschen. `uq_market_data_silver_bronze_
    version` erzwingt zusaetzlich physisch, dass je Bronze-Version hoechstens
    eine Silver-Zeile existiert (Nebenlaeufigkeits-Haertung, Iteration 2)."""
    source = _migration_source()
    assert "data_source_id UUID NOT NULL REFERENCES data_source (id)" in source
    assert "CONSTRAINT uq_market_data_silver_bronze_version" in source
    assert "UNIQUE (bronze_id, bronze_ingested_at, observed_at)" in source
    assert "ix_market_data_silver_data_source_id_symbol" in source
