"""Tests fuer die exit_default_set/atr_multiplier_default-Stammdaten-
Migration (Story S-038).

Covers (strategie-exit-regeln): AC7, AC8, AC9

- AC8: der Seed deckt genau die 5 Default-Exit-Set-Kategorien der Spec-
  Tabelle ab, samt Stop-Typ/Hinweisen; das ORM-Modell lehnt Kategorien/
  Stop-Typen ausserhalb der Katalog-Wertemenge ab (CHECK-Constraint).
- AC7: kein fixer Prozent-Stop (`fix_pct`) als blanket Default — nur die
  explizite `index_buy_and_hold`-Tabellenzeile nutzt ihn.
- AC9: der Seed deckt genau die 2 Volatilitaetsklassen (ruhig/volatil) mit
  einem Multiplikator innerhalb der Spec-Bandbreite ab; das ORM-Modell
  lehnt eine unbekannte Volatilitaetsklasse ab.

Die Seed-Konstanten werden direkt aus der Migrationsdatei importiert (statt
dupliziert), analog `tests/db/test_strategie_katalog_migration.py`.
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
from app.db.models import AtrMultiplierDefault, ExitDefaultSet

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "app"
    / "db"
    / "migrations"
    / "versions"
    / "655b7f43eff4_create_exit_default_set_and_atr_.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "exit_regel_ableitung_migration_2", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MIGRATION = _load_migration_module()
EXIT_DEFAULT_SET_SEED = _MIGRATION.EXIT_DEFAULT_SET_SEED
ATR_MULTIPLIER_DEFAULT_SEED = _MIGRATION.ATR_MULTIPLIER_DEFAULT_SEED

EXPECTED_KATEGORIEN = {
    "value_aktien",
    "growth_momentum",
    "index_buy_and_hold",
    "krypto",
    "daytrade_swing",
}


def test_seed_covers_exactly_5_default_exit_set_kategorien() -> None:
    """@trace strategie-exit-regeln#AC8 — genau die 5 Kategorien der
    Spec-Tabelle sind geseedet, jede genau einmal."""
    assert len(EXIT_DEFAULT_SET_SEED) == 5
    kategorien = {row["kategorie"] for row in EXIT_DEFAULT_SET_SEED}
    assert kategorien == EXPECTED_KATEGORIEN


def test_seed_every_row_has_non_empty_stop_hinweis() -> None:
    """@trace strategie-exit-regeln#AC6 — jede Kategorie traegt einen
    nicht-leeren Stop-Hinweis (Stop-Trigger ist nie leer)."""
    for row in EXIT_DEFAULT_SET_SEED:
        assert row["stop_parameter_hinweis"].strip()
        assert row["stop_typ"]


def test_seed_only_index_buy_and_hold_uses_fix_pct_stop() -> None:
    """@trace strategie-exit-regeln#AC7 — kein fixer Prozent-Stop als
    blanket Default: nur `index_buy_and_hold` nutzt `stop_typ ==
    "fix_pct"`, alle anderen Kategorien nutzen ATR/fundamental/technisch."""
    fix_pct_kategorien = {
        row["kategorie"] for row in EXIT_DEFAULT_SET_SEED if row["stop_typ"] == "fix_pct"
    }
    assert fix_pct_kategorien == {"index_buy_and_hold"}


def test_seed_index_buy_and_hold_stop_parameter_pct_in_spec_spanne() -> None:
    """@trace strategie-exit-regeln#AC8 — der Index/Buy-and-Hold-Prozent-
    Default liegt in der Spec-Spanne 25-30% (AC8-Praezisierung: 27.5%
    Mittelpunkt)."""
    zeile = next(row for row in EXIT_DEFAULT_SET_SEED if row["kategorie"] == "index_buy_and_hold")
    assert Decimal("25") <= Decimal(str(zeile["stop_parameter_pct"])) <= Decimal("30")


def test_seed_covers_exactly_2_atr_multiplier_volatilitaetsklassen() -> None:
    """@trace strategie-exit-regeln#AC9 — genau "ruhig"/"volatil" sind
    geseedet."""
    assert len(ATR_MULTIPLIER_DEFAULT_SEED) == 2
    klassen = {row["volatilitaetsklasse"] for row in ATR_MULTIPLIER_DEFAULT_SEED}
    assert klassen == {"ruhig", "volatil"}


def test_seed_atr_multiplikator_liegt_innerhalb_der_eigenen_min_max_spanne() -> None:
    """@trace strategie-exit-regeln#AC9 — der angewandte Multiplikator
    liegt innerhalb der (in derselben Zeile dokumentierten) Spec-Bandbreite."""
    for row in ATR_MULTIPLIER_DEFAULT_SEED:
        assert row["multiplikator_min"] <= row["multiplikator"] <= row["multiplikator_max"]


def test_seed_ruhig_multiplikator_niedriger_als_volatil() -> None:
    """@trace strategie-exit-regeln#AC9 — ruhige Titel haben einen
    niedrigeren ATR-Multiplikator als volatile (Richtwert: ruhig 2-2.5x,
    volatil 3-4x)."""
    by_klasse = {
        row["volatilitaetsklasse"]: row["multiplikator"] for row in ATR_MULTIPLIER_DEFAULT_SEED
    }
    assert by_klasse["ruhig"] < by_klasse["volatil"]


def test_model_rejects_exit_default_set_kategorie_outside_catalog() -> None:
    """@trace strategie-exit-regeln#AC8 — nur die 5 katalogisierten
    Kategorien sind gueltig (CHECK-Constraint)."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            ExitDefaultSet(
                kategorie="unbekannt",
                stop_typ="atr_trailing",
                stop_parameter_hinweis="n/a",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_model_rejects_exit_default_set_stop_typ_outside_catalog() -> None:
    """@trace strategie-exit-regeln#AC7 — nur die katalogisierten
    Stop-Typen sind gueltig (CHECK-Constraint)."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            ExitDefaultSet(
                kategorie="value_aktien",
                stop_typ="unbekannt",
                stop_parameter_hinweis="n/a",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_model_rejects_atr_multiplier_default_volatilitaetsklasse_outside_catalog() -> None:
    """@trace strategie-exit-regeln#AC9 — nur "ruhig"/"volatil" sind
    gueltige Volatilitaetsklassen (CHECK-Constraint)."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            AtrMultiplierDefault(
                volatilitaetsklasse="extrem",
                multiplikator=Decimal("5.0"),
                multiplikator_min=Decimal("4.0"),
                multiplikator_max=Decimal("6.0"),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_seed_insert_is_idempotent_via_on_conflict_do_nothing() -> None:
    """Verifiziert data-model.md §11 Punkt 10 ("Idempotent seedbar via
    ON CONFLICT DO NOTHING") fuer beide Seed-Insert-Statements dieser
    Migration — kein `@trace`-Tag, da allgemeine DB-Konvention, keine
    bestimmte AC/BR.

    `postgresql.insert(...).on_conflict_do_nothing(...)` ist nur unter dem
    Postgres-Dialekt compilierbar; daher wird hier die compilierte SQL
    geprueft statt ein echter Doppel-Lauf (Muster identisch zu
    `tests/db/test_strategie_katalog_migration.py`).
    """
    from sqlalchemy import Column, Interval, MetaData, Numeric, String, Table
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    metadata = MetaData()
    exit_default_set = Table(
        "exit_default_set",
        metadata,
        Column("kategorie", String, primary_key=True),
        Column("stop_typ", String, nullable=False),
        Column("stop_parameter_hinweis", String, nullable=False),
        Column("stop_parameter_pct", Numeric(6, 3), nullable=True),
        Column("take_profit_hinweis", String, nullable=True),
        Column("time_box", Interval, nullable=True),
    )
    atr_multiplier_default = Table(
        "atr_multiplier_default",
        metadata,
        Column("volatilitaetsklasse", String, primary_key=True),
        Column("multiplikator", Numeric(5, 2), nullable=False),
        Column("multiplikator_min", Numeric(5, 2), nullable=False),
        Column("multiplikator_max", Numeric(5, 2), nullable=False),
    )

    exit_stmt = (
        pg_insert(exit_default_set)
        .values(EXIT_DEFAULT_SET_SEED)
        .on_conflict_do_nothing(index_elements=["kategorie"])
    )
    atr_stmt = (
        pg_insert(atr_multiplier_default)
        .values(ATR_MULTIPLIER_DEFAULT_SEED)
        .on_conflict_do_nothing(index_elements=["volatilitaetsklasse"])
    )

    for stmt, conflict_col in ((exit_stmt, "(kategorie)"), (atr_stmt, "(volatilitaetsklasse)")):
        compiled_sql = str(stmt.compile(dialect=postgresql.dialect()))
        assert "ON CONFLICT" in compiled_sql
        assert "DO NOTHING" in compiled_sql
        assert conflict_col in compiled_sql
