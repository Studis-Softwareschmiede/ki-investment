"""Tests fuer die strategy_cluster/strategy/time_horizon-Stammdaten-Migration
(Story S-037).

Covers (strategie-exit-regeln): AC2, AC3

- AC2 wird strukturell gegen die Seed-Daten der Migration
  (`app/db/migrations/versions/ddaf9dcc6216_create_strategy_cluster_strategy_and_.py`)
  sowie gegen die CHECK-/FK-Constraints der ORM-Modelle
  (`app/db/models.StrategyCluster`/`Strategy`) geprueft.
- AC3 wird strukturell gegen die time_horizon-Seed-Daten sowie das
  ORM-Modell (`app/db/models.TimeHorizon`) geprueft.

Die Seed-Konstanten werden direkt aus der Migrationsdatei importiert (statt
dupliziert), damit ein kuenftiger Migrations-Edit ohne Test-Anpassung nicht
unbemerkt divergiert (Muster identisch zu `tests/db/test_asset_class_migration.py`).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import Strategy, StrategyCluster, TimeHorizon

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "app"
    / "db"
    / "migrations"
    / "versions"
    / "ddaf9dcc6216_create_strategy_cluster_strategy_and_.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("strategie_katalog_migration", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MIGRATION = _load_migration_module()
STRATEGY_CLUSTER_SEED = _MIGRATION.STRATEGY_CLUSTER_SEED
STRATEGY_SEED = _MIGRATION.STRATEGY_SEED
TIME_HORIZON_SEED = _MIGRATION.TIME_HORIZON_SEED


def _sqlite_engine_with_fk():
    """SQLite-Engine mit aktiviertem `PRAGMA foreign_keys=ON` — ohne dieses
    Pragma ignoriert SQLite Fremdschluessel-Constraints stillschweigend
    (dba-Lesson, siehe .claude/lessons/coder.md)."""
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


# Erwartete Cluster -> Strategien-Anzahl laut Konzept-Notiz
# "KI Investment – Anlagestrategien.md" (Implementierungs-Cluster-Tabelle).
EXPECTED_STRATEGY_COUNT_BY_CLUSTER = {
    "passiv_regelbasiert": 4,
    "aktiv_fundamental": 7,
    "aktiv_technisch_makro": 5,
    "professionell_algo": 2,
}

# Erwartete App-Stufe je Cluster (1:1-Mapping laut Konzept-Notiz).
EXPECTED_STUFE_BY_CLUSTER = {
    "passiv_regelbasiert": "MVP",
    "aktiv_fundamental": "Stufe2",
    "aktiv_technisch_makro": "Stufe3",
    "professionell_algo": "Stufe4",
}

# 9 Zeithorizont-Namen in Reihenfolge 1-9 laut Spec-AC3.
EXPECTED_TIME_HORIZON_NAMES_BY_ID = {
    1: "Hochfrequenz",
    2: "Scalping",
    3: "Daytrading",
    4: "Swing-Trading",
    5: "Position-Trading",
    6: "Mittelfristig",
    7: "Langfristig",
    8: "Buy-and-Hold",
    9: "Generationell",
}


def test_seed_covers_18_strategies_in_4_clusters() -> None:
    """@trace strategie-exit-regeln#AC2 — Katalog von 18 Strategien in 4
    Clustern (Passiv/Regelbasiert, Aktiv-Fundamental, Aktiv-Technisch/Makro,
    Professionell/Algorithmisch)."""
    assert len(STRATEGY_SEED) == 18
    assert len(STRATEGY_CLUSTER_SEED) == 4

    cluster_codes = {row["code"] for row in STRATEGY_CLUSTER_SEED}
    assert cluster_codes == set(EXPECTED_STRATEGY_COUNT_BY_CLUSTER)

    counts: dict[str, int] = {}
    for row in STRATEGY_SEED:
        assert row["cluster"] in cluster_codes
        counts[row["cluster"]] = counts.get(row["cluster"], 0) + 1
    assert counts == EXPECTED_STRATEGY_COUNT_BY_CLUSTER

    # Strategie-Namen sind eindeutig (UNIQUE-Constraint, keine Duplikate im Seed).
    names = [row["name"] for row in STRATEGY_SEED]
    assert len(names) == len(set(names))


def test_seed_strategy_stufe_matches_cluster_app_stufe_mapping() -> None:
    """@trace strategie-exit-regeln#AC2 — jede Strategie traegt die App-Stufe
    ihres Clusters (Passiv/Regelbasiert -> MVP, ... Professionell/Algo -> Stufe4)."""
    for row in STRATEGY_SEED:
        assert row["stufe"] == EXPECTED_STUFE_BY_CLUSTER[row["cluster"]]


def test_seed_only_passiv_regelbasiert_cluster_ist_freigeschaltet() -> None:
    """@trace strategie-exit-regeln#AC2 — im MVP ist ausschliesslich der
    Cluster Passiv/Regelbasiert freigeschaltet (deckt E2: Anforderung
    ausserhalb des freigeschalteten Clusters wird abgelehnt)."""
    freigeschaltet = {row["code"] for row in STRATEGY_CLUSTER_SEED if row["freigeschaltet"]}
    assert freigeschaltet == {"passiv_regelbasiert"}

    gesperrt = {row["code"] for row in STRATEGY_CLUSTER_SEED if not row["freigeschaltet"]}
    assert gesperrt == {"aktiv_fundamental", "aktiv_technisch_makro", "professionell_algo"}


def test_passiv_regelbasiert_cluster_enthaelt_die_spec_genannten_beispiele() -> None:
    """@trace strategie-exit-regeln#AC2 — Spec nennt "u. a. Index, DCA,
    Dividende, Factor/Smart Beta" als Beispiele des freigeschalteten Clusters."""
    passiv_namen = {row["name"] for row in STRATEGY_SEED if row["cluster"] == "passiv_regelbasiert"}
    assert passiv_namen == {"Index", "DCA", "Dividende", "Factor/Smart Beta"}


