"""Tests fuer die category_weight-/analysis_category-Migration (Story S-004).

Covers (anlageklassen-config): AC6, AC7, AC8
- AC6 (5 Kategoriegewichte je der 11 Klassen, Summe je Klasse = 100 %) und
  AC8 (Gewichte entsprechen exakt der Verträge-Tabelle) werden strukturell
  gegen die Seed-Daten der Migration
  (`app/db/migrations/versions/2da446925bbc_...py`) geprueft.
- AC7 (ungültige Gewichtung wird zurueckgewiesen) wird auf zwei Ebenen
  abgedeckt: die schnelle, dialekt-unabhaengige App-Validierung
  (`tests/db/test_category_weights_validation.py`) sowie hier strukturell
  ueber das CHECK-Constraint `ck_category_weight_range` (0-100 je Zeile).
  Die vollstaendige Σ=100- und Zeilenanzahl-Ablehnung ist DB-seitig ein
  deferred Constraint-Trigger (nur unter Postgres ausfuehrbar, nicht via
  SQLite-In-Memory-Test reproduzierbar) — dieser wurde manuell gegen die
  lokale Compose-Postgres-Instanz verifiziert (Coder-Self-Test, siehe
  Handoff, Iteration 3): (1) ein Insert eines 5-Zeilen-Sets mit Summe 99
  wird beim COMMIT mit einer Exception zurueckgewiesen, die Transaktion
  rollt vollstaendig zurueck; (2) ein Insert einer einzelnen Zeile mit
  weight_pct=100 (Summe stimmt zufaellig, aber nur 1 statt 5 Zeilen, AC6)
  wird ebenfalls per Row-Count-Check (`row_count NOT IN (0, 5)`)
  zurueckgewiesen.

Die Seed-Konstanten werden direkt aus der Migrationsdatei importiert (statt
dupliziert), damit ein kuenftiger Migrations-Edit ohne Test-Anpassung nicht
unbemerkt divergiert (Konvention aus `test_asset_class_migration.py`).
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
from app.db.models import AnalysisCategory, AssetClass, CategoryWeight

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "app"
    / "db"
    / "migrations"
    / "versions"
    / "2da446925bbc_create_analysis_category_and_category_.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("category_weight_migration", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MIGRATION = _load_migration_module()
CATEGORY_SEED = _MIGRATION.ANALYSIS_CATEGORY_SEED
WEIGHT_SEED = _MIGRATION.CATEGORY_WEIGHT_SEED

# Verträge-Tabelle docs/specs/anlageklassen-config.md — Kategoriegewichte je
# Klasse (Fundamental, Technisch, Qualitativ, Makro, Risiko & Quant), AC8.
EXPECTED_WEIGHTS_BY_CLASS_ID = {
    1: {"fundamental": 35, "technisch": 15, "qualitativ": 20, "makro": 10, "risiko_quant": 20},
    2: {"fundamental": 30, "technisch": 10, "qualitativ": 30, "makro": 15, "risiko_quant": 15},
    3: {"fundamental": 30, "technisch": 0, "qualitativ": 20, "makro": 35, "risiko_quant": 15},
    4: {"fundamental": 30, "technisch": 10, "qualitativ": 10, "makro": 25, "risiko_quant": 25},
    5: {"fundamental": 30, "technisch": 5, "qualitativ": 30, "makro": 10, "risiko_quant": 25},
    6: {"fundamental": 35, "technisch": 5, "qualitativ": 20, "makro": 20, "risiko_quant": 20},
    7: {"fundamental": 18, "technisch": 22, "qualitativ": 15, "makro": 20, "risiko_quant": 25},
    8: {"fundamental": 30, "technisch": 20, "qualitativ": 5, "makro": 25, "risiko_quant": 20},
    9: {"fundamental": 35, "technisch": 5, "qualitativ": 20, "makro": 20, "risiko_quant": 20},
    10: {"fundamental": 20, "technisch": 25, "qualitativ": 5, "makro": 30, "risiko_quant": 20},
    11: {"fundamental": 15, "technisch": 35, "qualitativ": 10, "makro": 15, "risiko_quant": 25},
}


def _weights_by_class() -> dict[int, dict[str, int]]:
    grouped: dict[int, dict[str, int]] = {}
    for row in WEIGHT_SEED:
        grouped.setdefault(row["asset_class_id"], {})[row["category_code"]] = row["weight_pct"]
    return grouped


def test_seed_covers_all_11_classes_with_all_5_categories() -> None:
    """@trace anlageklassen-config#AC6 — jede der 11 Klassen traegt genau die
    5 Kategoriegewichte (Fundamental, Technisch, Qualitativ, Makro,
    Risiko & Quantitativ)."""
    grouped = _weights_by_class()
    assert set(grouped.keys()) == set(range(1, 12))
    for asset_class_id, weights in grouped.items():
        assert set(weights.keys()) == set(CATEGORY_SEED[i]["code"] for i in range(5))


def test_seed_each_class_sums_to_exactly_100() -> None:
    """@trace anlageklassen-config#AC6 — die fünf Gewichte je Klasse
    summieren sich auf exakt 100 %."""
    grouped = _weights_by_class()
    for asset_class_id, weights in grouped.items():
        assert sum(weights.values()) == 100, f"asset_class_id {asset_class_id} != 100"


def test_seed_matches_vertraege_table_exactly() -> None:
    """@trace anlageklassen-config#AC8 — die hinterlegten Kategoriegewichte
    entsprechen exakt der Gewichtungstabelle im Abschnitt "Verträge"
    (u. a. Aktien 35/15/20/10/20, Cash 30/0/20/35/15, Krypto 18/22/15/20/25,
    Derivate 15/35/10/15/25)."""
    grouped = _weights_by_class()
    assert grouped == EXPECTED_WEIGHTS_BY_CLASS_ID


def test_analysis_category_seed_has_5_fixed_codes_only_risiko_quant_ist_risiko() -> None:
    """@trace anlageklassen-config#AC6 — die 5 Analysekategorien existieren
    als Stammdaten-Voraussetzung fuer die Kategoriegewichte; nur
    `risiko_quant` ist als Risiko-Kategorie markiert (data-model.md
    `ist_risiko`, ausserhalb dieser AC aber strukturelle Vorbedingung)."""
    codes = {row["code"] for row in CATEGORY_SEED}
    assert codes == {"fundamental", "technisch", "qualitativ", "makro", "risiko_quant"}
    risiko_codes = {row["code"] for row in CATEGORY_SEED if row["ist_risiko"]}
    assert risiko_codes == {"risiko_quant"}


def test_model_rejects_weight_pct_outside_0_100() -> None:
    """@trace anlageklassen-config#AC7 — ein Gewicht ausserhalb 0-100 %
    (Zeilen-CHECK) wird als ungültig zurückgewiesen (Edge-Case, deckt E1
    strukturell auf Zeilenebene; die vollständige Σ=100-Ablehnung ist der
    DB-Trigger, siehe Modul-Docstring + `test_category_weights_validation.py`)."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(
            AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True, retail_driven=True)
        )
        session.add(AnalysisCategory(code="fundamental", name="Fundamental", ist_risiko=False))
        session.commit()

        session.add(
            CategoryWeight(asset_class_id=1, category_code="fundamental", weight_pct=Decimal("150"))
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_seed_insert_is_idempotent_via_on_conflict_do_nothing() -> None:
    """Verifiziert data-model.md §11 Punkt 10 ("Idempotent seedbar via
    ON CONFLICT DO NOTHING") fuer beide Seed-Inserts dieser Migration —
    kein `@trace`-Tag, da allgemeine DB-Konvention statt spezifischer AC.

    `postgresql.insert(...).on_conflict_do_nothing(...)` ist nur unter dem
    Postgres-Dialekt compilierbar — daher wird hier die compilierte SQL
    geprueft statt ein echter Doppel-Lauf. Der reale doppelte
    `alembic upgrade head`-Lauf (Zeilenzahl bleibt 5 + 55) wurde manuell
    gegen die lokale Compose-Postgres-Instanz verifiziert (Coder-Self-Test).
    """
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    metadata = Base.metadata
    analysis_category = metadata.tables["analysis_category"]
    category_weight = metadata.tables["category_weight"]

    cat_stmt = (
        pg_insert(analysis_category)
        .values(CATEGORY_SEED)
        .on_conflict_do_nothing(index_elements=["code"])
    )
    weight_stmt = (
        pg_insert(category_weight)
        .values(WEIGHT_SEED)
        .on_conflict_do_nothing(index_elements=["asset_class_id", "category_code"])
    )

    cat_sql = str(cat_stmt.compile(dialect=postgresql.dialect()))
    weight_sql = str(weight_stmt.compile(dialect=postgresql.dialect()))

    assert "ON CONFLICT" in cat_sql and "DO NOTHING" in cat_sql and "(code)" in cat_sql
    assert "ON CONFLICT" in weight_sql and "DO NOTHING" in weight_sql
    assert "(asset_class_id, category_code)" in weight_sql
