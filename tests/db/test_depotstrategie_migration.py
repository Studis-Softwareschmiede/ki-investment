"""Tests fuer die risk_profile/portfolio_strategy/portfolio_class_limit-
Migration (Story S-043).

Covers (risikomanagement): AC1, AC3, AC4

- AC1 (Grenzwert-Regelwerk: max. Gewicht je Branche/Sektor [GICS], max.
  Gewicht je Anlageklasse, max. Einzelposition, Cash-Quote) wird
  strukturell gegen die ORM-Modelle (`app.db.models.RiskProfile`/
  `PortfolioStrategy`/`PortfolioClassLimit`, 1:1 aus der Migration
  `c7e21f4a9d63_create_risk_profile_portfolio_strategy_.py`) geprueft:
  Spalten, CHECK-Constraints (0-100 %-Bereich je Prozent-Feld), FK auf
  `risk_profile`/`asset_class`, Composite-PK auf `portfolio_class_limit`.
- AC3 (3 Risikoprofile als Presets) wird gegen die Seed-Daten geprueft:
  genau 3 `risk_profile`-Zeilen (konservativ/ausgewogen/offensiv), genau
  eine `portfolio_strategy`-Preset-Zeile je Profil, alle initial
  `aktiv=False` (Preset-Wahl ist Nutzer-Entscheidung, keine
  Migrations-Vorwegnahme).
- AC4 (provisorische, konfigurierbare Preset-Defaults) wird gegen die
  konkreten Seed-Werte geprueft: Einzelposition 2 % (konservativ) / 10 %
  (offensiv), Sektor/Branche 20 % (alle Profile), Krypto 5-15 %
  (profilabhaengig), Cash-Quote 5 % (alle Profile).

Die Seed-Konstanten werden direkt aus der Migrationsdatei importiert (statt
dupliziert), damit ein kuenftiger Migrations-Edit ohne Test-Anpassung nicht
unbemerkt divergiert (Muster identisch zu
`tests/db/test_strategie_katalog_migration.py`).

Der partielle UNIQUE-Index `ux_portfolio_strategy_aktiv` (BR-117, "genau
eine aktive Depotstrategie") ist — analog `ux_category_weight_version_
current`/`ux_analysis_method_version_current` — nur unter echtem Postgres
compilierbar (kein SQLite-Aequivalent im ORM-Modell, siehe
`app.db.models.PortfolioStrategy`-Docstring); die App-seitige Durchsetzung
(`app.db.depotstrategie._deaktiviere_aktive_strategie`) ist in
`tests/db/test_depotstrategie.py` abgedeckt.
"""

from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import AssetClass, PortfolioClassLimit, PortfolioStrategy, RiskProfile

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "app"
    / "db"
    / "migrations"
    / "versions"
    / "c7e21f4a9d63_create_risk_profile_portfolio_strategy_.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("depotstrategie_migration", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MIGRATION = _load_migration_module()
RISK_PROFILE_SEED = _MIGRATION.RISK_PROFILE_SEED
PORTFOLIO_STRATEGY_SEED = _MIGRATION.PORTFOLIO_STRATEGY_SEED
PORTFOLIO_CLASS_LIMIT_SEED = _MIGRATION.PORTFOLIO_CLASS_LIMIT_SEED
KRYPTO_ASSET_CLASS_ID = _MIGRATION._KRYPTO_ASSET_CLASS_ID


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


def _seed_asset_classes(session: Session) -> None:
    session.add(
        AssetClass(
            id=KRYPTO_ASSET_CLASS_ID,
            name="Kryptowährungen",
            prio_stufe="Stufe3",
            aktiv=True,
            retail_driven=True,
        )
    )
    session.commit()


# --- AC3: 3 Risikoprofile als Presets ---------------------------------


def test_seed_covers_exactly_3_risk_profiles() -> None:
    """@trace risikomanagement#AC3 — genau 3 Risikoprofile
    (konservativ/ausgewogen/offensiv)."""
    names = {row["name"] for row in RISK_PROFILE_SEED}
    assert names == {"konservativ", "ausgewogen", "offensiv"}
    assert len(RISK_PROFILE_SEED) == 3


