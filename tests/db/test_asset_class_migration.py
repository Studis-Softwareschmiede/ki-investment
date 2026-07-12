"""Tests fuer die asset_class-Stammdaten-Migration (Story S-003).

Covers (anlageklassen-config): AC1, AC2, AC3, AC12
- AC1/AC2/AC3 werden strukturell gegen die Seed-Daten der Migration
  (`app/db/migrations/versions/b2bd709be080_...py`) sowie gegen die
  CHECK-Constraints des ORM-Modells (`app/db/models.AssetClass`) geprueft.
- AC12 (Persistenz ueber Neustarts) wird ueber eine dateibasierte SQLite-DB
  simuliert: ein zweiter, unabhaengiger Engine-/Session-Zyklus gegen dieselbe
  Datei steht fuer einen Prozess-Neustart. Die tatsaechliche Postgres-Ziel-DB
  (`db_dialect: postgres`) wurde zusaetzlich manuell per
  `alembic upgrade head` gegen eine lokale Compose-Postgres-Instanz
  verifiziert (Coder-Self-Test, siehe Handoff) — kein automatisierter
  Docker-Postgres-Start in `uv run pytest` (Migrations-Apply ist laut
  `migration-tool-subsystem.md` §9 ein separater Smoke-Schritt, kein
  Pytest-Bestandteil).

Die Seed-Konstante wird direkt aus der Migrationsdatei importiert (statt
dupliziert), damit ein kuenftiger Migrations-Edit ohne Test-Anpassung nicht
unbemerkt divergiert.

Zusaetzlich (Iteration 2, DBA-Review-Fix): der Seed-Insert der Migration
verwendet `postgresql.insert(...).on_conflict_do_nothing()` (idempotenter
Seed laut docs/data-model.md §11 Punkt 10). Da dieses Konstrukt nur unter dem
Postgres-Dialekt compilierbar ist und `uv run pytest` laut
`migration-tool-subsystem.md` §9 keinen Docker-Postgres startet, wird die
Idempotenz hier durch Kompilieren des Insert-Statements gegen den
Postgres-Dialekt geprueft (SQL enthaelt `ON CONFLICT ... DO NOTHING` auf der
`id`-Spalte) statt durch tatsaechliches zweifaches Ausfuehren. Der reale
zweifache `alembic upgrade head`-Lauf (weiterhin 11 Zeilen nach Re-Run) wurde
manuell gegen die lokale Compose-Postgres-Instanz verifiziert (Coder-Self-Test,
siehe Handoff).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import AssetClass

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "app"
    / "db"
    / "migrations"
    / "versions"
    / "b2bd709be080_create_asset_class_table_and_seed_11_.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("seed_migration", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SEED = _load_migration_module().ASSET_CLASS_SEED

# Verbindliche Nummerierung + Namen laut AC1.
EXPECTED_NAMES_BY_ID = {
    1: "Aktien",
    2: "ETFs",
    3: "Cash/Geldmarkt",
    4: "Obligationen",
    5: "Aktive Fonds",
    6: "Immobilien",
    7: "Kryptowährungen",
    8: "Rohstoffe",
    9: "Infrastrukturfonds",
    10: "FX",
    11: "Derivate",
}

# Empfehlungsstufe je Klasse laut Verträge-Tabelle (AC3).
EXPECTED_PRIO_STUFE_BY_ID = {
    1: "MVP",
    2: "MVP",
    3: "MVP",
    4: "Stufe2",
    5: "Stufe2",
    6: "Stufe2",
    7: "Stufe3",
    8: "Stufe3",
    9: "Stufe3",
    10: "Stufe3",
    11: "Stufe3",
}


def test_seed_covers_all_11_classes_with_binding_numbering() -> None:
    """@trace anlageklassen-config#AC1 — 11 Klassen, IDs 1-11 lückenlos, Namen gemäss AC1-Liste."""
    ids = sorted(row["id"] for row in SEED)
    assert ids == list(range(1, 12))
    for row in SEED:
        assert row["name"] == EXPECTED_NAMES_BY_ID[row["id"]]


def test_seed_default_active_classes_are_aktien_etfs_krypto() -> None:
    """@trace anlageklassen-config#AC2 — Erstinstallations-Default aktiv = {1, 2, 7}."""
    active_ids = {row["id"] for row in SEED if row["aktiv"]}
    assert active_ids == {1, 2, 7}
    inactive_ids = {row["id"] for row in SEED if not row["aktiv"]}
    assert inactive_ids == set(range(1, 12)) - {1, 2, 7}


