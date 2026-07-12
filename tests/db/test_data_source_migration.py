"""Tests fuer die data_source-/data_source_asset_class-Migration (Story S-006).

Covers (dateneingang): AC5, AC6, AC13
- AC5 (12 Quellen in 5 Kategorien, Anlageklassen-Zuordnung 1-11) wird
  strukturell gegen die Seed-Daten der Migration
  (`app/db/migrations/versions/ea80c97626ee_...py`) geprueft.
- AC6 (Reddit-Sentiment ausschliesslich fuer retail-getriebene Klassen 1/7,
  BR-123) wird gegen die konkrete Anlageklassen-Zuordnung der
  Reddit-Zeile geprueft (exakt {1, 7}, insbesondere NICHT 4/Obligationen
  oder 10/FX).
- AC13 (MVP nur Freiquellen aktiv) wird gegen das `aktiv`-Flag aller 12
  Zeilen geprueft: exakt die 5 in AC13 namentlich genannten Quellen (SEC
  Form 4, Reddit, Polymarket, FRED, Wirtschaftskalender) sind aktiv, die
  uebrigen 7 sind registriert, aber inaktiv.

Die Seed-Konstanten werden direkt aus der Migrationsdatei importiert (statt
dupliziert), damit ein kuenftiger Migrations-Edit ohne Test-Anpassung nicht
unbemerkt divergiert (Konvention aus `test_asset_class_migration.py` /
`test_category_weight_migration.py`).

Der reale doppelte `alembic upgrade head`-Lauf gegen eine lokale
Compose-Postgres-Instanz (Zeilenzahl bleibt 12 + 24, `alembic check`
meldet keinen Model-Drift) wurde manuell verifiziert (Coder-Self-Test,
siehe Handoff) — `postgresql.insert(...).on_conflict_do_nothing(...)` ist
nur unter dem Postgres-Dialekt compilierbar, nicht gegen SQLite ausfuehrbar.

Iteration 2 (Reviewer-Fix): `wirtschaftskalender-finnworlds` deckte
faelschlich auch Anlageklasse 8 (Rohstoffe) ab, obwohl
`docs/specs/dateneingang.md` § Nicht-Ziele Rohstoffe (8) explizit als "noch
offen und nicht Teil des MVP" ausschliesst — Zuordnung auf {3, 4, 10}
korrigiert, `test_no_source_is_mapped_to_the_out_of_scope_classes_6_or_8`
deckt das strukturell ab.
"""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import AssetClass, DataSource, DataSourceAssetClass

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "app"
    / "db"
    / "migrations"
    / "versions"
    / "ea80c97626ee_create_data_source_and_data_source_.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("data_source_migration", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MIGRATION = _load_migration_module()
SOURCE_SEED = _MIGRATION.DATA_SOURCE_SEED
ASSET_CLASS_IDS_BY_SLUG = _MIGRATION.DATA_SOURCE_ASSET_CLASS_IDS
SOURCE_ID = _MIGRATION._source_id

EXPECTED_CATEGORIES = {
    "equity_fundamentals",
    "retail_social",
    "blockchain_crypto",
    "etf_fonds",
    "makro_anleihen",
}

# AC13: exakt diese 5 Quellen (Slugs) sind im MVP aktiv.
EXPECTED_ACTIVE_SLUGS = {
    "sec-form4-insider-trades",
    "reddit-wallstreetbets-sentiment",
    "polymarket-prediction-markets",
    "fred-federal-reserve-economic-data",
    "wirtschaftskalender-finnworlds",
}


def test_seed_has_exactly_12_sources_in_5_categories() -> None:
    """@trace dateneingang#AC5 — Registry fuehrt genau 12 Quellen in genau
    den 5 spec-genannten Kategorien (Equity Insider & Fundamentals, Retail
    Sentiment & Social, Blockchain & Crypto, ETFs & Fonds, Makro & Anleihen)."""
    assert len(SOURCE_SEED) == 12
    assert len({row["name"] for row in SOURCE_SEED}) == 12
    categories = {row["kategorie"] for row in SOURCE_SEED}
    assert categories == EXPECTED_CATEGORIES