def test_seed_covers_exactly_one_portfolio_strategy_preset_per_profile() -> None:
    """@trace risikomanagement#AC3 — jedes Risikoprofil hat genau EINE
    Preset-Zeile in `portfolio_strategy`."""
    profile_ids = {row["id"] for row in RISK_PROFILE_SEED}
    strategy_profile_ids = [row["risk_profile_id"] for row in PORTFOLIO_STRATEGY_SEED]
    assert set(strategy_profile_ids) == profile_ids
    assert len(strategy_profile_ids) == len(set(strategy_profile_ids)) == 3


def test_seed_no_preset_is_active_by_default() -> None:
    """@trace risikomanagement#AC3 — welches Preset aktiv ist, ist eine
    Nutzer-Entscheidung (AC3 "der Nutzer kann ein Preset wählen"); die
    Migration nimmt das nicht vorweg."""
    assert all(row["aktiv"] is False for row in PORTFOLIO_STRATEGY_SEED)


# --- AC4: provisorische, konfigurierbare Preset-Defaults ---------------


def _strategy_row_for_profile(profile_name: str) -> dict:
    profile_id = next(row["id"] for row in RISK_PROFILE_SEED if row["name"] == profile_name)
    return next(row for row in PORTFOLIO_STRATEGY_SEED if row["risk_profile_id"] == profile_id)


def test_seed_einzelposition_range_matches_ac4_2_to_10_percent() -> None:
    """@trace risikomanagement#AC4 — Einzelposition zwischen 2 %
    (konservativ) und bis 10 % (offensiv)."""
    assert _strategy_row_for_profile("konservativ")["max_einzelposition_pct"] == 2
    assert _strategy_row_for_profile("offensiv")["max_einzelposition_pct"] == 10


def test_seed_sektor_limit_is_20_percent_for_every_profile() -> None:
    """@trace risikomanagement#AC4 — Sektor/Branche max 20 % (kein
    Profil-Unterschied laut Spec-Wortlaut)."""
    for row in PORTFOLIO_STRATEGY_SEED:
        assert row["max_sektor_pct"] == 20


def test_seed_cash_quote_is_5_percent_for_every_profile() -> None:
    """@trace risikomanagement#AC4 — Cash-Quote ~5 % (kein Profil-
    Unterschied laut Spec-Wortlaut)."""
    for row in PORTFOLIO_STRATEGY_SEED:
        assert row["cash_quote_ziel_pct"] == 5


def test_seed_krypto_klassenlimit_range_matches_ac4_5_to_15_percent() -> None:
    """@trace risikomanagement#AC4 — Anlageklasse Krypto 5-15 %
    (profilabhängig)."""
    konservativ_id = _strategy_row_for_profile("konservativ")["id"]
    offensiv_id = _strategy_row_for_profile("offensiv")["id"]

    konservativ_limit = next(
        row for row in PORTFOLIO_CLASS_LIMIT_SEED if row["portfolio_strategy_id"] == konservativ_id
    )
    offensiv_limit = next(
        row for row in PORTFOLIO_CLASS_LIMIT_SEED if row["portfolio_strategy_id"] == offensiv_id
    )

    assert konservativ_limit["asset_class_id"] == KRYPTO_ASSET_CLASS_ID
    assert konservativ_limit["max_klasse_pct"] == 5
    assert offensiv_limit["asset_class_id"] == KRYPTO_ASSET_CLASS_ID
    assert offensiv_limit["max_klasse_pct"] == 15


def test_seed_class_limits_only_seed_krypto_no_other_asset_class() -> None:
    """@trace risikomanagement#AC4 — nur Krypto ist mit einem konkreten,
    spec-genannten Prozentbereich geseedet; keine unbelegten Werte für die
    übrigen 10 Anlageklassen (siehe Migrations-Docstring)."""
    assert len(PORTFOLIO_CLASS_LIMIT_SEED) == 3
    assert all(row["asset_class_id"] == KRYPTO_ASSET_CLASS_ID for row in PORTFOLIO_CLASS_LIMIT_SEED)


# --- AC1: Schema-Struktur (CHECK/FK/PK) ---------------------------------