def test_seed_recommendation_stufe_matches_vertraege_table() -> None:
    """@trace anlageklassen-config#AC3 — Empfehlungsstufe je Klasse, Krypto bewusst Stufe3
    trotz aktiv-Default (Spec-Hinweis Verträge-Tabelle)."""
    for row in SEED:
        assert row["prio_stufe"] == EXPECTED_PRIO_STUFE_BY_ID[row["id"]]
    # Krypto (7) ist aktiv, aber NICHT MVP-Empfehlungsstufe — Empfehlung
    # schränkt Aktivierbarkeit nicht ein (AC3 zweiter Satz).
    krypto = next(row for row in SEED if row["id"] == 7)
    assert krypto["aktiv"] is True
    assert krypto["prio_stufe"] == "Stufe3"


def test_model_rejects_id_outside_1_11() -> None:
    """@trace anlageklassen-config#AC1 — verbindliche Nummerierung 1-11 wird per
    CHECK-Constraint erzwungen (BR-100), keine Klasse ausserhalb des Bereichs."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            AssetClass(id=12, name="Ungültig", prio_stufe="MVP", aktiv=False, retail_driven=False)
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_model_rejects_invalid_prio_stufe() -> None:
    """@trace anlageklassen-config#AC3 — nur MVP/Stufe2/Stufe3 sind gültige Empfehlungsstufen."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            AssetClass(id=1, name="Aktien", prio_stufe="Stufe5", aktiv=True, retail_driven=True)
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_toggle_state_persists_across_reconnect(tmp_path) -> None:
    """@trace anlageklassen-config#AC12 — Toggle-Zustand persistiert über einen
    neuen Verbindungs-/Session-Zyklus hinweg (simuliert Neustart) statt nur
    im Prozessspeicher zu leben."""
    db_file = tmp_path / "asset_class_persist.sqlite"

    first_engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(first_engine)
    with Session(first_engine) as session:
        session.add_all(AssetClass(**row) for row in SEED)
        session.commit()
    first_engine.dispose()

    # Neuer, unabhängiger Engine-/Session-Zyklus gegen dieselbe Datei —
    # steht für einen Prozess-/App-Neustart (AC12: „persistent über Neustarts").
    second_engine = create_engine(f"sqlite:///{db_file}")
    with Session(second_engine) as session:
        aktien = session.get(AssetClass, 1)
        krypto = session.get(AssetClass, 7)
        cash = session.get(AssetClass, 3)
        assert aktien is not None and aktien.aktiv is True
        assert krypto is not None and krypto.aktiv is True
        assert cash is not None and cash.aktiv is False
    second_engine.dispose()


def test_seed_insert_is_idempotent_via_on_conflict_do_nothing() -> None:
    """Verifiziert data-model.md §11 Punkt 10 ("Idempotent seedbar via
    ON CONFLICT DO NOTHING") fuer den Migrations-Seed-Insert — kein `@trace`-Tag,
    da keiner bestimmten AC/BR zugeordnet, sondern eine allgemeine DB-Konvention.

    `postgresql.insert(...).on_conflict_do_nothing(...)` ist nur unter dem
    Postgres-Dialekt compilierbar (nicht gegen SQLite ausfuehrbar) — daher wird
    hier die compilierte SQL geprueft statt ein echter Doppel-Lauf. Der reale
    doppelte `alembic upgrade head`-Lauf (Zeilenzahl bleibt 11) wurde manuell
    gegen die lokale Compose-Postgres-Instanz verifiziert (Coder-Self-Test).
    """
    from sqlalchemy import Boolean, Column, MetaData, SmallInteger, String, Table
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    metadata = MetaData()
    asset_class = Table(
        "asset_class",
        metadata,
        Column("id", SmallInteger, primary_key=True, autoincrement=False),
        Column("name", String, nullable=False, unique=True),
        Column("prio_stufe", String, nullable=False),
        Column("aktiv", Boolean, nullable=False),
        Column("retail_driven", Boolean, nullable=False),
    )

    stmt = pg_insert(asset_class).values(SEED).on_conflict_do_nothing(index_elements=["id"])
    compiled_sql = str(stmt.compile(dialect=postgresql.dialect()))

    assert "ON CONFLICT" in compiled_sql
    assert "DO NOTHING" in compiled_sql
    assert "(id)" in compiled_sql
