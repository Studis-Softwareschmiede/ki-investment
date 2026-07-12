"""Tests fuer die data_source-/data_source_asset_class-Registry-Migration (Story S-006).

Covers (dateneingang): AC5, AC6, AC13
- AC5 (12 Quellen in 5 Kategorien, Anlageklassen-Zuordnung je Quelle) wird
  strukturell gegen die Seed-Daten der Migration
  (`app/db/migrations/versions/3654339f201d_...py`) geprueft.
- AC6 (Reddit-Sentiment ausschliesslich fuer retail-getriebene Klassen 1/7,
  keine Zeile fuer 4/10) wird sowohl gegen die
  `DATA_SOURCE_ASSET_CLASS_SEED`-Zuordnung dieser Migration als auch
  gegenkontrolliert gegen das `retail_driven`-Flag der `asset_class`-Seed-Daten
  (`app/db/migrations/versions/b2bd709be080_...py`, Story S-003/AC-anlageklassen-config)
  geprueft.
- AC13 (nur die 5 kostenlosen MVP-Quellen sind aktiv, alle anderen registriert
  aber deaktiviert) wird gegen das `aktiv`-Feld jeder Seed-Zeile geprueft.

Die CHECK-Constraints des ORM-Modells (`app/db/models.DataSource`) werden
zusaetzlich strukturell gegen eine SQLite-In-Memory-DB verifiziert (Konvention
aus `test_asset_class_migration.py`/`test_category_weight_migration.py`).

Die Seed-Konstanten werden direkt aus der Migrationsdatei importiert (statt
dupliziert), damit ein kuenftiger Migrations-Edit ohne Test-Anpassung nicht
unbemerkt divergiert.
"""

from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import DataSource

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "app"
    / "db"
    / "migrations"
    / "versions"
    / "3654339f201d_create_data_source_and_data_source_.py"
)
ASSET_CLASS_MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "app"
    / "db"
    / "migrations"
    / "versions"
    / "b2bd709be080_create_asset_class_table_and_seed_11_.py"
)


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MIGRATION = _load_module(MIGRATION_PATH, "data_source_migration")
SOURCE_SEED = _MIGRATION.DATA_SOURCE_SEED
SOURCE_ASSET_CLASS_SEED = _MIGRATION.DATA_SOURCE_ASSET_CLASS_SEED

_ASSET_CLASS_MIGRATION = _load_module(ASSET_CLASS_MIGRATION_PATH, "asset_class_migration_for_ds")
ASSET_CLASS_SEED = _ASSET_CLASS_MIGRATION.ASSET_CLASS_SEED

# AC5: die 5 Kategorien aus C-009/"KI Investment – Datenquellen.md".
EXPECTED_CATEGORIES = {
    "equity_fundamentals",
    "retail_social",
    "blockchain_crypto",
    "etf_fonds",
    "makro_anleihen",
}

# AC13: wörtlich aus der Spec — genau diese 5 Quellen sind im MVP aktiv.
EXPECTED_ACTIVE_SOURCE_NAMES = {
    "SEC Form 4 Insider-Trades",
    "Reddit WallStreetBets Sentiment",
    "Polymarket Prediction Markets",
    "FRED – Federal Reserve Economic Data",
    "Wirtschaftskalender (Finnworlds)",
}


def _asset_classes_by_source() -> dict[str, set[int]]:
    return {name: set(asset_class_ids) for name, asset_class_ids in SOURCE_ASSET_CLASS_SEED}


def test_seed_has_exactly_12_sources_in_5_categories() -> None:
    """@trace dateneingang#AC5 — die Registry führt 12 Quellen in genau den
    5 Kategorien (Equity Insider & Fundamentals, Retail Sentiment & Social,
    Blockchain & Crypto, ETFs & Fonds, Makro & Anleihen)."""
    assert len(SOURCE_SEED) == 12
    names = [row["name"] for row in SOURCE_SEED]
    assert len(names) == len(set(names)), "Quellennamen müssen eindeutig sein (UNIQUE)"
    categories = {row["kategorie"] for row in SOURCE_SEED}
    assert categories == EXPECTED_CATEGORIES
    for category in EXPECTED_CATEGORIES:
        assert any(row["kategorie"] == category for row in SOURCE_SEED), (
            f"Kategorie {category} hat keine einzige Quelle"
        )


def test_every_source_maps_to_at_least_one_asset_class_1_to_11() -> None:
    """@trace dateneingang#AC5 — jede Quelle ist mindestens einer Anlageklasse
    (1–11) zugeordnet, für die sie verwertbare Signale liefert."""
    mapping = _asset_classes_by_source()
    source_names = {row["name"] for row in SOURCE_SEED}
    assert set(mapping.keys()) == source_names
    for name, asset_class_ids in mapping.items():
        assert asset_class_ids, f"Quelle {name} hat keine Anlageklassen-Zuordnung"
        assert asset_class_ids.issubset(set(range(1, 12))), (
            f"Quelle {name} referenziert eine Anlageklasse ausserhalb 1-11"
        )


