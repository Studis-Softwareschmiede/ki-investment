"""version category_weight (AC10) — replace config_version tag with append-only history

Covers (anlageklassen-config): AC10 (Kategoriegewichte-Teil)

Quelle: docs/data-model.md §1 `category_weight_version` / `category_weight`
(S-018-Präzisierung), BR-101, BR-133; docs/specs/anlageklassen-config.md AC10.

Ersetzt die reine `category_weight.config_version SMALLINT`-Tag-Spalte aus
S-004 (Migration `2da446925bbc_...py`) — diese Spalte markierte zwar einen
Versionswert, überschrieb aber bei jeder Änderung dieselbe Zeile (keine
Historie, siehe Docstring der Vorgänger-Migration). Diese Migration führt
`category_weight_version` als eigenständiges Versionsregister ein
(vollständiger Snapshot je Version, append-only) und macht
`config_version_id` zum dritten Teil des `category_weight`-PK:

1. `category_weight_version` anlegen (UUID-PK, `is_current`, `note`) +
   partieller UNIQUE-Index auf `is_current` (genau eine aktuelle Version,
   BR-133).
2. Genau eine initiale Version einfügen (Migration der bestehenden 55
   S-004-Seed-Zeilen als „Version 1").
3. `config_version_id` auf `category_weight` ergänzen, mit der initialen
   Version befüllen (Backfill), NOT NULL setzen, FK anlegen.
4. Alten zusammengesetzten PK `(asset_class_id, category_code)` gegen
   `(asset_class_id, category_code, config_version_id)` tauschen.
5. Alte `config_version`-Tag-Spalte droppen (durch `config_version_id`
   ersetzt — data-model.md-Notiz bei S-004 markierte sie explizit als
   "NICHT ausreichend für AC10").
6. Den deferred Σ=100-Constraint-Trigger (`2da446925bbc`) auf
   `(asset_class_id, config_version_id)`-Scope umstellen — ohne diese
   Änderung würden mehrere Versionen einer Klasse gemeinsam summiert, sobald
   künftig eine zweite Version existiert (BR-101-Bruch).

`downgrade()` verwirft die Versionshistorie (nur die zuletzt aktuelle
Version bleibt als flache `config_version`-Spalte erhalten) — vertretbar,
da laut alembic/A14 kein allgemeines Muster für rückwärtskompatible
Daten-Downgrades existiert und dies der Zustand vor dieser Migration ist.

Revision ID: 386f43ae972d
Revises: 0da3d5a72ba2
Create Date: 2026-07-13 09:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "386f43ae972d"
down_revision: Union[str, Sequence[str], None] = "0da3d5a72ba2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TRIGGER_FUNCTION_NAME = "check_category_weight_sum"
_TRIGGER_NAME = "trg_category_weight_sum_check"
_CURRENT_VERSION_INDEX = "ux_category_weight_version_current"
_INITIAL_VERSION_NOTE = "Initial-Version — migriert aus S-004-Seed (2da446925bbc)"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "category_weight_version",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("note", sa.String(), nullable=True),
    )
    op.execute(
        f"""
        CREATE UNIQUE INDEX {_CURRENT_VERSION_INDEX}
        ON category_weight_version (is_current)
        WHERE is_current
        """
    )

    # Initiale Version fuer die bestehenden S-004-Seed-Zeilen (BR-133: genau
    # eine is_current=true-Zeile, hier trivial erfuellt). Statischer,
    # quote-freier Konstanten-String -- keine Interpolation von Nutzer-/
    # Laufzeit-Input (security/R03 nicht einschlaegig).
    op.execute(f"INSERT INTO category_weight_version (note) VALUES ('{_INITIAL_VERSION_NOTE}')")

    # Alten Trigger VOR dem Backfill-UPDATE droppen: Postgres verweigert ein
    # nachfolgendes ALTER TABLE (SET NOT NULL/PK-Tausch), solange innerhalb
    # derselben Transaktion noch ausstehende DEFERRED-Trigger-Events auf der
    # Tabelle existieren ("cannot ALTER TABLE ... because it has pending
    # trigger events", empirisch gegen Postgres 17 verifiziert,
    # Coder-Self-Test) — das Backfill-UPDATE würde sonst den alten
    # `trg_category_weight_sum_check` (deferred) pro Zeile feuern.
    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER_NAME} ON category_weight")
    op.execute(f"DROP FUNCTION IF EXISTS {_TRIGGER_FUNCTION_NAME}()")

    op.add_column(
        "category_weight",
        sa.Column("config_version_id", UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        """
        UPDATE category_weight
        SET config_version_id = (SELECT id FROM category_weight_version LIMIT 1)
        WHERE config_version_id IS NULL
        """
    )
    op.alter_column("category_weight", "config_version_id", nullable=False)
    op.create_foreign_key(
        "fk_category_weight_config_version_id",
        "category_weight",
        "category_weight_version",
        ["config_version_id"],
        ["id"],
    )
    op.create_index(
        "ix_category_weight_config_version_id", "category_weight", ["config_version_id"]
    )

    op.drop_constraint("category_weight_pkey", "category_weight", type_="primary")
    op.create_primary_key(
        "category_weight_pkey",
        "category_weight",
        ["asset_class_id", "category_code", "config_version_id"],
    )

    op.drop_column("category_weight", "config_version")

    # Trigger auf (asset_class_id, config_version_id)-Scope umstellen (siehe
    # Modul-Docstring Punkt 6) — bereits oben (vor dem Backfill-UPDATE)
    # gedroppt; hier nur Neuanlage mit der erweiterten Scope-Logik.
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_TRIGGER_FUNCTION_NAME}() RETURNS TRIGGER AS $$
        DECLARE
            affected_asset_class_id SMALLINT;
            affected_config_version_id UUID;
            total NUMERIC(8,3);
            row_count INTEGER;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                affected_asset_class_id := OLD.asset_class_id;
                affected_config_version_id := OLD.config_version_id;
            ELSE
                affected_asset_class_id := NEW.asset_class_id;
                affected_config_version_id := NEW.config_version_id;
            END IF;

            SELECT COUNT(*), COALESCE(SUM(weight_pct), 0) INTO row_count, total
            FROM category_weight
            WHERE asset_class_id = affected_asset_class_id
              AND config_version_id = affected_config_version_id;

            -- AC6 verlangt genau 5 Gewichte je (Klasse, Version). row_count = 0
            -- bedeutet: keine Zeile (mehr) fuer diese Kombination vorhanden
            -- (z.B. alle 5 Zeilen geloescht, um sie innerhalb derselben
            -- Transaktion neu zu seeden) -- ein zulaessiger
            -- Zwischen-/Leerzustand. Jede andere Anzahl ist ungueltig.
            IF row_count NOT IN (0, 5) THEN
                RAISE EXCEPTION
                    'category_weight: Klasse % / Version % hat % Zeilen statt 5 (AC6)',
                    affected_asset_class_id, affected_config_version_id, row_count;
            END IF;

            IF total <> 0 AND ABS(total - 100) > 0.01 THEN
                RAISE EXCEPTION
                    'category_weight: Klasse % / Version % Summe % (erwartet 100 +/- 0.01)',
                    affected_asset_class_id, affected_config_version_id, total;
            END IF;

            IF TG_OP = 'UPDATE' AND (
                OLD.asset_class_id <> NEW.asset_class_id
                OR OLD.config_version_id <> NEW.config_version_id
            ) THEN
                SELECT COUNT(*), COALESCE(SUM(weight_pct), 0) INTO row_count, total
                FROM category_weight
                WHERE asset_class_id = OLD.asset_class_id
                  AND config_version_id = OLD.config_version_id;

                IF row_count NOT IN (0, 5) THEN
                    RAISE EXCEPTION
                        'category_weight: Klasse % / Version % hat % Zeilen statt 5 (AC6)',
                        OLD.asset_class_id, OLD.config_version_id, row_count;
                END IF;

                IF total <> 0 AND ABS(total - 100) > 0.01 THEN
                    RAISE EXCEPTION
                        'category_weight: Klasse % / Version % Summe % (erwartet 100)',
                        OLD.asset_class_id, OLD.config_version_id, total;
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
    # Neuen Trigger VOR der DELETE-Bereinigung und den nachfolgenden
    # ALTER-TABLE-Schritten droppen — sonst feuert das DELETE den
    # (deferred) Trigger pro Zeile, und Postgres verweigert anschliessend
    # jedes ALTER TABLE auf `category_weight`, solange noch ausstehende
    # Trigger-Events in derselben Transaktion existieren (siehe
    # `upgrade()`-Kommentar, empirisch gegen Postgres 17 verifiziert).
    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER_NAME} ON category_weight")
    op.execute(f"DROP FUNCTION IF EXISTS {_TRIGGER_FUNCTION_NAME}()")

    # Verwirft alle Nicht-Aktuell-Versionen (Historie geht beim Downgrade
    # verloren, siehe Modul-Docstring) — sonst verletzt die anschliessend
    # wiederhergestellte 2-Spalten-PK (asset_class_id, category_code)
    # Eindeutigkeit, sobald mehr als eine Version existiert.
    op.execute(
        """
        DELETE FROM category_weight
        WHERE config_version_id NOT IN (
            SELECT id FROM category_weight_version WHERE is_current
        )
        """
    )

    op.add_column(
        "category_weight",
        sa.Column("config_version", sa.SmallInteger(), nullable=False, server_default=sa.text("1")),
    )
    op.drop_constraint("category_weight_pkey", "category_weight", type_="primary")
    op.create_primary_key(
        "category_weight_pkey", "category_weight", ["asset_class_id", "category_code"]
    )
    op.drop_index("ix_category_weight_config_version_id", table_name="category_weight")
    op.drop_constraint(
        "fk_category_weight_config_version_id", "category_weight", type_="foreignkey"
    )
    op.drop_column("category_weight", "config_version_id")
    op.execute(f"DROP INDEX IF EXISTS {_CURRENT_VERSION_INDEX}")
    op.drop_table("category_weight_version")

    # Alten (asset_class_id-scope) Trigger zuletzt wiederherstellen — nach
    # allen strukturellen Änderungen, damit keine Zwischen-Inserts/-Deletes
    # (z.B. das DELETE oben) ihn unnötig auslösen.
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