def test_seed_every_source_maps_to_at_least_one_asset_class_1_to_11() -> None:
    """@trace dateneingang#AC5 — jeder Quelle sind eine oder mehrere
    Anlageklassen (1-11) zugeordnet, fuer die sie verwertbare Signale liefert."""
    slugs = {row["slug"] for row in SOURCE_SEED}
    assert set(ASSET_CLASS_IDS_BY_SLUG.keys()) == slugs
    for slug, asset_class_ids in ASSET_CLASS_IDS_BY_SLUG.items():
        assert len(asset_class_ids) >= 1, slug
        for asset_class_id in asset_class_ids:
            assert 1 <= asset_class_id <= 11, f"{slug}: {asset_class_id} ausserhalb 1-11"


def test_no_source_is_mapped_to_the_out_of_scope_classes_6_or_8() -> None:
    """@trace dateneingang#AC5 — die Spec-Nicht-Ziele schliessen Immobilien
    (6) und Rohstoffe (8) explizit als "noch offen und nicht Teil des MVP"
    aus; die Seed-Daten duerfen diese vertagte Scope-Entscheidung nicht
    stillschweigend vorwegnehmen (Reviewer-Fund Iteration 1, u.a. betraf
    `wirtschaftskalender-finnworlds` faelschlich Klasse 8)."""
    all_mapped_classes = {
        asset_class_id
        for asset_class_ids in ASSET_CLASS_IDS_BY_SLUG.values()
        for asset_class_id in asset_class_ids
    }
    assert 6 not in all_mapped_classes
    assert 8 not in all_mapped_classes


def test_reddit_is_restricted_to_retail_driven_classes_aktien_and_krypto() -> None:
    """@trace dateneingang#AC6 — Reddit-Sentiment ist ausschliesslich den
    retail-getriebenen Klassen Aktien (1) und Krypto (7) zugeordnet;
    Obligationen (4) und FX (10) sind explizit NICHT dabei."""
    reddit_classes = set(ASSET_CLASS_IDS_BY_SLUG["reddit-wallstreetbets-sentiment"])
    assert reddit_classes == {1, 7}
    assert 4 not in reddit_classes
    assert 10 not in reddit_classes


def test_only_the_5_mvp_free_sources_are_active() -> None:
    """@trace dateneingang#AC13 — im MVP sind nur die 5 kostenlosen Quellen
    (SEC Form 4, Reddit, Polymarket, FRED, Wirtschaftskalender) aktiv;
    kostenpflichtige/institutionelle Quellen sind registriert, aber
    `aktiv=False`."""
    active_slugs = {row["slug"] for row in SOURCE_SEED if row["aktiv"]}
    assert active_slugs == EXPECTED_ACTIVE_SLUGS
    inactive_slugs = {row["slug"] for row in SOURCE_SEED if not row["aktiv"]}
    assert inactive_slugs == {row["slug"] for row in SOURCE_SEED} - EXPECTED_ACTIVE_SLUGS
    assert len(inactive_slugs) == 7