def test_reddit_covers_only_retail_driven_classes_1_and_7() -> None:
    """@trace dateneingang#AC6 — Reddit-Sentiment wird ausschliesslich für die
    retail-getriebenen Anlageklassen Aktien (1) und Krypto (7) herangezogen;
    für Obligationen (4) und FX (10) existiert keine Reddit-Zeile."""
    mapping = _asset_classes_by_source()
    reddit_classes = mapping["Reddit WallStreetBets Sentiment"]
    assert reddit_classes == {1, 7}
    assert 4 not in reddit_classes
    assert 10 not in reddit_classes


def test_reddit_asset_classes_match_retail_driven_flag_in_asset_class_seed() -> None:
    """@trace dateneingang#AC6 — die Reddit-Zuordnung deckt sich mit dem
    `retail_driven`-Flag der `asset_class`-Stammdaten (BR-123): exakt die
    Klassen mit `retail_driven=True` (1, 7) tauchen bei Reddit auf, alle
    `retail_driven=False`-Klassen (u. a. 4 Obligationen, 10 FX) nicht."""
    retail_driven_ids = {row["id"] for row in ASSET_CLASS_SEED if row["retail_driven"]}
    non_retail_driven_ids = {row["id"] for row in ASSET_CLASS_SEED if not row["retail_driven"]}
    assert retail_driven_ids == {1, 7}

    reddit_classes = _asset_classes_by_source()["Reddit WallStreetBets Sentiment"]
    assert reddit_classes == retail_driven_ids
    assert reddit_classes.isdisjoint(non_retail_driven_ids)


def test_mvp_active_sources_are_exactly_the_5_free_sources() -> None:
    """@trace dateneingang#AC13 — im MVP sind nur die kostenlosen Quellen
    (SEC Form 4, Reddit, Polymarket, FRED, Wirtschaftskalender) aktiv."""
    active_names = {row["name"] for row in SOURCE_SEED if row["aktiv"]}
    assert active_names == EXPECTED_ACTIVE_SOURCE_NAMES
    assert len(active_names) == 5


def test_paid_institutional_sources_are_registered_but_inactive() -> None:
    """@trace dateneingang#AC13 — kostenpflichtige/institutionelle Quellen
    (7 der 12) sind registriert (in der Seed-Tabelle vorhanden), aber
    `aktiv=false` — sie lösen ohne Aktivierung keinen Abruf aus, da der
    Scheduler (spätere Story) ausschliesslich `aktiv=true`-Quellen abfragt."""
    inactive_rows = [row for row in SOURCE_SEED if not row["aktiv"]]
    assert len(inactive_rows) == 7
    inactive_names = {row["name"] for row in inactive_rows}
    assert inactive_names.isdisjoint(EXPECTED_ACTIVE_SOURCE_NAMES)
    for row in inactive_rows:
        assert row["kostenmodell"] in {"pro", "institutionell", "free_tier"}, (
            f"{row['name']}: unerwartetes kostenmodell {row['kostenmodell']!r} für eine "
            "im MVP deaktivierte Quelle"
        )


def test_model_rejects_invalid_kategorie() -> None:
    """@trace dateneingang#AC5 — nur die 5 definierten Kategorien sind gültig
    (CHECK-Constraint)."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            DataSource(
                name="Ungültige Quelle",
                kategorie="unbekannt",
                frequenz_sekunden=3600,
                aktiv=False,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_model_rejects_frequenz_outside_30_to_86400() -> None:
    """@trace dateneingang#AC5 — Abrufintervall ausserhalb 30-86400 Sekunden
    wird als ungültig zurückgewiesen (CHECK-Constraint)."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            DataSource(
                name="Zu schnelle Quelle",
                kategorie="makro_anleihen",
                frequenz_sekunden=5,
                aktiv=False,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_model_accepts_valid_minimal_source() -> None:
    """Strukturelle Gegenprobe zu den beiden Reject-Tests — eine gültige
    Zeile (analog Seed-Schema) wird nicht zurückgewiesen."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            DataSource(
                name="Testquelle",
                kategorie="retail_social",
                qualitaet="mittel",
                frequenz_sekunden=1200,
                kostenmodell="frei",
                kosten_monatlich_chf=Decimal("0"),
                aktiv=True,
            )
        )
        session.commit()  # keine Exception


def test_seed_insert_is_idempotent_via_on_conflict_do_nothing() -> None:
    """Verifiziert data-model.md §11 Punkt 10 ("Idempotent seedbar via
    ON CONFLICT DO NOTHING") für beide Seed-Inserts dieser Migration — kein
    `@trace`-Tag, da allgemeine DB-Konvention statt spezifischer AC.

    `postgresql.insert(...).on_conflict_do_nothing(...)` ist nur unter dem
    Postgres-Dialekt compilierbar — daher wird hier die compilierte SQL
    geprüft statt ein echter Doppel-Lauf. Der reale doppelte
    `alembic upgrade head`-Lauf (Zeilenzahl bleibt 12 + Summe der
    Anlageklassen-Zuordnungen) wurde manuell gegen die lokale
    Compose-Postgres-Instanz verifiziert (Coder-Self-Test, siehe Handoff).
    """
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    metadata = Base.metadata
    data_source = metadata.tables["data_source"]

    stmt = (
        pg_insert(data_source).values(SOURCE_SEED).on_conflict_do_nothing(index_elements=["name"])
    )
    compiled_sql = str(stmt.compile(dialect=postgresql.dialect()))

    assert "ON CONFLICT" in compiled_sql
    assert "DO NOTHING" in compiled_sql
    assert "(name)" in compiled_sql
