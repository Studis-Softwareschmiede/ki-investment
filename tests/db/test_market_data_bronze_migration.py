"""Tests fuer die market_data_bronze-Migration (Story S-022).

Covers (datenqualitaet): AC1, AC2, AC9, AC10

- AC1 (immutabel/append-only): das ORM-Modell (`app.db.models.MarketDataBronze`)
  bildet Pflichtfelder + FK-Constraints strukturell ab (SQLite); die
  BEFORE-UPDATE/DELETE-Trigger-Migration selbst ist Postgres-spezifisches DDL
  (`PARTITION BY RANGE`, `plpgsql`-Funktionen) und daher nicht unter SQLite
  ausfuehrbar — hier per Quelltext-Pruefung der Migrationsdatei abgesichert
  (Regressionsschutz gegen versehentliches Entfernen), der reale
  Trigger-Effekt (UPDATE/DELETE scheitert mit Exception) wurde manuell gegen
  die lokale Compose-Postgres-Instanz verifiziert (Coder-Self-Test, siehe
  Handoff).
- AC2/AC9/AC10 (Point-in-Time/Idempotenz/Versionierung): die
  Verhaltenslogik selbst ist in `tests/db/test_bronze.py`
  (`app.db.bronze`) vollstaendig abgedeckt; hier nur die strukturelle
  Absicherung, dass die DB-seitige zweite Sicherung (Dedupe-/Versionierungs-
  Trigger) in der Migration tatsaechlich vorhanden ist (Quelltext-Pruefung).

Die Migration selbst per `alembic upgrade head` gegen eine lokale
Compose-Postgres-Instanz (Coder-Self-Test, siehe Handoff) angewendet und
manuell verifiziert: (1) Insert eines Datenpunkts -> 1 Zeile; (2) identischer
Re-Insert -> weiterhin 1 Zeile (AC9); (3) Insert mit abweichendem `payload`
fuer dieselbe (data_source_id, source_event_id) -> 2 Zeilen, die erste
unveraendert (AC10); (4) `UPDATE market_data_bronze SET payload = ...` und
`DELETE FROM market_data_bronze` scheitern beide mit der erwarteten Exception
(AC1/BR-121); (5) zweiter `alembic upgrade head`-Lauf ist ein No-Op
(bereits auf Head).

**Iteration-2-Fix-Verifikation (Reviewer-Befund, siehe
`.claude/lessons/coder.md`):** zusaetzlich manuell gegen eine frische
Docker-Postgres-17-Instanz verifiziert (DDL direkt aus dieser Migration
extrahiert, da kein Testcontainer-Setup im Projekt existiert):
(a) ein identischer Re-Insert wirft jetzt eine abfangbare Exception
(`ERROR: market_data_bronze_duplicate ...`, SQLSTATE `unique_violation`)
statt still `RETURN NULL` auszufuehren; (b) zwei parallele, ueberlappende
`app.db.bronze.record_observation()`-Aufrufe (zwei echte Threads, zwei
Sessions, jeweils 0.3s offene Transaktion vor `commit()`) fuer dieselbe
`(data_source_id, source_event_id)` lieferten OHNE den `pg_advisory_xact_lock`
zwei Duplikat-Zeilen (reproduzierter Iteration-1-Befund), MIT Lock genau
eine Zeile und in beiden Threads dieselbe `id` — kein `ObjectDeletedError`
nach `commit()` bei nachfolgendem Attributzugriff.
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
from app.db.models import AssetClass, DataSource, MarketDataBronze

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "app"
    / "db"
    / "migrations"
    / "versions"
    / "cfdd83ba9a2c_create_market_data_bronze_bronze_layer.py"
)


def _migration_source() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


def test_migration_chains_onto_current_head() -> None:
    """@trace datenqualitaet#AC1 — die Migration haengt korrekt an den
    bisherigen Head (`ea80c97626ee`), keine gebrochene down_revision-Kette
    (alembic/A03/A05)."""
    source = _migration_source()
    assert 'revision: str = "cfdd83ba9a2c"' in source
    assert 'down_revision: Union[str, Sequence[str], None] = "ea80c97626ee"' in source


def test_migration_declares_range_partitioning_and_default_partition() -> None:
    """@trace datenqualitaet#AC2 — `ingested_at` ist Partitionsschluessel
    (data-model.md §9, Point-in-Time/Replay je Partition); eine
    Default-Partition faengt jeden Wert strukturell auf."""
    source = _migration_source()
    assert "PARTITION BY RANGE (ingested_at)" in source
    assert "PARTITION OF market_data_bronze DEFAULT" in source


def test_migration_declares_dedupe_and_immutability_triggers() -> None:
    """@trace datenqualitaet#AC9 — die DB-seitige zweite Idempotenz-/
    Versionierungs-Sicherung (BEFORE INSERT) ist vorhanden UND wirft bei
    einem Duplikat eine abfangbare Exception (Iteration-2-Fix: kein
    stilles `RETURN NULL` mehr, siehe `app/db/bronze.py`).
    @trace datenqualitaet#AC10 — derselbe Trigger laesst inhaltlich
    abweichende Ankuenfte als neue Version durch statt sie zu verwerfen.
    """
    source = _migration_source()
    # Isoliert den Quelltext der Dedupe-Trigger-Funktion (zwischen ihrer
    # Definition und dem ersten `$$ LANGUAGE plpgsql;`), damit die
    # "kein `RETURN NULL` mehr"-Pruefung unten nicht faelschlich auf
    # Docstring-Erwaehnungen des alten Verhaltens anschlaegt.
    dedupe_funktion = source.split("_DEDUPE_FUNCTION_NAME}() RETURNS TRIGGER AS $$")[1].split(
        "$$ LANGUAGE"
    )[0]

    assert "trg_market_data_bronze_dedupe_or_version" in source
    assert "BEFORE INSERT ON market_data_bronze" in source
    assert "RAISE EXCEPTION" in dedupe_funktion
    assert "ERRCODE = 'unique_violation'" in dedupe_funktion  # abfangbar statt stillem RETURN NULL
    assert "RETURN NULL" not in dedupe_funktion  # Iteration-2-Fix: kein stiller No-Op mehr
    assert "RETURN NEW" in dedupe_funktion  # neue Version bei abweichendem Inhalt


def test_migration_declares_immutability_trigger_for_update_and_delete() -> None:
    """@trace datenqualitaet#AC1 — BEFORE-UPDATE/DELETE-Trigger weist jeden
    Aenderungsversuch zurueck (BR-121, append-only)."""
    source = _migration_source()
    assert "BEFORE UPDATE OR DELETE ON market_data_bronze" in source
    assert "RAISE EXCEPTION" in source


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
            AssetClass(
                id=3, name="Cash/Geldmarkt", prio_stufe="MVP", aktiv=True, retail_driven=False
            )
        )
        db_session.add(
            DataSource(
                id=uuid.uuid4(),
                name="FRED - Federal Reserve Economic Data",
                kategorie="makro_anleihen",
                qualitaet="sehr_hoch",
                frequenz_sekunden=86400,
                aktiv=True,
            )
        )
        db_session.commit()
        yield db_session


def test_model_requires_payload_and_observed_at(session: Session) -> None:
    """@trace datenqualitaet#AC1 — `payload` (roh_wert) und `observed_at`
    (beobachtungs_zeitpunkt) sind Pflichtfelder des Bronze-Vertrags; ein
    Datensatz ohne Point-in-Time-Zeitpunkt wird zurueckgewiesen."""
    source_id = session.query(DataSource).one().id
    session.add(
        MarketDataBronze(
            data_source_id=source_id,
            source_event_id="fred:CPIAUCSL:2026-01-01",
            payload={"value": "3.1"},
            observed_at=None,  # fehlender Point-in-Time-Zeitpunkt (AC2-Pflichtfeld)
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_model_rejects_unknown_data_source(session: Session) -> None:
    """@trace datenqualitaet#AC1 — `data_source_id` muss auf eine
    registrierte Quelle verweisen (FK-Constraint)."""
    session.add(
        MarketDataBronze(
            data_source_id=uuid.uuid4(),  # keine registrierte Quelle
            source_event_id="fred:CPIAUCSL:2026-01-01",
            payload={"value": "3.1"},
            observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