def test_seed_covers_9_time_horizon_stufen_in_order() -> None:
    """@trace strategie-exit-regeln#AC3 — Zeithorizont aus genau 9 Stufen
    (1 Hochfrequenz ... 9 Generationell)."""
    assert len(TIME_HORIZON_SEED) == 9
    ids = sorted(row["id"] for row in TIME_HORIZON_SEED)
    assert ids == list(range(1, 10))
    for row in TIME_HORIZON_SEED:
        assert row["name"] == EXPECTED_TIME_HORIZON_NAMES_BY_ID[row["id"]]


def test_seed_time_horizon_has_transaktionskosten_und_break_even_attribute() -> None:
    """@trace strategie-exit-regeln#AC3 — zu jeder Stufe sind
    Transaktionskosten-Relevanz und Break-Even-Anforderung als Attribut
    hinterlegt."""
    for row in TIME_HORIZON_SEED:
        assert row["transaktionskosten_relevanz"].strip()
        assert row["break_even_anforderung"].strip()


def test_model_rejects_strategy_cluster_code_outside_catalog() -> None:
    """@trace strategie-exit-regeln#AC2 — nur die 4 katalogisierten
    Cluster-Codes sind gueltig (CHECK-Constraint)."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(StrategyCluster(code="unbekannt", name="Unbekannt", freigeschaltet=False))
        with pytest.raises(IntegrityError):
            session.commit()


def test_model_rejects_invalid_strategy_stufe() -> None:
    """@trace strategie-exit-regeln#AC2 — nur MVP/Stufe2/Stufe3/Stufe4 sind
    gueltige App-Stufen fuer eine Strategie."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(StrategyCluster(code="passiv_regelbasiert", name="Passiv", freigeschaltet=True))
        session.commit()
        session.add(Strategy(name="Ungueltig", cluster="passiv_regelbasiert", stufe="StufeX"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_model_rejects_strategy_with_unknown_cluster_fk() -> None:
    """@trace strategie-exit-regeln#AC2 — `strategy.cluster` ist ein FK auf
    `strategy_cluster.code`; ein nicht existierender Cluster wird abgelehnt."""
    engine = _sqlite_engine_with_fk()
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Strategy(name="Waise", cluster="nicht_existent", stufe="MVP"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_model_rejects_time_horizon_id_outside_1_9() -> None:
    """@trace strategie-exit-regeln#AC3 — Zeithorizont-Stufe ist per
    CHECK-Constraint auf 1-9 begrenzt."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            TimeHorizon(
                id=10,
                name="Ungueltig",
                transaktionskosten_relevanz="MINIMAL",
                break_even_anforderung="n/a",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_seed_insert_is_idempotent_via_on_conflict_do_nothing() -> None:
    """Verifiziert data-model.md §11 Punkt 10 ("Idempotent seedbar via
    ON CONFLICT DO NOTHING") fuer die drei Seed-Insert-Statements dieser
    Migration — kein `@trace`-Tag, da allgemeine DB-Konvention, keine
    bestimmte AC/BR.

    `postgresql.insert(...).on_conflict_do_nothing(...)` ist nur unter dem
    Postgres-Dialekt compilierbar; daher wird hier die compilierte SQL
    geprueft statt ein echter Doppel-Lauf (Muster identisch zu
    `tests/db/test_asset_class_migration.py`).
    """
    from sqlalchemy import Boolean, Column, MetaData, SmallInteger, String, Table
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    metadata = MetaData()
    strategy_cluster = Table(
        "strategy_cluster",
        metadata,
        Column("code", String, primary_key=True),
        Column("name", String, nullable=False, unique=True),
        Column("freigeschaltet", Boolean, nullable=False),
    )
    strategy = Table(
        "strategy",
        metadata,
        Column("name", String, nullable=False, unique=True),
        Column("cluster", String, nullable=False),
        Column("stufe", String, nullable=False),
    )
    time_horizon = Table(
        "time_horizon",
        metadata,
        Column("id", SmallInteger, primary_key=True, autoincrement=False),
        Column("name", String, nullable=False, unique=True),
        Column("transaktionskosten_relevanz", String, nullable=False),
        Column("break_even_anforderung", String, nullable=False),
    )

    cluster_stmt = (
        pg_insert(strategy_cluster)
        .values(STRATEGY_CLUSTER_SEED)
        .on_conflict_do_nothing(index_elements=["code"])
    )
    strategy_stmt = (
        pg_insert(strategy).values(STRATEGY_SEED).on_conflict_do_nothing(index_elements=["name"])
    )
    horizon_stmt = (
        pg_insert(time_horizon)
        .values(TIME_HORIZON_SEED)
        .on_conflict_do_nothing(index_elements=["id"])
    )

    for stmt, conflict_col in (
        (cluster_stmt, "(code)"),
        (strategy_stmt, "(name)"),
        (horizon_stmt, "(id)"),
    ):
        compiled_sql = str(stmt.compile(dialect=postgresql.dialect()))
        assert "ON CONFLICT" in compiled_sql
        assert "DO NOTHING" in compiled_sql
        assert conflict_col in compiled_sql
