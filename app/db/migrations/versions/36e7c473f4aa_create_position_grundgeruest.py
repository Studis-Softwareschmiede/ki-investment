"""create position grundgeruest (instrument, position, exit_rule)

Covers (depot): AC1, AC10

Quelle: docs/data-model.md §1 `instrument`, §4 `position`/`exit_rule`; Spec
`docs/specs/depot.md` (Story S-015).

data-model.md §11 (Migrations-Reihenfolge) ordnet `strategy`/`time_horizon`
der Stammdaten-Basis (Schritt 1) und `instrument` Schritt 3 zu, beide harte
FK-Voraussetzungen für `position` (Schritt 6). `strategy`/`time_horizon`
kommen seit dem Merge von S-037 (Migration
`ddaf9dcc6216_create_strategy_cluster_strategy_and_.py`, `down_revision`
dieser Migration) bereits vollständig samt Katalog-Seed — diese Migration
legt sie daher NICHT mehr selbst (leer) an; nur `instrument` bleibt hier als
harte, noch von keiner anderen Story angelegte FK-Voraussetzung mitgezogen
(analog zur `analysis_category`-Voraussetzung aus S-004, Migration
`2da446925bbc`, kein Seed, kein Board-Item legt `instrument` an).

`position`/`exit_rule` selbst sind das "Positions-Grundgerüst" dieser Story
(AC1: mindestens Titel-Identität, Menge, Einstandspreis, Anlageklasse,
GICS-Branche, Strategie, Zeithorizont, Exit-Regeln, These je Position).
"Aktuelle Bewertung" (ebenfalls AC1) ist bewusst KEINE Spalte — sie kommt
live über den Socket-Live-Kurs-Zugriff (Spec §Verträge "Bewertung").

BR-111 (exit_rule nach Position-Open unveränderlich, kein UPDATE) wird HIER
NICHT durchgesetzt (kein Trigger/Grant-Entzug) — das ist Sache der Story,
die die Attribut-Bündel-Fixierung umsetzt (S-040), nicht dieses
Positions-Grundgerüsts.

Revision ID: 36e7c473f4aa
Revises: ddaf9dcc6216
Create Date: 2026-07-12 15:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

# revision identifiers, used by Alembic.
revision: str = "36e7c473f4aa"
down_revision: Union[str, Sequence[str], None] = "ddaf9dcc6216"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # --- Stammdaten-/FK-Voraussetzung (leer, kein Seed — siehe Docstring) ---
    op.create_table(
        "instrument",
        sa.Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "asset_class_id",
            sa.SmallInteger(),
            sa.ForeignKey("asset_class.id"),
            nullable=False,
        ),
        sa.Column("gics_sector", sa.String(), nullable=True),
        sa.Column("gics_industry", sa.String(), nullable=True),
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column("liquiditaet", sa.Numeric(20, 8), nullable=True),
        sa.Column("volatilitaet", sa.Numeric(10, 6), nullable=True),
        sa.UniqueConstraint("symbol", "asset_class_id", name="uq_instrument_symbol_asset_class"),
        sa.CheckConstraint("length(currency) = 3", name="ck_instrument_currency_iso3"),
    )
    op.create_index("ix_instrument_asset_class_id", "instrument", ["asset_class_id"])
    op.create_index("ix_instrument_symbol", "instrument", ["symbol"])

    # --- Positions-Grundgerüst (AC1) ---
    op.create_table(
        "position",
        sa.Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "instrument_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("instrument.id"),
            nullable=False,
        ),
        sa.Column(
            "asset_class_id",
            sa.SmallInteger(),
            sa.ForeignKey("asset_class.id"),
            nullable=False,
        ),
        sa.Column(
            "strategy_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("strategy.id"),
            nullable=False,
        ),
        sa.Column(
            "time_horizon_id",
            sa.SmallInteger(),
            sa.ForeignKey("time_horizon.id"),
            nullable=False,
        ),
        sa.Column("these", sa.String(), nullable=False),
        sa.Column("menge", sa.Numeric(20, 8), nullable=False),
        sa.Column("einstand_preis", sa.Numeric(20, 8), nullable=False),
        sa.Column(
            "einstand_methode",
            sa.String(),
            nullable=False,
            server_default=sa.text("'gleitender_durchschnitt'"),
        ),
        sa.Column(
            "realisierter_gv", sa.Numeric(20, 8), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("unrealisierter_gv", sa.Numeric(20, 8), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("menge >= 0", name="ck_position_menge_non_negative"),
        sa.CheckConstraint(
            "einstand_methode IN ('gleitender_durchschnitt', 'fifo')",
            name="ck_position_einstand_methode",
        ),
        sa.CheckConstraint("status IN ('offen', 'geschlossen')", name="ck_position_status"),
        sa.CheckConstraint("mode IN ('echt', 'simuliert')", name="ck_position_mode"),
    )
    op.create_index("ix_position_instrument_id", "position", ["instrument_id"])
    op.create_index("ix_position_status", "position", ["status"])
    op.create_index("ix_position_mode", "position", ["mode"])
    op.create_index("ix_position_asset_class_id", "position", ["asset_class_id"])

    op.create_table(
        "exit_rule",
        sa.Column(
            "position_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("position.id"),
            primary_key=True,
        ),
        sa.Column("stop_loss_pct", sa.Numeric(6, 3), nullable=True),
        sa.Column("take_profit_pct", sa.Numeric(6, 3), nullable=True),
        sa.Column("stop_typ", sa.String(), nullable=True),
        sa.Column("atr_multiplikator", sa.Numeric(5, 2), nullable=True),
        sa.Column("thesis_invalidation", sa.String(), nullable=True),
        sa.Column("time_box", sa.Interval(), nullable=True),
        sa.CheckConstraint(
            "stop_typ IN ('fix_pct', 'atr_trailing', 'fundamental', 'keiner')",
            name="ck_exit_rule_stop_typ",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("exit_rule")
    op.drop_index("ix_position_asset_class_id", table_name="position")
    op.drop_index("ix_position_mode", table_name="position")
    op.drop_index("ix_position_status", table_name="position")
    op.drop_index("ix_position_instrument_id", table_name="position")
    op.drop_table("position")
    op.drop_index("ix_instrument_symbol", table_name="instrument")
    op.drop_index("ix_instrument_asset_class_id", table_name="instrument")
    op.drop_table("instrument")
