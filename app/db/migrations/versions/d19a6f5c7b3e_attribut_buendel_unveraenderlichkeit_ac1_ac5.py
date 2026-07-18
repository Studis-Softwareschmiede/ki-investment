"""attribut buendel unveraenderlichkeit (AC1/AC5, S-040)

Covers (strategie-exit-regeln): AC1, AC5

Quelle: docs/data-model.md §4 `position`/`exit_rule` (C-011, C-014); Spec
`docs/specs/strategie-exit-regeln.md` (Story S-040) AC1/AC5, BR-111,
BR-137.

Diese Migration schliesst die beiden von S-015/S-038 explizit offen
gelassenen Lücken (siehe Docstrings von `app.db.models.ExitRule`/
`Position` vor S-040):

1. **AC1-Voraussetzung:** `exit_rule.stop_typ` erlaubte bislang nicht den
   Wert `'technisch'`, den `app.db.exit_regel_ableitung
   .klassifiziere_exit_kategorie` für die Kategorie `daytrade_swing`
   liefert (`exit_default_set`-Seed, Migration `655b7f43eff4`) — ohne diese
   Erweiterung würde die Fixierung (AC1, `SqlAlchemyPositionRepository
   .lege_position_an`) einer Daytrade/Swing-Position an der
   CHECK-Constraint scheitern. Die Wertemenge wird dazu von
   `app.db.models.EXIT_RULE_STOP_TYP_VALUES` bezogen (kein drittes,
   unabhängiges Duplikat der Werteliste, S-037-Lesson).
2. **AC5 (BR-111):** `exit_rule` wird unter Postgres per `BEFORE UPDATE OR
   DELETE`-Trigger vor jeder Mutation/Löschung geschützt — analog zu
   `transaction` (BR-115, Migration `a1c4e7f2b930`) und `trial_registry`
   (BR-118, Migration `e4f7a1c9b2d3`).
3. **AC5 (BR-137, neu):** `position.strategy_id`/`position.time_horizon_id`/
   `position.these` sind nach dem Kauf unveränderlich — ANDERS als
   `exit_rule`/`transaction` ist `position` aber KEINE reine Append-only-
   Tabelle (`menge`, `einstand_preis`, `status`, `closed_at` etc. werden
   von `aktualisiere_kauf`/`verbuche_verkauf_lot` regulär fortgeschrieben,
   S-016). Der Trigger vergleicht daher NUR diese drei Spalten
   (`IS DISTINCT FROM`) und lässt jede andere Spaltenänderung unangetastet
   durch.

Unter SQLite (Struktur-Tests) werden weder die CHECK-Erweiterung noch die
Trigger als Postgres-DDL abgebildet — die Struktur-Tests prüfen die
CHECK-Erweiterung direkt gegen `Base.metadata` (ORM-Modell), die Trigger
sind laut Projekt-Konvention (siehe `a1c4e7f2b930`/`e4f7a1c9b2d3`) Teil des
Coder-Self-Tests gegen eine echte Postgres-Instanz.

Revision ID: d19a6f5c7b3e
Revises: 3c0ecd3737cb
Create Date: 2026-07-18 09:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d19a6f5c7b3e"
down_revision: Union[str, Sequence[str], None] = "3c0ecd3737cb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_EXIT_RULE_STOP_TYP_OLD = "stop_typ IN ('fix_pct', 'atr_trailing', 'fundamental', 'keiner')"
_EXIT_RULE_STOP_TYP_NEW = (
    "stop_typ IN ('fix_pct', 'atr_trailing', 'fundamental', 'technisch', 'keiner')"
)

_EXIT_RULE_TRIGGER_NAME = "trg_exit_rule_append_only"
_EXIT_RULE_TRIGGER_FUNCTION_NAME = "exit_rule_append_only_guard"
_POSITION_TRIGGER_NAME = "trg_position_attribut_buendel_lock"
_POSITION_TRIGGER_FUNCTION_NAME = "position_attribut_buendel_lock_guard"


def upgrade() -> None:
    """Upgrade schema."""
    # --- AC1-Voraussetzung: 'technisch' als gueltiger exit_rule.stop_typ ---
    op.drop_constraint("ck_exit_rule_stop_typ", "exit_rule", type_="check")
    op.create_check_constraint("ck_exit_rule_stop_typ", "exit_rule", _EXIT_RULE_STOP_TYP_NEW)

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # --- AC5/BR-111: exit_rule ist nach dem Insert vollstaendig unveraenderlich ---
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_EXIT_RULE_TRIGGER_FUNCTION_NAME}() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'exit_rule ist nach Position-Open unveraenderlich (BR-111) - '
                'UPDATE/DELETE nicht erlaubt';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_EXIT_RULE_TRIGGER_NAME}
        BEFORE UPDATE OR DELETE ON exit_rule
        FOR EACH ROW EXECUTE FUNCTION {_EXIT_RULE_TRIGGER_FUNCTION_NAME}();
        """
    )

    # --- AC5/BR-137: nur strategy_id/time_horizon_id/these auf position sind gesperrt ---
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_POSITION_TRIGGER_FUNCTION_NAME}() RETURNS trigger AS $$
        BEGIN
            IF NEW.strategy_id IS DISTINCT FROM OLD.strategy_id
                OR NEW.time_horizon_id IS DISTINCT FROM OLD.time_horizon_id
                OR NEW.these IS DISTINCT FROM OLD.these
            THEN
                RAISE EXCEPTION
                    'position.strategy_id/time_horizon_id/these sind nach Kauf '
                    'unveraenderlich (BR-137) - UPDATE dieser Spalten nicht erlaubt';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_POSITION_TRIGGER_NAME}
        BEFORE UPDATE ON position
        FOR EACH ROW EXECUTE FUNCTION {_POSITION_TRIGGER_FUNCTION_NAME}();
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(f"DROP TRIGGER IF EXISTS {_POSITION_TRIGGER_NAME} ON position;")
        op.execute(f"DROP FUNCTION IF EXISTS {_POSITION_TRIGGER_FUNCTION_NAME}();")
        op.execute(f"DROP TRIGGER IF EXISTS {_EXIT_RULE_TRIGGER_NAME} ON exit_rule;")
        op.execute(f"DROP FUNCTION IF EXISTS {_EXIT_RULE_TRIGGER_FUNCTION_NAME}();")

    op.drop_constraint("ck_exit_rule_stop_typ", "exit_rule", type_="check")
    op.create_check_constraint("ck_exit_rule_stop_typ", "exit_rule", _EXIT_RULE_STOP_TYP_OLD)
