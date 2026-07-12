"""create analysis_category and category_weight tables with seed and sum100 trigger

Covers (anlageklassen-config): AC6, AC7, AC8

Quelle: docs/data-model.md §1 `analysis_category` + `category_weight` (BR-101),
Verträge-Tabelle "Kategoriegewichte" in docs/specs/anlageklassen-config.md.

`analysis_category` ist in data-model.md §11 (Migrations-Reihenfolge) Teil der
Stammdaten-Basis (Schritt 1) und eine harte FK-Voraussetzung für
`category_weight` (Schritt 2) — ohne die 5 Kategorie-Codes kann kein
Kategoriegewicht referenziert werden (AC6 nennt die 5 Kategorien explizit:
Fundamental, Technisch, Qualitativ, Makro, Risiko & Quantitativ). Da keine
andere Story `analysis_category` anlegt, wird sie hier als Voraussetzung für
AC6-8 mitgezogen (keine eigenständige AC, keine Methodentabellen — die bleiben
S-018).

`config_version` auf `category_weight`: reine Tag-Spalte, **NICHT** Teil des
PK und **NICHT** ausreichend, um AC10 zu erfüllen — ein künftiges Hochzählen
per UPDATE überschreibt die Vorgänger-Gewichte in derselben Zeile, es entsteht
keine Historie. Für AC10 fehlt noch (Folge-Story) entweder eine separate
Historien-/Snapshot-Tabelle je Version, oder `config_version` als Teil eines
erweiterten PK mit append-only-Zeilen + „aktuell gültig"-Zeiger, plus eine
Referenz von `analysis_result` auf die genutzte Version (siehe
docs/data-model.md §1 `category_weight`-Notiz).

BR-101 (Σ weight_pct je asset_class = 100, ±0.01) wird zweischichtig
durchgesetzt (data-model.md §10 "App-Validierung + DB-Trigger/Deferred-Check"):
- DB: eine DEFERRABLE INITIALLY DEFERRED CONSTRAINT TRIGGER prüft am
  Transaktionsende sowohl die Zeilenanzahl (genau 5 oder 0 je Klasse, AC6)
  als auch die Summe je betroffener asset_class_id (AC7 — eine ungültige
  Gewichtung wird zurückgewiesen, die gesamte Transaktion rollt zurück,
  nichts wird wirksam).
- App: `app/db/category_weights.py::validate_category_weights` (schnelle,
  dialekt-unabhängige Vorab-Prüfung für künftige Config-Schreibpfade).

Revision ID: 2da446925bbc
Revises: b2bd709be080
Create Date: 2026-07-12 13:50:01.771234

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import insert as pg_insert

# revision identifiers, used by Alembic.
revision: str = "2da446925bbc"
down_revision: Union[str, Sequence[str], None] = "b2bd709be080"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 5 Analysekategorien (C-007, data-model.md `analysis_category`). Nur
# `risiko_quant` ist ist_risiko=true (Basis Sanity-Cap BR-106, ausserhalb
# dieser Story).
ANALYSIS_CATEGORY_SEED = [
    {"code": "fundamental", "name": "Fundamental", "ist_risiko": False},
    {"code": "technisch", "name": "Technisch", "ist_risiko": False},
    {"code": "qualitativ", "name": "Qualitativ", "ist_risiko": False},
    {"code": "makro", "name": "Makro", "ist_risiko": False},
    {"code": "risiko_quant", "name": "Risiko & Quantitativ", "ist_risiko": True},
]

# Kategoriegewichte je Klasse — 1:1 aus der Verträge-Tabelle
# docs/specs/anlageklassen-config.md (AC8). Jede Zeilen-Gruppe (je
# asset_class_id) summiert exakt auf 100 (AC6).
CATEGORY_WEIGHT_SEED = [
    # Aktien
    {"asset_class_id": 1, "category_code": "fundamental", "weight_pct": 35},
    {"asset_class_id": 1, "category_code": "technisch", "weight_pct": 15},
    {"asset_class_id": 1, "category_code": "qualitativ", "weight_pct": 20},
    {"asset_class_id": 1, "category_code": "makro", "weight_pct": 10},
    {"asset_class_id": 1, "category_code": "risiko_quant", "weight_pct": 20},
    # ETFs
    {"asset_class_id": 2, "category_code": "fundamental", "weight_pct": 30},
    {"asset_class_id": 2, "category_code": "technisch", "weight_pct": 10},
    {"asset_class_id": 2, "category_code": "qualitativ", "weight_pct": 30},
    {"asset_class_id": 2, "category_code": "makro", "weight_pct": 15},
    {"asset_class_id": 2, "category_code": "risiko_quant", "weight_pct": 15},
    # Cash/Geldmarkt
    {"asset_class_id": 3, "category_code": "fundamental", "weight_pct": 30},
    {"asset_class_id": 3, "category_code": "technisch", "weight_pct": 0},
    {"asset_class_id": 3, "category_code": "qualitativ", "weight_pct": 20},
    {"asset_class_id": 3, "category_code": "makro", "weight_pct": 35},
    {"asset_class_id": 3, "category_code": "risiko_quant", "weight_pct": 15},
    # Obligationen
    {"asset_class_id": 4, "category_code": "fundamental", "weight_pct": 30},
    {"asset_class_id": 4, "category_code": "technisch", "weight_pct": 10},
    {"asset_class_id": 4, "category_code": "qualitativ", "weight_pct": 10},
    {"asset_class_id": 4, "category_code": "makro", "weight_pct": 25},
    {"asset_class_id": 4, "category_code": "risiko_quant", "weight_pct": 25},
    # Aktive Fonds
    {"asset_class_id": 5, "category_code": "fundamental", "weight_pct": 30},
    {"asset_class_id": 5, "category_code": "technisch", "weight_pct": 5},
    {"asset_class_id": 5, "category_code": "qualitativ", "weight_pct": 30},
    {"asset_class_id": 5, "category_code": "makro", "weight_pct": 10},
    {"asset_class_id": 5, "category_code": "risiko_quant", "weight_pct": 25},
    # Immobilien
    {"asset_class_id": 6, "category_code": "fundamental", "weight_pct": 35},
    {"asset_class_id": 6, "category_code": "technisch", "weight_pct": 5},
    {"asset_class_id": 6, "category_code": "qualitativ", "weight_pct": 20},
    {"asset_class_id": 6, "category_code": "makro", "weight_pct": 20},
    {"asset_class_id": 6, "category_code": "risiko_quant", "weight_pct": 20},
    # Kryptowährungen
    {"asset_class_id": 7, "category_code": "fundamental", "weight_pct": 18},
    {"asset_class_id": 7, "category_code": "technisch", "weight_pct": 22},
    {"asset_class_id": 7, "category_code": "qualitativ", "weight_pct": 15},
    {"asset_class_id": 7, "category_code": "makro", "weight_pct": 20},
    {"asset_class_id": 7, "category_code": "risiko_quant", "weight_pct": 25},
    # Rohstoffe
    {"asset_class_id": 8, "category_code": "fundamental", "weight_pct": 30},
    {"asset_class_id": 8, "category_code": "technisch", "weight_pct": 20},
    {"asset_class_id": 8, "category_code": "qualitativ", "weight_pct": 5},
    {"asset_class_id": 8, "category_code": "makro", "weight_pct": 25},
    {"asset_class_id": 8, "category_code": "risiko_quant", "weight_pct": 20},
    # Infrastrukturfonds
    {"asset_class_id": 9, "category_code": "fundamental", "weight_pct": 35},
    {"asset_class_id": 9, "category_code": "technisch", "weight_pct": 5},
    {"asset_class_id": 9, "category_code": "qualitativ", "weight_pct": 20},
    {"asset_class_id": 9, "category_code": "makro", "weight_pct": 20},
    {"asset_class_id": 9, "category_code": "risiko_quant", "weight_pct": 20},
    # FX
    {"asset_class_id": 10, "category_code": "fundamental", "weight_pct": 20},
    {"asset_class_id": 10, "category_code": "technisch", "weight_pct": 25},
    {"asset_class_id": 10, "category_code": "qualitativ", "weight_pct": 5},
    {"asset_class_id": 10, "category_code": "makro", "weight_pct": 30},
    {"asset_class_id": 10, "category_code": "risiko_quant", "weight_pct": 20},
    # Derivate
    {"asset_class_id": 11, "category_code": "fundamental", "weight_pct": 15},
    {"asset_class_id": 11, "category_code": "technisch", "weight_pct": 35},
    {"asset_class_id": 11, "category_code": "qualitativ", "weight_pct": 10},
    {"asset_class_id": 11, "category_code": "makro", "weight_pct": 15},
    {"asset_class_id": 11, "category_code": "risiko_quant", "weight_pct": 25},
]

_TRIGGER_FUNCTION_NAME = "check_category_weight_sum"
_TRIGGER_NAME = "trg_category_weight_sum_check"


def upgrade() -> None:
    """Upgrade schema."""
    analysis_category = op.create_table(
        "analysis_category",
        sa.Column("code", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("ist_risiko", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint(
            "code IN ('fundamental', 'technisch', 'qualitativ', 'makro', 'risiko_quant')",
            name="ck_analysis_category_code",
        ),
    )

    category_weight = op.create_table(
        "category_weight",
        sa.Column(
            "asset_class_id",
            sa.SmallInteger(),
            sa.ForeignKey("asset_class.id"),
            primary_key=True,
        ),
        sa.Column(
            "category_code",
            sa.String(),
            sa.ForeignKey("analysis_category.code"),
            primary_key=True,
        ),
        sa.Column("weight_pct", sa.Numeric(6, 3), nullable=False),
        sa.Column(
            "config_version",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.CheckConstraint(
            "weight_pct >= 0 AND weight_pct <= 100", name="ck_category_weight_range"
        ),
    )

    # Idempotenter Seed (data-model.md §11 Punkt 10: "ON CONFLICT DO NOTHING").
    op.execute(
        pg_insert(analysis_category)
        .values(ANALYSIS_CATEGORY_SEED)
        .on_conflict_do_nothing(index_elements=["code"])
    )
    op.execute(
        pg_insert(category_weight)
        .values(CATEGORY_WEIGHT_SEED)
        .on_conflict_do_nothing(index_elements=["asset_class_id", "category_code"])
    )

    # BR-101 DB-Layer: Σ weight_pct je asset_class_id muss exakt 100 (±0.01)
    # sein. Deferred Constraint Trigger, damit die 5 Zeilen einer Klasse
    # innerhalb derselben Transaktion (Seed wie künftige Config-Writes)
    # eingefügt werden dürfen, bevor am COMMIT geprüft wird (AC7: eine
    # ungültige Gewichtung wird zurückgewiesen — die ganze Transaktion rollt
    # zurück, nichts davon wird wirksam).
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_TRIGGER_FUNCTION_NAME}() RETURNS TRIGGER AS $$
        DECLARE
            affected_id SMALLINT;
            total NUMERIC(8,3);
            row_count INTEGER;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                affected_id := OLD.asset_class_id;
            ELSE
                affected_id := NEW.asset_class_id;
            END IF;

            SELECT COUNT(*), COALESCE(SUM(weight_pct), 0) INTO row_count, total
            FROM category_weight
            WHERE asset_class_id = affected_id;

            -- AC6 verlangt genau 5 Gewichte je Klasse (eine je
            -- Analysekategorie). row_count = 0 bedeutet: keine Zeile (mehr)
            -- fuer diese Klasse vorhanden (z.B. alle 5 Zeilen einer Klasse
            -- geloescht, um sie innerhalb derselben Transaktion neu zu
            -- seeden) -- ein zulaessiger Zwischen-/Leerzustand. Jede andere
            -- Anzahl (z.B. eine einzelne 100%-Zeile) ist ungueltig, auch
            -- wenn die Summe zufaellig 100 ergibt.
            IF row_count NOT IN (0, 5) THEN
                RAISE EXCEPTION
                    'category_weight: asset_class_id % hat % Gewichte statt 5 (AC6)',
                    affected_id, row_count;
            END IF;

            IF total <> 0 AND ABS(total - 100) > 0.01 THEN
                RAISE EXCEPTION
                    'category_weight: Summe fuer asset_class_id % ist % (erwartet 100 +/- 0.01)',
                    affected_id, total;
            END IF;

            IF TG_OP = 'UPDATE' AND OLD.asset_class_id <> NEW.asset_class_id THEN
                SELECT COUNT(*), COALESCE(SUM(weight_pct), 0) INTO row_count, total
                FROM category_weight
                WHERE asset_class_id = OLD.asset_class_id;

                IF row_count NOT IN (0, 5) THEN
                    RAISE EXCEPTION
                        'category_weight: asset_class_id % hat % Gewichte statt 5 (AC6)',
                        OLD.asset_class_id, row_count;
                END IF;

                IF total <> 0 AND ABS(total - 100) > 0.01 THEN
                    RAISE EXCEPTION
                        'category_weight: Summe fuer asset_class_id % ist % (erwartet 100)',
                        OLD.asset_class_id, total;
                END IF;
            END IF;

            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        f"""
        CREATE CONSTRAINT TRIGGER {_TRIGGER_NAME}
        AFTER INSERT OR UPDATE OR DELETE ON category_weight
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION {_TRIGGER_FUNCTION_NAME}();
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER_NAME} ON category_weight")
    op.execute(f"DROP FUNCTION IF EXISTS {_TRIGGER_FUNCTION_NAME}()")
    op.drop_table("category_weight")
    op.drop_table("analysis_category")
