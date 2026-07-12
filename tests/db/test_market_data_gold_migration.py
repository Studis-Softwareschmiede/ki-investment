"""Tests fuer die market_data_gold-Migration (Story S-051).

Covers (datenqualitaet): AC4

- AC4 (Anreicherung, Reproduzierbarkeit): die Migration ist
  Postgres-spezifisches DDL (`PARTITION BY RANGE`) und daher nicht unter
  SQLite ausfuehrbar -- hier per Quelltext-Pruefung abgesichert
  (Regressionsschutz, analog `tests/db/test_market_data_silver_migration.py`),
  die Verhaltenslogik selbst ist in `tests/db/test_gold.py`
  (`app.db.gold`) vollstaendig abgedeckt. Das ORM-Modell
  (`app.db.models.MarketDataGold`) bildet die zusammengesetzte FK auf
  `market_data_silver(id, observed_at)` strukturell ab (SQLite mit
  aktivierten Foreign-Key-Pragmas).

Die Migration selbst wurde per `alembic upgrade head` gegen eine lokale
Postgres-17-Instanz (`docker run postgres:17-alpine`) angewendet und manuell
verifiziert (Coder-Self-Test, siehe Handoff): (1) Tabelle inkl.
Default-Partition, Indizes, FK- und Unique-Constraints wird korrekt angelegt
(per psql-Schema-Introspektion geprueft); (2) ein Insert mit einem
`silver_id`/`data_source_id`-Paar, das auf keine bestehende Silver-/
Datenquellen-Zeile verweist, scheitert an der zusammengesetzten FK bzw. der
`data_source_id`-FK; (3) ein zweiter `alembic upgrade head`-Lauf ist ein
No-Op (bereits auf Head). Der erste Anlauf der Migration schlug mit
PostgreSQL 17 real fehl (`FeatureNotSupported: unique constraint on
partitioned table must include all partitioning columns` — SQLite haette
das nicht erkannt), weil `uq_market_data_gold_silver_version` den
Partitionsschluessel `observed_at` nicht enthielt; behoben durch Aufnahme von
`observed_at` in den Unique-Index (siehe Migrations-Docstring).
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
from app.db.models import AssetClass, DataSource, MarketDataBronze, MarketDataGold, MarketDataSilver

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "app"
    / "db"
    / "migrations"
    / "versions"
    / "0da3d5a72ba2_create_market_data_gold_gold_layer.py"
)


def _migration_source() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


def test_migration_chains_onto_current_head() -> None:
    """@trace datenqualitaet#AC4 — die Migration haengt korrekt an den
    bisherigen Head (`cf167d0a63f5`, Silver-Migration), keine gebrochene
    down_revision-Kette (alembic/A03/A05)."""
    source = _migration_source()
    assert 'revision: str = "0da3d5a72ba2"' in source
    assert 'down_revision: Union[str, Sequence[str], None] = "cf167d0a63f5"' in source


def test_migration_declares_range_partitioning_and_default_partition() -> None:
    """@trace datenqualitaet#AC4 — `observed_at` ist Partitionsschluessel
    (data-model.md §9), eine Default-Partition faengt jeden Wert
    strukturell auf (analog Bronze/Silver)."""
    source = _migration_source()
    assert "PARTITION BY RANGE (observed_at)" in source
    assert "PARTITION OF market_data_gold DEFAULT" in source


def test_migration_declares_foreign_key_to_silver_composite_pk() -> None:
    """@trace datenqualitaet#AC4 — `herkunft: silver_version` (Spec-Vertrag)
    wird als zusammengesetzte FK auf `market_data_silver(id, observed_at)`
    erzwungen (Partitionsschluessel-Pflicht bei FK auf partitionierte
    Tabelle)."""
    source = _migration_source()
    assert "FOREIGN KEY (silver_id, silver_observed_at)" in source
    assert "REFERENCES market_data_silver (id, observed_at)" in source


def test_migration_declares_qualitaetsindikator_and_data_source_id_columns() -> None:
    """@trace datenqualitaet#AC4 — die Spalten fuer Vertragsfeld
    `qualitaetsindikator` und die denormalisierte
    Cross-Data-Source-Sicherheits-Spalte `data_source_id` sind Teil des
    physischen Schemas."""
    source = _migration_source()
    assert "qualitaetsindikator TEXT" in source
    assert "data_source_id UUID NOT NULL REFERENCES data_source (id)" in source
    assert "CONSTRAINT uq_market_data_gold_silver_version" in source
    assert "UNIQUE (silver_id, silver_observed_at, observed_at)" in source
    assert "ix_market_data_gold_data_source_id_symbol" in source


def test_migration_declares_no_immutability_trigger() -> None:
    """@trace datenqualitaet#AC4 — anders als Bronze (BR-121) ist Gold NICHT
    append-only (Rebuild aus Silver/Bronze jederzeit moeglich, AC4-NFR) --
    kein BEFORE-UPDATE/DELETE-Trigger vorhanden."""
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


def test_model_requires_angereicherter_wert(session: Session) -> None:
    """@trace datenqualitaet#AC4 — `angereicherter_wert` ist Pflichtfeld des
    Gold-Vertrags; ein Datensatz ohne diesen Wert wird zurueckgewiesen."""
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
    silber_zeile = MarketDataSilver(
        bronze_id=bronze_zeile.id,
        bronze_ingested_at=bronze_zeile.ingested_at,
        data_source_id=source_id,
        source_event_id=bronze_zeile.source_event_id,
        symbol="AAPL",
        normalisierter_wert=400,
        einheit="CHF",
        observed_at=bronze_zeile.observed_at,
    )
    session.add(silber_zeile)
    session.commit()

    session.add(
        MarketDataGold(
            silver_id=silber_zeile.id,
            silver_observed_at=silber_zeile.observed_at,
            data_source_id=source_id,
            source_event_id=silber_zeile.source_event_id,
            symbol="AAPL",
            angereicherter_wert=None,
            observed_at=silber_zeile.observed_at,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_model_rejects_gold_row_without_matching_silver_version(session: Session) -> None:
    """@trace datenqualitaet#AC4 — `silver_id`/`silver_observed_at` muessen
    auf eine tatsaechlich existierende Silver-Version verweisen
    (zusammengesetzte FK-Constraint, deckt `herkunft: silver_version`)."""
    source_id = session.query(DataSource).one().id
    session.add(
        MarketDataGold(
            silver_id=uuid.uuid4(),  # keine existierende Silver-Zeile
            silver_observed_at=datetime(2026, 1, 1, tzinfo=UTC),
            data_source_id=source_id,
            source_event_id="ibkr:AAPL:2026-01-01",
            symbol="AAPL",
            angereicherter_wert=400,
            observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