def test_model_rejects_unknown_risk_profile_name() -> None:
    """@trace risikomanagement#AC3 — nur die 3 katalogisierten Profile
    (CHECK-Constraint)."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(RiskProfile(name="unbekannt"))
        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize(
    "feld,wert",
    [
        ("max_einzelposition_pct", Decimal("-1")),
        ("max_einzelposition_pct", Decimal("101")),
        ("max_sektor_pct", Decimal("-1")),
        ("max_sektor_pct", Decimal("101")),
        ("cash_quote_ziel_pct", Decimal("-1")),
        ("cash_quote_ziel_pct", Decimal("101")),
        ("gesamt_exposure_cap_pct", Decimal("-1")),
        ("gesamt_exposure_cap_pct", Decimal("101")),
    ],
)
def test_model_rejects_portfolio_strategy_percent_field_outside_0_100(
    feld: str, wert: Decimal
) -> None:
    """@trace risikomanagement#AC1 — jedes Prozent-Feld der Depotstrategie
    ist per CHECK-Constraint auf 0-100 % begrenzt."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(RiskProfile(name="konservativ"))
        session.commit()
        profil = session.execute(RiskProfile.__table__.select()).first()

        werte = {
            "risk_profile_id": profil.id,
            "max_einzelposition_pct": Decimal("2"),
            "max_sektor_pct": Decimal("20"),
            "cash_quote_ziel_pct": Decimal("5"),
            "gesamt_exposure_cap_pct": Decimal("20"),
        }
        werte[feld] = wert
        session.add(PortfolioStrategy(**werte))
        with pytest.raises(IntegrityError):
            session.commit()