def test_model_rejects_invalid_kategorie() -> None:
    """@trace dateneingang#AC5 — nur die 5 registrierten Kategorien sind
    gueltig (CHECK-Constraint), keine freie Zusatz-Kategorie."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            DataSource(
                id=uuid.uuid4(),
                name="Ungueltige Quelle",
                kategorie="unbekannte_kategorie",
                frequenz_sekunden=3600,
                aktiv=False,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_model_rejects_frequenz_outside_30_to_86400_seconds() -> None:
    """@trace dateneingang#AC5 — Abrufintervall ausserhalb des zulaessigen
    Bereichs (30 s - 86400 s, data-model.md) wird als ungueltig zurueckgewiesen."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            DataSource(
                id=uuid.uuid4(),
                name="Zu haeufige Quelle",
                kategorie="makro_anleihen",
                frequenz_sekunden=5,
                aktiv=False,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_data_source_asset_class_has_index_on_asset_class_id() -> None:
    """@trace dateneingang#AC5 — data-model.md §8 verlangt fuer
    `data_source_asset_class` einen `(asset_class_id)`-Index ("Quellen je
    Klasse", Datenquellen-Abfrage-Matching); der Composite-PK
    (data_source_id, asset_class_id) deckt einen reinen
    asset_class_id-Filter allein nicht ab (DBA-Review-Fund Iteration 2)."""
    index_names_by_columns = {
        tuple(col.name for col in index.columns): index.name
        for index in DataSourceAssetClass.__table__.indexes
    }
    assert ("asset_class_id",) in index_names_by_columns
    assert (
        index_names_by_columns[("asset_class_id",)] == "ix_data_source_asset_class_asset_class_id"
    )


def test_data_source_asset_class_mapping_persists_via_orm() -> None:
    """@trace dateneingang#AC5 — die M:N-Zuordnung Quelle <-> Anlageklasse
    ist ueber das ORM-Modell abfragbar (Grundlage der spaeteren
    Datenquellen-Abfrage, AC7/AC8 ausserhalb dieser Story)."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True, retail_driven=True)
        )
        source_id = uuid.uuid4()
        session.add(
            DataSource(
                id=source_id,
                name="Test-Quelle",
                kategorie="equity_fundamentals",
                frequenz_sekunden=7200,
                aktiv=True,
            )
        )
        session.commit()
        session.add(DataSourceAssetClass(data_source_id=source_id, asset_class_id=1))
        session.commit()

        mapping = session.get(DataSourceAssetClass, (source_id, 1))
        assert mapping is not None
        assert mapping.asset_class_id == 1


def test_seed_insert_is_idempotent_via_on_conflict_do_nothing() -> None:
    """Verifiziert data-model.md §11 Punkt 10 ("Idempotent seedbar via
    ON CONFLICT DO NOTHING") fuer beide Seed-Inserts dieser Migration —
    kein `@trace`-Tag, da allgemeine DB-Konvention statt spezifischer AC.

    `postgresql.insert(...).on_conflict_do_nothing(...)` ist nur unter dem
    Postgres-Dialekt compilierbar, daher wird hier die compilierte SQL
    geprueft statt ein echter Doppel-Lauf (der reale doppelte
    `alembic upgrade head`-Lauf wurde manuell verifiziert, siehe
    Modul-Docstring)."""
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    metadata = Base.metadata
    data_source = metadata.tables["data_source"]
    data_source_asset_class = metadata.tables["data_source_asset_class"]

    seed_rows = [{**row, "id": SOURCE_ID(row["slug"])} for row in SOURCE_SEED]
    for row in seed_rows:
        row.pop("slug")

    source_stmt = (
        pg_insert(data_source).values(seed_rows).on_conflict_do_nothing(index_elements=["id"])
    )
    mapping_rows = [
        {"data_source_id": SOURCE_ID(slug), "asset_class_id": asset_class_id}
        for slug, asset_class_ids in ASSET_CLASS_IDS_BY_SLUG.items()
        for asset_class_id in asset_class_ids
    ]
    mapping_stmt = (
        pg_insert(data_source_asset_class)
        .values(mapping_rows)
        .on_conflict_do_nothing(index_elements=["data_source_id", "asset_class_id"])
    )

    source_sql = str(source_stmt.compile(dialect=postgresql.dialect()))
    mapping_sql = str(mapping_stmt.compile(dialect=postgresql.dialect()))

    assert "ON CONFLICT" in source_sql and "DO NOTHING" in source_sql and "(id)" in source_sql
    assert "ON CONFLICT" in mapping_sql and "DO NOTHING" in mapping_sql
    assert "(data_source_id, asset_class_id)" in mapping_sql
