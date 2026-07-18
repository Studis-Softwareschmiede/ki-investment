"""create order and trade_fill (Order-Lifecycle-Zustände & TCA-Fills, S-048)

Covers (ausfuehrung-paper): AC6, AC7, AC8

Quelle: docs/data-model.md §4 `order`/`trade_fill` (C-016), S-048-präzisiert
(`order.order_typ` — deckungsgleich mit `ExecutionOrderTyp`/AC6, siehe
Präzisierungsnote in data-model.md); Spec `docs/specs/ausfuehrung-paper.md`
(Story S-048, "Verträge" — Ausführungsergebnis-Tupel `{ fill_preis,
ausgefuehrte_menge, tatsaechliche_kosten, arrival_price, slippage, status }`);
BR-113 (order.mode), BR-114 (trade_fill.slippage_abs), BR-139 (Reject/Timeout
verändert keinen Bestand).

AC7: `trade_fill.slippage_abs` speichert die Arrival-Price-Slippage je Fill
(`app.domain.execution.order_ausfuehrung.berechne_arrival_price_slippage`,
BR-114) — Grundlage der Order-Ausführungs-eigenen TCA (C-016).

AC8: `order.status` trägt den nach `app.domain.execution.order_ausfuehrung
.verarbeite_fill` ermittelten Endzustand (`filled|teilfill|rejected|
timeout`); ein `trade_fill`-Eintrag entsteht NUR bei `filled`/`teilfill`
(BR-139) — `rejected`/`timeout` erzeugen ausschliesslich den `order`-Zeile
selbst (kein Bestand verändert).

Revision ID: 4c822552d4d7
Revises: b6c1f4a08e27
Create Date: 2026-07-18 09:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

# revision identifiers, used by Alembic.
revision: str = "4c822552d4d7"
down_revision: Union[str, Sequence[str], None] = "b6c1f4a08e27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "order",
        sa.Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("position_id", PGUUID(as_uuid=True), sa.ForeignKey("position.id"), nullable=True),
        sa.Column(
            "instrument_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("instrument.id"),
            nullable=False,
        ),
        sa.Column(
            "platform_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("trading_platform.id"),
            nullable=True,
        ),
        sa.Column("richtung", sa.String(), nullable=False),
        sa.Column("order_typ", sa.String(), nullable=False),
        sa.Column("menge", sa.Numeric(20, 8), nullable=False),
        sa.Column("limit_preis", sa.Numeric(20, 8), nullable=True),
        sa.Column("arrival_price", sa.Numeric(20, 8), nullable=False),
        sa.Column("exit_urgency", sa.String(), nullable=True),
        sa.Column("tranche_index", sa.SmallInteger(), nullable=True),
        sa.Column("tranche_total", sa.SmallInteger(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("richtung IN ('buy', 'sell')", name="ck_order_richtung"),
        sa.CheckConstraint(
            "order_typ IN ('market', 'limit', 'stop', 'stop_limit', 'trailing', 'twap')",
            name="ck_order_order_typ",
        ),
        sa.CheckConstraint("menge > 0", name="ck_order_menge_positive"),
        sa.CheckConstraint(
            "exit_urgency IN ('hard', 'soft', 'none')", name="ck_order_exit_urgency"
        ),
        sa.CheckConstraint(
            "status IN ('offen', 'teilfill', 'filled', 'rejected', 'timeout', 'cancelled')",
            name="ck_order_status",
        ),
        sa.CheckConstraint("mode IN ('echt', 'simuliert')", name="ck_order_mode"),
    )
    op.create_index("ix_order_position_id", "order", ["position_id"])
    op.create_index("ix_order_status", "order", ["status"])
    op.create_index("ix_order_mode", "order", ["mode"])
    op.create_index("ix_order_created_at", "order", ["created_at"])

    op.create_table(
        "trade_fill",
        sa.Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("order_id", PGUUID(as_uuid=True), sa.ForeignKey("order.id"), nullable=False),
        sa.Column("fill_preis", sa.Numeric(20, 8), nullable=False),
        sa.Column("fill_menge", sa.Numeric(20, 8), nullable=False),
        sa.Column("courtage_chf", sa.Numeric(20, 8), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "spread_kosten_chf", sa.Numeric(20, 8), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("slippage_abs", sa.Numeric(20, 8), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("fill_menge > 0", name="ck_trade_fill_menge_positive"),
    )
    op.create_index("ix_trade_fill_order_id", "trade_fill", ["order_id"])
    op.create_index("ix_trade_fill_executed_at", "trade_fill", ["executed_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_trade_fill_executed_at", table_name="trade_fill")
    op.drop_index("ix_trade_fill_order_id", table_name="trade_fill")
    op.drop_table("trade_fill")

    op.drop_index("ix_order_created_at", table_name="order")
    op.drop_index("ix_order_mode", table_name="order")
    op.drop_index("ix_order_status", table_name="order")
    op.drop_index("ix_order_position_id", table_name="order")
    op.drop_table("order")
