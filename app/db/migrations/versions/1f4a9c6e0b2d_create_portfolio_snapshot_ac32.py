"""create portfolio_snapshot (AC32 Portfolio-Wert-Snapshot-Read-Modell)

Covers (frontend-cockpit): AC32

Quelle: docs/data-model.md §5 `portfolio_snapshot` (S-081-Präzisierung),
§8 Index `(mode, snapshot_at)` + UNIQUE `(mode, snapshot_datum)`, §10
BR-142; Spec `docs/specs/frontend-cockpit.md` AC32, Story S-081.

`portfolio_snapshot` war seit der S-036-Migrationswelle als Schema für
eine spätere Persistenz-/Historien-Story reserviert (nie migriert) — diese
Migration legt sie erstmals an, als das AC32-Read-Modell für den
Depot-Verlauf-Chart (AC33). `portfolio_weight` (Klassen-/Branchen-Split je
Snapshot) bleibt bewusst unmigriert (AC32 nennt den Split optional, AC33
braucht nur die Wert-Zeitreihe).

`snapshot_datum` (S-081-Ergänzung zum ursprünglich reservierten Schema):
aus `snapshot_at` abgeleiteter Kalendertag (UTC) — Grundlage von
`UNIQUE (mode, snapshot_datum)` (→ BR-142): Idempotenz des periodischen
Snapshot-Jobs (`app.scheduler.portfolio_snapshot_job`), ein erneuter Lauf
am selben Kalendertag erzeugt keine Duplikat-Zeile.

Revision ID: 1f4a9c6e0b2d
Revises: 827b9dcc737c
Create Date: 2026-07-19 09:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

# revision identifiers, used by Alembic.
revision: str = "1f4a9c6e0b2d"
down_revision: Union[str, Sequence[str], None] = "827b9dcc737c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "portfolio_snapshot",
        sa.Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "snapshot_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("snapshot_datum", sa.Date(), nullable=False),
        sa.Column("total_value_chf", sa.Numeric(20, 8), nullable=False),
        sa.Column("cash_quote_pct", sa.Numeric(6, 3), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.CheckConstraint("mode IN ('echt', 'simuliert')", name="ck_portfolio_snapshot_mode"),
        sa.UniqueConstraint(
            "mode", "snapshot_datum", name="uq_portfolio_snapshot_mode_snapshot_datum"
        ),
    )
    op.create_index(
        "ix_portfolio_snapshot_mode_snapshot_at", "portfolio_snapshot", ["mode", "snapshot_at"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_portfolio_snapshot_mode_snapshot_at", table_name="portfolio_snapshot")
    op.drop_table("portfolio_snapshot")