def test_model_rejects_portfolio_class_limit_max_klasse_pct_outside_0_100() -> None:
    """@trace risikomanagement#AC1 — `max_klasse_pct` ist per
    CHECK-Constraint auf 0-100 % begrenzt."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_asset_classes(session)
        session.add(RiskProfile(name="konservativ"))
        session.commit()
        profil = session.execute(RiskProfile.__table__.select()).first()
        strategie = PortfolioStrategy(
            risk_profile_id=profil.id,
            max_einzelposition_pct=Decimal("2"),
            max_sektor_pct=Decimal("20"),
            cash_quote_ziel_pct=Decimal("5"),
            gesamt_exposure_cap_pct=Decimal("20"),
        )
        session.add(strategie)
        session.commit()

        session.add(
            PortfolioClassLimit(
                portfolio_strategy_id=strategie.id,
                asset_class_id=KRYPTO_ASSET_CLASS_ID,
                max_klasse_pct=Decimal("101"),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_model_rejects_portfolio_strategy_with_unknown_risk_profile_fk() -> None:
    """@trace risikomanagement#AC1 — `portfolio_strategy.risk_profile_id`
    ist ein FK auf `risk_profile.id`."""
    import uuid

    engine = _sqlite_engine_with_fk()
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            PortfolioStrategy(
                risk_profile_id=uuid.uuid4(),
                max_einzelposition_pct=Decimal("2"),
                max_sektor_pct=Decimal("20"),
                cash_quote_ziel_pct=Decimal("5"),
                gesamt_exposure_cap_pct=Decimal("20"),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_portfolio_class_limit_composite_pk_persists_via_orm() -> None:
    """@trace risikomanagement#AC1 — der Composite-PK `(portfolio_strategy_id,
    asset_class_id)` ist über die ORM abfragbar."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_asset_classes(session)
        session.add(RiskProfile(name="konservativ"))
        session.commit()
        profil = session.execute(RiskProfile.__table__.select()).first()
        strategie = PortfolioStrategy(
            risk_profile_id=profil.id,
            max_einzelposition_pct=Decimal("2"),
            max_sektor_pct=Decimal("20"),
            cash_quote_ziel_pct=Decimal("5"),
            gesamt_exposure_cap_pct=Decimal("20"),
        )
        session.add(strategie)
        session.commit()

        session.add(
            PortfolioClassLimit(
                portfolio_strategy_id=strategie.id,
                asset_class_id=KRYPTO_ASSET_CLASS_ID,
                max_klasse_pct=Decimal("5"),
            )
        )
        session.commit()

        gefunden = session.get(PortfolioClassLimit, (strategie.id, KRYPTO_ASSET_CLASS_ID))
        assert gefunden is not None
        assert gefunden.max_klasse_pct == Decimal("5")


def test_portfolio_strategy_aktiv_defaults_to_false() -> None:
    """@trace risikomanagement#AC3 — `aktiv` ist per Default `false`
    (data-model.md §1) — muss explizit gesetzt werden, um eine
    Depotstrategie zu aktivieren."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(RiskProfile(name="konservativ"))
        session.commit()
        profil = session.execute(RiskProfile.__table__.select()).first()
        strategie = PortfolioStrategy(
            risk_profile_id=profil.id,
            max_einzelposition_pct=Decimal("2"),
            max_sektor_pct=Decimal("20"),
            cash_quote_ziel_pct=Decimal("5"),
            gesamt_exposure_cap_pct=Decimal("20"),
        )
        session.add(strategie)
        session.commit()
        assert strategie.aktiv is False


def test_portfolio_class_limit_has_no_dedicated_asset_class_id_index() -> None:
    """@trace risikomanagement#AC1 — data-model.md §8 nimmt
    `portfolio_class_limit` explizit von der "Index auf jede FK-Spalte"-
    Regel aus (geringe Kardinalität, sql/R05-Ausnahme); der Composite-PK
    bleibt der einzige Index."""
    index_columns = [
        tuple(col.name for col in idx.columns) for idx in PortfolioClassLimit.__table__.indexes
    ]
    assert ("asset_class_id",) not in index_columns


def test_seed_insert_is_idempotent_via_on_conflict_do_nothing() -> None:
    """Verifiziert data-model.md §11 Punkt 10 ("Idempotent seedbar via
    ON CONFLICT DO NOTHING") fuer die drei Seed-Insert-Statements dieser
    Migration — kein `@trace`-Tag, da allgemeine DB-Konvention, keine
    bestimmte AC/BR.

    `postgresql.insert(...).on_conflict_do_nothing(...)` ist nur unter dem
    Postgres-Dialekt compilierbar; daher wird hier die compilierte SQL
    geprueft statt ein echter Doppel-Lauf (Muster identisch zu
    `tests/db/test_strategie_katalog_migration.py`).
    """
    from sqlalchemy import Column, MetaData, Numeric, SmallInteger, String, Table
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.dialects.postgresql import UUID as PGUUID
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    metadata = MetaData()
    risk_profile = Table(
        "risk_profile",
        metadata,
        Column("id", PGUUID(as_uuid=True), primary_key=True),
        Column("name", String, nullable=False, unique=True),
    )
    portfolio_strategy = Table(
        "portfolio_strategy",
        metadata,
        Column("id", PGUUID(as_uuid=True), primary_key=True),
        Column("risk_profile_id", PGUUID(as_uuid=True), nullable=False),
        Column("max_einzelposition_pct", Numeric(6, 3), nullable=False),
        Column("max_sektor_pct", Numeric(6, 3), nullable=False),
        Column("cash_quote_ziel_pct", Numeric(6, 3), nullable=False),
        Column("gesamt_exposure_cap_pct", Numeric(6, 3), nullable=False),
    )
    portfolio_class_limit = Table(
        "portfolio_class_limit",
        metadata,
        Column("portfolio_strategy_id", PGUUID(as_uuid=True), primary_key=True),
        Column("asset_class_id", SmallInteger, primary_key=True),
        Column("max_klasse_pct", Numeric(6, 3), nullable=False),
    )

    risk_profile_stmt = (
        pg_insert(risk_profile)
        .values([{"id": row["id"], "name": row["name"]} for row in RISK_PROFILE_SEED])
        .on_conflict_do_nothing(index_elements=["id"])
    )
    strategy_stmt = (
        pg_insert(portfolio_strategy)
        .values([{k: v for k, v in row.items() if k != "aktiv"} for row in PORTFOLIO_STRATEGY_SEED])
        .on_conflict_do_nothing(index_elements=["id"])
    )
    class_limit_stmt = (
        pg_insert(portfolio_class_limit)
        .values(PORTFOLIO_CLASS_LIMIT_SEED)
        .on_conflict_do_nothing(index_elements=["portfolio_strategy_id", "asset_class_id"])
    )

    for stmt, conflict_col in (
        (risk_profile_stmt, "(id)"),
        (strategy_stmt, "(id)"),
        (class_limit_stmt, "(portfolio_strategy_id, asset_class_id)"),
    ):
        compiled_sql = str(stmt.compile(dialect=postgresql.dialect()))
        assert "ON CONFLICT" in compiled_sql
        assert "DO NOTHING" in compiled_sql
        assert conflict_col in compiled_sql
